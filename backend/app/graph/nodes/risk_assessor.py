"""
Risk Assessor node.

Input:  current_prompt, repo_context, structured_requirements
Output: risk_report

LLM: Anthropic claude-sonnet-4-5, temperature 0.2

Runs AGAIN after every Refiner step — always operates on the current current_prompt.
If no repo_context: produce a minimal report and state this in rationale.
"""

import json

from app.graph.state import PromptOptimizerState, RiskReport
from app.graph.services.llm.anthropic_provider import AnthropicProvider
from app.graph.prompts.system_prompts import RISK_ASSESSOR_SYSTEM


def risk_assessor_node(state: PromptOptimizerState) -> dict:
    provider = AnthropicProvider()

    current_prompt = state["current_prompt"]
    repo_context = state.get("repo_context")
    structured_requirements = state.get("structured_requirements")

    repo_context_text = (
        "null — no repository was provided or scan failed. "
        "Base the risk assessment on the prompt content alone."
    )
    if repo_context is not None:
        repo_context_text = json.dumps(repo_context.model_dump(), indent=2)

    req_text = "null"
    if structured_requirements is not None:
        req_text = json.dumps(structured_requirements.model_dump(), indent=2)

    user_prompt = (
        f"Implementation Prompt to Assess:\n{current_prompt}\n\n"
        f"Repository Context:\n{repo_context_text}\n\n"
        f"Structured Requirements:\n{req_text}\n\n"
        "Perform a risk assessment on this implementation prompt."
    )

    risk_report: RiskReport = provider.generate_structured(
        system_prompt=RISK_ASSESSOR_SYSTEM,
        user_prompt=user_prompt,
        schema=RiskReport,
        temperature=0.2,
    )

    return {"risk_report": risk_report}
