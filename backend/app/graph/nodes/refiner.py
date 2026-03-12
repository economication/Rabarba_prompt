"""
Refiner node.

Input:  current_prompt, review_result (FAIL issues only)
Output: current_prompt (updated)

LLM: Anthropic claude-sonnet-4-5, temperature 0.4

Rules (enforced via system prompt + input restriction):
  - Receives ONLY current_prompt + ordered list of FAIL issues {code, fix_instruction}
  - Does NOT receive full reviewer reasoning or UNCERTAIN items
  - Must NOT rewrite from scratch or expand scope
  - Must preserve passing sections exactly
  - Must NOT alter the risk section unless a fix explicitly targets it

After Refiner: flow MUST continue to Risk Assessor → Prompt Assembler → Reviewer.
(Wired in graph.py — Refiner itself does not control this.)

iteration_count is NOT incremented here — incremented after next Reviewer completes.
"""

import json

from app.graph.state import PromptOptimizerState
from app.graph.services.llm.anthropic_provider import AnthropicProvider
from app.graph.prompts.system_prompts import REFINER_SYSTEM


def refiner_node(state: PromptOptimizerState) -> dict:
    provider = AnthropicProvider()

    current_prompt = state["current_prompt"]
    review_result = state["review_result"]

    # Pass ONLY fail issues with code + fix_instruction — no full reasoning, no UNCERTAIN
    fail_issues = [
        {"code": issue.code, "fix_instruction": issue.fix_instruction}
        for issue in review_result.issues
        if issue.verdict == "FAIL"
    ]

    if not fail_issues:
        # No FAIL items — nothing to refine. Should not happen if stop logic works correctly.
        return {}

    user_prompt = (
        f"Current Prompt:\n{current_prompt}\n\n"
        f"FAIL Issues to Fix (apply ONLY these, nothing else):\n"
        f"{json.dumps(fail_issues, indent=2)}\n\n"
        "Apply the specified fixes. Return only the refined prompt text."
    )

    refined_prompt: str = provider.generate(
        system_prompt=REFINER_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.4,
    )

    return {"current_prompt": refined_prompt}
