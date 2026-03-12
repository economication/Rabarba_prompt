"""
FastAPI routes for Rabarba Prompt.

POST /api/intro             — generate clarification questions (no DB write)
POST /api/optimize          — run prompt optimization workflow (SSE stream)
POST /api/runs/{run_id}/cancel — signal cancellation of a running run
GET  /api/runs              — list recent runs (last 50)
GET  /api/runs/{run_id}     — run detail with prompt_versions, cost, final result
GET  /api/health            — liveness check

Error contract:
  - On graph error: SSE "error" event, then stream ends.
  - Persistence failures are logged and silently swallowed.
  - All Pydantic validation errors produce 422 (FastAPI default).
"""

import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Generator, Optional

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator, model_validator

from app.api.schemas import (
    CostSummary,
    NodeCostSummary,
    PromptVersionOut,
    RunDetailResponse,
    RunSummary,
)
from app.core.config import get_settings
from app.graph.graph import graph
from app.graph.prompts.system_prompts import INTRO_ANALYZER_SYSTEM
from app.graph.services.persistence import (
    create_run,
    list_runs,
    load_run_detail,
    save_intro_data,
    save_result,
    save_run_artifacts,
    update_run_status,
)
from app.graph.state import NodeUsage, PromptOptimizerState

logger = logging.getLogger(__name__)
router = APIRouter()

# In-memory cancel signal store — cleared on restart (acceptable for Wave 2)
cancel_flags: dict[str, bool] = {}

STATUS_MAP = {
    "all_pass":       "completed",
    "repeated_fail":  "completed",
    "max_iterations": "completed",
    "uncertain_only": "completed",
    "error":          "failed",
    "cancelled":      "completed_partial",
}

_VERDICT_MAP = {
    "accept":         "all_pass",
    "revise":         "has_failures",
    "human_required": "uncertain_only",
    "":               "",
}

_STABLE_STOP_REASONS = {"all_pass", "uncertain_only"}


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

class IntroQuestion(BaseModel):
    id: str
    question: str
    type: str  # "text" | "boolean"


FIXED_QUESTIONS: list[IntroQuestion] = [
    IntroQuestion(id="language",      question="Hangi dil veya framework kullanılacak?",                          type="text"),
    IntroQuestion(id="output_format", question="Beklenen çıktı formatı veya yapısı nedir?",                       type="text"),
    IntroQuestion(id="constraints",   question="Kritik kısıtlar veya non-negotiable gereksinimler var mı?",       type="text"),
    IntroQuestion(id="test_required", question="Test yazılması gerekiyor mu?",                                    type="boolean"),
]


class IntroRequest(BaseModel):
    task_brief: str
    target_agent: Optional[str] = None

    @field_validator("task_brief")
    @classmethod
    def task_brief_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task_brief must not be empty")
        return v.strip()


class IntroResponse(BaseModel):
    fixed_questions: list[IntroQuestion]
    dynamic_questions: list[IntroQuestion]


class OptimizeRequest(BaseModel):
    run_id: Optional[str] = None
    task_brief: str
    repo_path: Optional[str] = None
    github_url: Optional[str] = None
    target_agent: Optional[str] = None
    max_iterations: Optional[int] = 3
    intro_questions: Optional[list[IntroQuestion]] = None
    intro_answers: Optional[dict[str, str]] = None

    @field_validator("task_brief")
    @classmethod
    def task_brief_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task_brief must not be empty after trimming whitespace")
        return v.strip()

    @field_validator("max_iterations")
    @classmethod
    def max_iterations_range(cls, v: Optional[int]) -> int:
        if v is None:
            return 3
        if not (1 <= v <= 5):
            raise ValueError("max_iterations must be between 1 and 5 (inclusive)")
        return v

    @field_validator("target_agent")
    @classmethod
    def valid_target_agent(cls, v: Optional[str]) -> Optional[str]:
        allowed = {"Generic", "Cursor", "Claude Code"}
        if v is not None and v not in allowed:
            raise ValueError(f"target_agent must be one of: {', '.join(sorted(allowed))}")
        return v

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        is_full_url = v.startswith("https://github.com/") or v.startswith("http://github.com/")
        is_short = v.count("/") == 1 and "." not in v.split("/")[0]
        if not (is_full_url or is_short):
            raise ValueError("github_url must be a GitHub URL or 'owner/repo' string")
        return v

    @model_validator(mode="after")
    def repo_source_exclusive(self) -> "OptimizeRequest":
        if self.repo_path and self.github_url:
            raise ValueError("repo_path and github_url cannot both be set")
        return self


class ReviewIssueOut(BaseModel):
    code: str
    rubric_item: str
    verdict: str
    reason: str
    fix_instruction: str


class HistoryItemOut(BaseModel):
    iteration: int
    prompt_text: str
    fail_signature: str
    reviewer_verdict: str


class OptimizeResponse(BaseModel):
    run_id: str
    final_prompt: str
    fail_signature: str
    stop_reason: str
    iteration_count: int
    risk_summary: str
    review_summary: str
    last_error: Optional[str]
    scan_warnings: list[str]
    review_issues: list[ReviewIssueOut]
    history: list[HistoryItemOut]
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    cost_by_node: list[NodeCostSummary]
    is_stable: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sse_event(event_type: str, payload: dict) -> str:
    data = {"type": event_type, **payload}
    return f"data: {json.dumps(data)}\n\n"


def _aggregate_costs(node_usages: list[NodeUsage]) -> tuple[float, int, int, list[NodeCostSummary]]:
    by_node: dict[str, list[NodeUsage]] = defaultdict(list)
    for u in node_usages:
        by_node[u.node_name].append(u)

    summaries = [
        NodeCostSummary(
            node_name=name,
            call_count=len(usages),
            total_cost_usd=sum(u.cost_usd for u in usages),
            total_input_tokens=sum(u.input_tokens for u in usages),
            total_output_tokens=sum(u.output_tokens for u in usages),
        )
        for name, usages in by_node.items()
    ]
    total_cost = sum(s.total_cost_usd for s in summaries)
    total_in = sum(s.total_input_tokens for s in summaries)
    total_out = sum(s.total_output_tokens for s in summaries)
    return total_cost, total_in, total_out, summaries


def _build_prompt_versions_out(
    run_id: str,
    prompt_versions: list,
    stop_reason: str,
) -> list[PromptVersionOut]:
    now = _now_iso()
    result = []
    last_idx = len(prompt_versions) - 1
    for i, v in enumerate(prompt_versions):
        mapped_verdict = _VERDICT_MAP.get(v.reviewer_verdict, v.reviewer_verdict)
        is_stable = (i == last_idx) and (stop_reason in _STABLE_STOP_REASONS)
        result.append(
            PromptVersionOut(
                run_id=run_id,
                iteration=v.iteration,
                source="assembled",
                prompt_text=v.prompt_text,
                fail_signature=v.fail_signature,
                reviewer_verdict=mapped_verdict,
                is_stable=is_stable,
                created_at=now,
            )
        )
    return result


def _build_optimize_response(run_id: str, final_state: dict, stop_reason: str) -> OptimizeResponse:
    final_summary = final_state.get("final_summary")
    review_result = final_state.get("review_result")
    repo_context = final_state.get("repo_context")
    node_usages: list[NodeUsage] = final_state.get("node_usages") or []

    risk_summary = final_summary.risk_summary if final_summary else ""
    review_summary = final_summary.review_summary if final_summary else ""
    fail_signature = final_summary.fail_signature if final_summary else ""

    scan_warnings: list[str] = []
    if repo_context is not None:
        scan_warnings = repo_context.scan_warnings

    review_issues: list[ReviewIssueOut] = []
    if review_result is not None:
        review_issues = [
            ReviewIssueOut(
                code=issue.code, rubric_item=issue.rubric_item, verdict=issue.verdict,
                reason=issue.reason, fix_instruction=issue.fix_instruction,
            )
            for issue in review_result.issues
        ]

    history: list[HistoryItemOut] = [
        HistoryItemOut(
            iteration=v.iteration, prompt_text=v.prompt_text,
            fail_signature=v.fail_signature, reviewer_verdict=v.reviewer_verdict,
        )
        for v in final_state.get("prompt_versions", [])
    ]

    total_cost, total_in, total_out, cost_by_node = _aggregate_costs(node_usages)

    is_stable = stop_reason in _STABLE_STOP_REASONS

    return OptimizeResponse(
        run_id=run_id,
        final_prompt=final_state.get("final_prompt", ""),
        fail_signature=fail_signature,
        stop_reason=stop_reason,
        iteration_count=final_state.get("iteration_count", 0),
        risk_summary=risk_summary,
        review_summary=review_summary,
        last_error=final_state.get("last_error"),
        scan_warnings=scan_warnings,
        review_issues=review_issues,
        history=history,
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cost_by_node=cost_by_node,
        is_stable=is_stable,
    )


def _build_partial_response(final_state: dict, run_id: str) -> OptimizeResponse:
    """Build a partial OptimizeResponse for a cancelled run."""
    # Use whatever final_prompt was assembled last
    current_prompt = final_state.get("current_prompt", "")
    final_prompt = final_state.get("final_prompt") or current_prompt

    node_usages: list[NodeUsage] = final_state.get("node_usages") or []
    repo_context = final_state.get("repo_context")
    scan_warnings: list[str] = repo_context.scan_warnings if repo_context else []

    total_cost, total_in, total_out, cost_by_node = _aggregate_costs(node_usages)

    history: list[HistoryItemOut] = [
        HistoryItemOut(
            iteration=v.iteration, prompt_text=v.prompt_text,
            fail_signature=v.fail_signature, reviewer_verdict=v.reviewer_verdict,
        )
        for v in final_state.get("prompt_versions", [])
    ]

    return OptimizeResponse(
        run_id=run_id,
        final_prompt=final_prompt,
        fail_signature="",
        stop_reason="cancelled",
        iteration_count=final_state.get("iteration_count", 0),
        risk_summary="",
        review_summary="",
        last_error=None,
        scan_warnings=scan_warnings,
        review_issues=[],
        history=history,
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cost_by_node=cost_by_node,
        is_stable=False,
    )


def _persist_result(run_id: str, state: dict, response: OptimizeResponse) -> None:
    try:
        stop_reason = response.stop_reason
        prompt_versions_out = _build_prompt_versions_out(
            run_id, state.get("prompt_versions", []), stop_reason
        )
        node_usages = state.get("node_usages") or []
        save_run_artifacts(run_id, prompt_versions_out, node_usages)
        save_result(run_id, response)
        new_status = STATUS_MAP.get(stop_reason, "failed")
        update_run_status(run_id, new_status, stop_reason)
    except Exception as e:
        logger.error(f"Persistence failed for run {run_id}: {e}")


def _persist_cancelled(run_id: str, state: dict, partial: OptimizeResponse) -> None:
    try:
        prompt_versions_out = _build_prompt_versions_out(
            run_id, state.get("prompt_versions", []), "cancelled"
        )
        node_usages = state.get("node_usages") or []
        save_run_artifacts(run_id, prompt_versions_out, node_usages)
        save_result(run_id, partial)
        update_run_status(run_id, "completed_partial", "cancelled")
    except Exception as e:
        logger.error(f"Cancel persistence failed for {run_id}: {e}")


def build_enriched_brief(
    task_brief: str,
    intro_questions: list[IntroQuestion],
    intro_answers: dict[str, str],
) -> str:
    lines = [task_brief, "", "Additional context from user:"]
    question_map = {q.id: q.question for q in intro_questions}
    for qid, question_text in question_map.items():
        answer = intro_answers.get(qid, "").strip()
        if answer:
            lines.append(f"- {question_text}: {answer}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

def _optimize_stream(request: OptimizeRequest) -> Generator[str, None, None]:
    effective_run_id = request.run_id or str(uuid.uuid4())
    config_dict = {
        "target_agent": request.target_agent,
        "max_iterations": request.max_iterations or 3,
        "reviewer_config": {},
    }

    create_run(effective_run_id, request.task_brief, config_dict)

    if request.intro_answers:
        update_run_status(effective_run_id, "intro_complete")
        if request.intro_questions:
            try:
                save_intro_data(effective_run_id, request.intro_questions, request.intro_answers)
            except Exception as e:
                logger.error(f"Failed to save intro_data for {effective_run_id}: {e}")

    update_run_status(effective_run_id, "running")

    # Build enriched task brief if intro answers were provided
    task_brief = request.task_brief
    if request.intro_questions and request.intro_answers:
        task_brief = build_enriched_brief(
            request.task_brief, request.intro_questions, request.intro_answers
        )

    initial_state: PromptOptimizerState = {
        "task_brief": task_brief,
        "repo_path": request.repo_path,
        "github_url": request.github_url,
        "target_agent": request.target_agent,
        "max_iterations": request.max_iterations or 3,
        "run_id": effective_run_id,
        "repo_context": None,
        "structured_requirements": None,
        "current_prompt": "",
        "prompt_versions": [],
        "risk_report": None,
        "review_result": None,
        "iteration_count": 0,
        "previous_fail_signature": "",
        "repeated_fail_signature": False,
        "stop": False,
        "stop_reason": "",
        "final_prompt": "",
        "final_summary": None,
        "node_usages": [],
        "last_error": None,
    }

    # Accumulated state delta (keys from each node's output)
    final_state: dict = dict(initial_state)

    active_node: Optional[str] = None
    active_node_start: float = 0.0
    current_iteration: int = 0

    try:
        for event in graph.stream(initial_state, stream_mode="updates"):
            node_name = list(event.keys())[0]
            node_output = event[node_name]

            # Accumulate state
            if node_output:
                final_state.update(node_output)

            # Cancel check after each node
            if cancel_flags.get(effective_run_id):
                # Emit complete for last active node before cancelling
                if active_node is not None:
                    duration_ms = int((time.time() - active_node_start) * 1000)
                    yield sse_event("stage_complete", {
                        "stage": active_node,
                        "iteration": current_iteration,
                        "duration_ms": duration_ms,
                    })

                partial_response = _build_partial_response(final_state, effective_run_id)
                yield sse_event("cancelled", {"data": partial_response.model_dump()})
                _persist_cancelled(effective_run_id, final_state, partial_response)
                cancel_flags.pop(effective_run_id, None)
                return

            # stop_logic: update iteration counter from accumulated state, skip stage display
            if node_name == "stop_logic":
                # iteration_count is incremented by reviewer (not stop_logic), read from
                # accumulated final_state which already has the updated value
                current_iteration = final_state.get("iteration_count", current_iteration)

                # Emit complete event for the previous visible node (reviewer)
                if active_node is not None and active_node != "stop_logic":
                    duration_ms = int((time.time() - active_node_start) * 1000)
                    yield sse_event("stage_complete", {
                        "stage": active_node,
                        "iteration": current_iteration,
                        "duration_ms": duration_ms,
                    })
                    active_node = None
                continue

            # Emit complete event for the previous visible node
            if active_node is not None:
                duration_ms = int((time.time() - active_node_start) * 1000)
                yield sse_event("stage_complete", {
                    "stage": active_node,
                    "iteration": current_iteration,
                    "duration_ms": duration_ms,
                })

            # Emit start event for this node
            active_node = node_name
            active_node_start = time.time()
            yield sse_event("stage_start", {
                "stage": node_name,
                "iteration": current_iteration,
            })

        # Loop ended — emit complete for last node
        if active_node is not None:
            duration_ms = int((time.time() - active_node_start) * 1000)
            yield sse_event("stage_complete", {
                "stage": active_node,
                "iteration": current_iteration,
                "duration_ms": duration_ms,
            })

    except Exception as exc:
        logger.error(f"Graph stream error for {effective_run_id}: {exc}")
        try:
            update_run_status(effective_run_id, "failed", "error")
        except Exception:
            pass
        yield sse_event("error", {"message": str(exc)})
        return

    # Build and yield the final result
    stop_reason = final_state.get("stop_reason", "")
    optimize_response = _build_optimize_response(effective_run_id, final_state, stop_reason)
    yield sse_event("result", {"data": optimize_response.model_dump()})
    _persist_result(effective_run_id, final_state, optimize_response)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/intro", response_model=IntroResponse)
def intro(request: IntroRequest) -> IntroResponse:
    """Generate clarification questions. Does not write to DB."""
    dynamic_questions: list[IntroQuestion] = []

    try:
        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        agent_hint = f"\nTarget agent: {request.target_agent}" if request.target_agent else ""
        user_prompt = f"Task brief: {request.task_brief}{agent_hint}"

        resp = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=512,
            temperature=0.4,
            system=INTRO_ANALYZER_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            timeout=10.0,
        )
        raw = resp.content[0].text.strip()

        # Parse JSON array
        import re
        # Try direct parse, then extract JSON array
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\[[\s\S]*\]", raw)
            if match:
                items = json.loads(match.group(0))
            else:
                items = []

        for item in items[:2]:
            q_id = str(item.get("id", f"dq_{len(dynamic_questions)}"))
            q_text = str(item.get("question", "")).strip()
            if q_text:
                dynamic_questions.append(IntroQuestion(id=q_id, question=q_text, type="text"))

    except Exception as exc:
        logger.warning(f"Intro dynamic question generation failed (fallback to empty): {exc}")
        dynamic_questions = []

    return IntroResponse(
        fixed_questions=FIXED_QUESTIONS,
        dynamic_questions=dynamic_questions,
    )


@router.post("/api/optimize")
def optimize_prompt(request: OptimizeRequest) -> StreamingResponse:
    return StreamingResponse(
        _optimize_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str) -> dict:
    cancel_flags[run_id] = True
    return {"status": "cancel_requested"}


@router.get("/api/runs", response_model=list[RunSummary])
def get_runs() -> list[RunSummary]:
    return list_runs(limit=50)


@router.get("/api/runs/{run_id}", response_model=RunDetailResponse)
def get_run(run_id: str) -> RunDetailResponse:
    detail = load_run_detail(run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return RunDetailResponse(**detail)


@router.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}
