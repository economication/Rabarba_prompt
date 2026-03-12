"""
Input Analyzer node.

Input:  task_brief, repo_context
Output: structured_requirements

LLM: Anthropic claude-sonnet-4-5, temperature 0.2
"""

import json

from app.graph.state import PromptOptimizerState, StructuredRequirements
from app.graph.services.llm.anthropic_provider import AnthropicProvider
from app.graph.prompts.system_prompts import INPUT_ANALYZER_SYSTEM


def input_analyzer_node(state: PromptOptimizerState) -> dict:
    provider = AnthropicProvider()

    task_brief = state["task_brief"]
    repo_context = state.get("repo_context")

    repo_context_text = "null"
    if repo_context is not None:
        repo_context_text = json.dumps(repo_context.model_dump(), indent=2)

    user_prompt = (
        f"Task Brief:\n{task_brief}\n\n"
        f"Repository Context (JSON, may be null):\n{repo_context_text}\n\n"
        "Extract structured requirements from the task brief above."
    )

    structured_requirements: StructuredRequirements = provider.generate_structured(
        system_prompt=INPUT_ANALYZER_SYSTEM,
        user_prompt=user_prompt,
        schema=StructuredRequirements,
        temperature=0.2,
    )

    return {"structured_requirements": structured_requirements}
