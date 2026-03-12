"""
FastAPI routes for Rabarba Prompt.

POST /api/optimize  — run the full prompt optimization workflow
GET  /api/health    — liveness check

Error contract:
  - On graph error: return 200 with stop_reason="error" and last_error populated.
  - Never return 5xx for workflow errors.
  - All Pydantic validation errors produce 422 (FastAPI default).
"""

import uuid
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, field_validator

from app.graph.graph import graph
from app.graph.state import PromptOptimizerState

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas (API layer — separate from internal state schemas)
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
    final_prompt: str
    fail_signature: str
    stop_reason: str
    iteration_count: int
    risk_summary: str
    review_summary: str
    last_error: Optional[str]
    scan_warnings: list[str]
    # Issues from the FINAL review cycle only
    review_issues: list[ReviewIssueOut]
    # Projection of internal prompt_versions — not a separate data structure
    history: list[HistoryItemOut]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/api/optimize", response_model=OptimizeResponse)
def optimize_prompt(request: OptimizeRequest) -> OptimizeResponse:
    """
    Run the LangGraph prompt optimization workflow synchronously.
    FastAPI runs sync route handlers in a thread pool automatically.
    """
    initial_state: PromptOptimizerState = {
        "task_brief": request.task_brief,
        "repo_path": request.repo_path,
        "target_agent": request.target_agent,
        "max_iterations": request.max_iterations or 3,
        # EXTENSION POINT: run_id is available for future persistence
        "run_id": str(uuid.uuid4()),
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
        "last_error": None,
    }

    try:
        result = graph.invoke(initial_state)
    except Exception as exc:
        # Outermost safety net for unhandled graph-level exceptions
        return OptimizeResponse(
            final_prompt="",
            fail_signature="",
            stop_reason="error",
            iteration_count=0,
            risk_summary="",
            review_summary="",
            last_error=str(exc),
            scan_warnings=[],
            review_issues=[],
            history=[],
        )

    final_summary = result.get("final_summary")
    review_result = result.get("review_result")
    repo_context = result.get("repo_context")

    risk_summary = final_summary.risk_summary if final_summary else ""
    review_summary = final_summary.review_summary if final_summary else ""
    fail_signature = final_summary.fail_signature if final_summary else ""

    # scan_warnings come from repo_context; never embedded in risk_summary
    scan_warnings: list[str] = []
    if repo_context is not None:
        scan_warnings = repo_context.scan_warnings

    # review_issues = final cycle only
    review_issues: list[ReviewIssueOut] = []
    if review_result is not None:
        review_issues = [
            ReviewIssueOut(
                code=issue.code,
                rubric_item=issue.rubric_item,
                verdict=issue.verdict,
                reason=issue.reason,
                fix_instruction=issue.fix_instruction,
            )
            for issue in review_result.issues
        ]

    # history is a projection of prompt_versions — not a separate structure
    history: list[HistoryItemOut] = [
        HistoryItemOut(
            iteration=v.iteration,
            prompt_text=v.prompt_text,
            fail_signature=v.fail_signature,
            reviewer_verdict=v.reviewer_verdict,
        )
        for v in result.get("prompt_versions", [])
    ]

    return OptimizeResponse(
        final_prompt=result.get("final_prompt", ""),
        fail_signature=fail_signature,
        stop_reason=result.get("stop_reason", ""),
        iteration_count=result.get("iteration_count", 0),
        risk_summary=risk_summary,
        review_summary=review_summary,
        last_error=result.get("last_error"),
        scan_warnings=scan_warnings,
        review_issues=review_issues,
        history=history,
    )


@router.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}
