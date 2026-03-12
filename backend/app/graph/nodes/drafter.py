"""
Drafter node.

Input:  structured_requirements, repo_context, target_agent
Output: current_prompt  (first draft — no risk section yet)

LLM: Anthropic claude-sonnet-4-5, temperature 0.7
"""

import json

from app.graph.state import PromptOptimizerState
from app.graph.services.llm.anthropic_provider import AnthropicProvider
from app.graph.prompts.system_prompts import DRAFTER_SYSTEM


def drafter_node(state: PromptOptimizerState) -> dict:
    provider = AnthropicProvider()

    structured_requirements = state["structured_requirements"]
    repo_context = state.get("repo_context")
    target_agent = state.get("target_agent") or "Generic"

    system_prompt = DRAFTER_SYSTEM.format(target_agent=target_agent)

    repo_context_text = "null (no repository was provided)"
    if repo_context is not None:
        repo_context_text = json.dumps(repo_context.model_dump(), indent=2)

    user_prompt = (
        f"Structured Requirements:\n"
        f"{json.dumps(structured_requirements.model_dump(), indent=2)}\n\n"
        f"Repository Context:\n{repo_context_text}\n\n"
        "Create a precise implementation prompt based on the requirements above. "
        "Do NOT include a risk assessment section."
    )

    draft_prompt: str = provider.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.7,
    )

    return {"current_prompt": draft_prompt}
