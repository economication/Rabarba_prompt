"""
Reviewer node.

Input:  current_prompt, task_brief, structured_requirements, repo_context, risk_report
Output: review_result, prompt_versions (last entry updated), iteration_count (+1),
        node_usages (updated)

LLM: OpenAI gpt-4o-mini, temperature 0.1
(Different vendor than other nodes to reduce same-model confirmation bias.)

Two-phase PromptVersion update:
  Prompt Assembler created the PromptVersion entry with prompt_text.
  Reviewer updates the SAME entry (last in list) with fail_signature + reviewer_verdict.
  A second entry is never created for the same iteration.
"""

import json

from app.graph.state import (
    NodeUsage,
    PromptOptimizerState,
    PromptVersion,
    ReviewResult,
)
from app.graph.services.llm.openai_provider import OpenAIProvider
from app.graph.prompts.system_prompts import REVIEWER_SYSTEM


def reviewer_node(state: PromptOptimizerState) -> dict:
    provider = OpenAIProvider()

    current_prompt = state["current_prompt"]
    task_brief = state["task_brief"]
    structured_requirements = state.get("structured_requirements")
    repo_context = state.get("repo_context")
    risk_report = state.get("risk_report")

    req_text = "null"
    if structured_requirements is not None:
        req_text = json.dumps(structured_requirements.model_dump(), indent=2)

    repo_text = "null (no repository was scanned)"
    if repo_context is not None:
        repo_text = json.dumps(repo_context.model_dump(), indent=2)

    risk_text = "null"
    if risk_report is not None:
        risk_text = json.dumps(risk_report.model_dump(), indent=2)

    user_prompt = (
        f"Task Brief:\n{task_brief}\n\n"
        f"Structured Requirements:\n{req_text}\n\n"
        f"Repository Context:\n{repo_text}\n\n"
        f"Risk Report:\n{risk_text}\n\n"
        f"Implementation Prompt to Review:\n---\n{current_prompt}\n---\n\n"
        "Evaluate this implementation prompt against the 8 rubric dimensions."
    )

    result = provider.generate_structured(
        system_prompt=REVIEWER_SYSTEM,
        user_prompt=user_prompt,
        schema=ReviewResult,
        temperature=0.1,
    )

    usage = NodeUsage(
        node_name="reviewer",
        iteration=state.get("iteration_count", 0),
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
        duration_ms=result.duration_ms,
        model=provider.model,
        vendor="openai",
    )

    # Two-phase update: update the last PromptVersion with reviewer results.
    prompt_versions = list(state.get("prompt_versions", []))
    if prompt_versions:
        last = prompt_versions[-1]
        prompt_versions[-1] = PromptVersion(
            iteration=last.iteration,
            prompt_text=last.prompt_text,
            fail_signature=result.data.fail_signature,
            reviewer_verdict=result.data.verdict,
        )

    return {
        "review_result": result.data,
        "prompt_versions": prompt_versions,
        # Increment here: each completed Reviewer run = +1 to iteration_count
        "iteration_count": state.get("iteration_count", 0) + 1,
        "node_usages": [*state.get("node_usages", []), usage],
    }
