"""
FastAPI routes for Rabarba Prompt.

POST /api/optimize        — run the full prompt optimization workflow
GET  /api/runs            — list recent runs (last 50)
GET  /api/runs/{run_id}   — run detail with prompt_versions, cost, final result
GET  /api/health          — liveness check

Error contract:
  - On graph error: return 200 with stop_reason="error" and last_error populated.
  - Never return 5xx for workflow errors.
  - Persistence failures are logged and silently swallowed.
  - All Pydantic validation errors produce 422 (FastAPI default).
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.api.schemas import (
    CostSummary,
    NodeCostSummary,
    PromptVersionOut,
    RunDetailResponse,
    RunSummary,
)
from app.graph.graph import graph
from app.graph.services.persistence import (
    create_run,
    list_runs,
    load_run_detail,
    save_result,
    save_run_artifacts,
    update_run_status,
)
from app.graph.state import NodeUsage, PromptOptimizerState

logger = logging.getLogger(__name__)
router = APIRouter()

STATUS_MAP = {
    "all_pass":       "completed",
    "repeated_fail":  "completed",
    "max_iterations": "completed",
    "uncertain_only": "completed",
    "error":          "failed",
}

# Maps PromptVersion.reviewer_verdict → PromptVersionOut.reviewer_verdict
_VERDICT_MAP = {
    "accept":         "all_pass",
    "revise":         "has_failures",
    "human_required": "uncertain_only",
    "":               "",
}

_STABLE_STOP_REASONS = {"all_pass", "uncertain_only"}


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class OptimizeRequest(BaseModel):
    task_brief: str
    repo_path: Optional[str] = None
    target_agent: Optional[str] = None
    max_iterations: Optional[int] = 3

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _aggregate_costs(node_usages: list[NodeUsage]) -> tuple[float, int, int, list[NodeCostSummary]]:
    """Return (total_cost, total_input, total_output, by_node_list)."""
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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/api/optimize", response_model=OptimizeResponse)
def optimize_prompt(request: OptimizeRequest) -> OptimizeResponse:
    run_id = str(uuid.uuid4())
    config_dict = {
        "target_agent": request.target_agent,
        "max_iterations": request.max_iterations or 3,
        "reviewer_config": {},
    }

    create_run(run_id, request.task_brief, config_dict)
    update_run_status(run_id, "running")

    initial_state: PromptOptimizerState = {
        "task_brief": request.task_brief,
        "repo_path": request.repo_path,
        "target_agent": request.target_agent,
        "max_iterations": request.max_iterations or 3,
        "run_id": run_id,
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

    try:
        result = graph.invoke(initial_state)
    except Exception as exc:
        update_run_status(run_id, "failed", "error")
        return OptimizeResponse(
            run_id=run_id,
            final_prompt="", fail_signature="", stop_reason="error",
            iteration_count=0, risk_summary="", review_summary="",
            last_error=str(exc), scan_warnings=[], review_issues=[], history=[],
            total_cost_usd=0.0, total_input_tokens=0, total_output_tokens=0,
            cost_by_node=[],
        )

    final_summary = result.get("final_summary")
    review_result = result.get("review_result")
    repo_context = result.get("repo_context")
    node_usages: list[NodeUsage] = result.get("node_usages") or []
    stop_reason: str = result.get("stop_reason", "")

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
        for v in result.get("prompt_versions", [])
    ]

    total_cost, total_in, total_out, cost_by_node = _aggregate_costs(node_usages)

    optimize_response = OptimizeResponse(
        run_id=run_id,
        final_prompt=result.get("final_prompt", ""),
        fail_signature=fail_signature,
        stop_reason=stop_reason,
        iteration_count=result.get("iteration_count", 0),
        risk_summary=risk_summary,
        review_summary=review_summary,
        last_error=result.get("last_error"),
        scan_warnings=scan_warnings,
        review_issues=review_issues,
        history=history,
        total_cost_usd=total_cost,
        total_input_tokens=total_in,
        total_output_tokens=total_out,
        cost_by_node=cost_by_node,
    )

    try:
        prompt_versions_out = _build_prompt_versions_out(
            run_id, result.get("prompt_versions", []), stop_reason
        )
        save_run_artifacts(run_id, prompt_versions_out, node_usages)

        if stop_reason != "error":
            save_result(run_id, optimize_response)

        new_status = STATUS_MAP.get(stop_reason, "failed")
        update_run_status(run_id, new_status, stop_reason)

    except Exception as e:
        logger.error(f"Persistence failed for run {run_id}: {e}")

    return optimize_response


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
