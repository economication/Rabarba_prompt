"""
Shared Pydantic schemas for the API layer.
These types are used in route responses and persistence helpers.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class NodeCostSummary(BaseModel):
    node_name: str
    call_count: int
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


class CostSummary(BaseModel):
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    by_node: list[NodeCostSummary]


class PromptVersionOut(BaseModel):
    run_id: str
    iteration: int
    source: str = "assembled"
    prompt_text: str
    fail_signature: str = ""
    # Controlled values: "has_failures" | "uncertain_only" | "all_pass" | ""
    reviewer_verdict: str = ""
    is_stable: bool = False
    created_at: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    stop_reason: Optional[str]
    task_brief_preview: str
    created_at: str
    updated_at: str
    iteration_count: int
    total_cost_usd: float


class RunDetailResponse(BaseModel):
    run_id: str
    status: str
    stop_reason: Optional[str]
    task_brief: str
    config: dict
    created_at: str
    updated_at: str
    prompt_versions: list[PromptVersionOut]
    cost_summary: CostSummary
    final_result: Optional[dict]
