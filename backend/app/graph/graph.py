"""
LangGraph graph definition for Rabarba Prompt.

Node execution order:
  Repo Scanner → Input Analyzer → Drafter
  → Risk Assessor → Prompt Assembler → Reviewer → Stop Logic
  → (stop? END : Refiner → Risk Assessor → ...)

CRITICAL LOOP RULE (per spec):
  After every Refiner step the flow MUST continue:
  Refiner → Risk Assessor → Prompt Assembler → Reviewer → Stop Logic
  Never send a refined prompt directly to Reviewer with a stale risk section.

Error handling:
  All LLM nodes are wrapped with make_safe_node().
  On any exception: stop=True, stop_reason="error", last_error=<message>, final_prompt=current_prompt.
  Subsequent nodes see stop=True and return empty dicts (no-ops).
  The conditional edge after stop_logic will route to END.
"""

from typing import Callable

from langgraph.graph import StateGraph, END

from app.graph.state import PromptOptimizerState
from app.graph.nodes.repo_scanner import repo_scanner_node
from app.graph.nodes.input_analyzer import input_analyzer_node
from app.graph.nodes.drafter import drafter_node
from app.graph.nodes.risk_assessor import risk_assessor_node
from app.graph.nodes.prompt_assembler import prompt_assembler_node
from app.graph.nodes.reviewer import reviewer_node
from app.graph.nodes.stop_logic import stop_logic_node
from app.graph.nodes.refiner import refiner_node


# ---------------------------------------------------------------------------
# Error handling wrapper
# ---------------------------------------------------------------------------


def make_safe_node(fn: Callable) -> Callable:
    """
    Wrap a node function so that any unhandled exception is caught and converted
    to a graceful error state instead of crashing the graph.

    On exception:
      - stop       = True
      - stop_reason = "error"
      - last_error  = exception message
      - final_prompt = latest current_prompt (or "" if not yet set)

    Subsequent nodes detect stop=True + stop_reason="error" and return {} (no-op).
    """

    def wrapper(state: PromptOptimizerState) -> dict:
        # Skip silently if a previous node already entered error state
        if state.get("stop") and state.get("stop_reason") == "error":
            return {}
        try:
            return fn(state)
        except Exception as exc:  # noqa: BLE001
            return {
                "stop": True,
                "stop_reason": "error",
                "last_error": str(exc),
                "final_prompt": state.get("current_prompt", ""),
            }

    wrapper.__name__ = fn.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def _route_after_stop_logic(state: PromptOptimizerState) -> str:
    """Route to END when the graph should stop; otherwise continue to Refiner."""
    return "end" if state.get("stop") else "refiner"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build_graph() -> StateGraph:
    builder = StateGraph(PromptOptimizerState)

    # Register nodes (all LLM nodes wrapped for graceful error handling)
    builder.add_node("repo_scanner", make_safe_node(repo_scanner_node))
    builder.add_node("input_analyzer", make_safe_node(input_analyzer_node))
    builder.add_node("drafter", make_safe_node(drafter_node))
    builder.add_node("risk_assessor", make_safe_node(risk_assessor_node))
    builder.add_node("prompt_assembler", make_safe_node(prompt_assembler_node))
    builder.add_node("reviewer", make_safe_node(reviewer_node))
    builder.add_node("stop_logic", make_safe_node(stop_logic_node))
    builder.add_node("refiner", make_safe_node(refiner_node))

    # Entry point
    builder.set_entry_point("repo_scanner")

    # Linear forward path
    builder.add_edge("repo_scanner", "input_analyzer")
    builder.add_edge("input_analyzer", "drafter")
    builder.add_edge("drafter", "risk_assessor")
    builder.add_edge("risk_assessor", "prompt_assembler")
    builder.add_edge("prompt_assembler", "reviewer")
    builder.add_edge("reviewer", "stop_logic")

    # Conditional branch: stop → END, continue → refiner
    builder.add_conditional_edges(
        "stop_logic",
        _route_after_stop_logic,
        {"end": END, "refiner": "refiner"},
    )

    # Loop back: refiner always re-runs risk assessor (never skips it)
    builder.add_edge("refiner", "risk_assessor")

    return builder.compile()


# Module-level compiled graph — imported by routes.py
graph = build_graph()
