"""
All schemas and the main LangGraph state for Rabarba Prompt.

Field naming follows the spec exactly. Do NOT rename required fields.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Supporting schemas (Pydantic for validation + serialization)
# ---------------------------------------------------------------------------


class PromptVersion(BaseModel):
    iteration: int
    # The exact assembled prompt sent to Reviewer — includes Risk Assessment
    # and Target Agent sections. NOT the Drafter output, NOT a Refiner intermediate.
    prompt_text: str
    # Filled in after Reviewer completes (two-phase update)
    fail_signature: str
    reviewer_verdict: str  # "accept" | "revise" | "human_required"


class RepoContext(BaseModel):
    file_tree: list[str]
    entry_points: list[str]
    package_managers: list[str]
    test_frameworks: list[str]
    key_files: list[str]
    dependency_clues: list[str]
    scan_warnings: list[str]


class StructuredRequirements(BaseModel):
    task_type: str
    language_or_tech: str
    scope: str
    constraints: list[str]
    expected_output: str
    acceptance_criteria: list[str]
    risks_or_missing_info: list[str]


class RiskReport(BaseModel):
    breaking_risk: str          # "LOW" | "MEDIUM" | "HIGH"
    safe_to_proceed: bool
    affected_files: list[str]
    dependency_risks: list[str]
    test_gaps: list[str]
    required_actions_before_implementation: list[str]
    rationale: str


class ReviewIssue(BaseModel):
    # Stable machine-readable deficiency code — e.g. "NO_TEST_PLAN"
    code: str
    # Rubric dimension name — e.g. "testability"
    rubric_item: str
    verdict: str                # "PASS" | "FAIL" | "UNCERTAIN"
    reason: str
    fix_instruction: str        # empty string if PASS or UNCERTAIN


class ReviewResult(BaseModel):
    verdict: str                # "accept" | "revise" | "human_required"
    issues: list[ReviewIssue]
    # Pipe-separated, alphabetically sorted FAIL codes — e.g. "NO_TEST_PLAN|SCOPE_AMBIGUOUS"
    fail_signature: str
    summary: str


class FinalSummary(BaseModel):
    risk_summary: str
    review_summary: str
    fail_signature: str
    stop_reason: str
    iteration_count: int


class NodeUsage(BaseModel):
    node_name: str
    iteration: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    model: str
    vendor: str


# ---------------------------------------------------------------------------
# Main LangGraph state
# ---------------------------------------------------------------------------


class PromptOptimizerState(TypedDict):
    # ---- Input (set once at graph start, never mutated) ----
    task_brief: str
    repo_path: Optional[str]
    target_agent: Optional[str]
    max_iterations: int                  # default 3

    # EXTENSION POINT: run_id is a UUID set at start — ready for future persistence
    run_id: Optional[str]

    # ---- Repo context (immutable after Repo Scanner) ----
    repo_context: Optional[RepoContext]

    # ---- Requirements (stable after Input Analyzer) ----
    structured_requirements: Optional[StructuredRequirements]

    # ---- Prompt evolution ----
    current_prompt: str
    # Versioning rule: only PromptVersion snapshots for prompts sent to Reviewer
    # after Prompt Assembler completes. Never save partial/intermediate states.
    prompt_versions: list[PromptVersion]

    # ---- Risk ----
    risk_report: Optional[RiskReport]

    # ---- Review ----
    review_result: Optional[ReviewResult]

    # ---- Stop tracking ----
    iteration_count: int                 # completed review cycles; first review = 1
    previous_fail_signature: str         # for repeated-fail detection
    repeated_fail_signature: bool        # True if same non-empty sig appears twice in a row

    # ---- Terminal state ----
    stop: bool
    # "all_pass" | "repeated_fail" | "max_iterations" | "uncertain_only" | "error"
    stop_reason: str
    # On error: latest successfully assembled prompt, or empty string
    final_prompt: str
    final_summary: Optional[FinalSummary]

    # ---- Cost tracking ----
    node_usages: list[NodeUsage]             # populated by LLM nodes; default: []

    # ---- Error tracking ----
    last_error: Optional[str]
