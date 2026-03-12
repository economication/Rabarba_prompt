"""
Prompt Assembler node.

Input:  current_prompt, risk_report, target_agent, iteration_count, prompt_versions
Output: current_prompt (updated with risk + agent sections), prompt_versions (updated)

Deterministic Python function — NO LLM call.

Responsibilities:
  1. Insert or REPLACE the ## ⚠️ Risk Assessment section (never duplicate)
  2. Insert or REPLACE the ## Target Agent section if target_agent is set (never duplicate)
  3. Create a new PromptVersion entry in prompt_versions for this iteration.
     - fail_signature and reviewer_verdict are set to "" at this stage.
     - Reviewer will update them after completing its review (two-phase update).

Per rule 16: return the full updated prompt_versions list, never a partial append.
"""

from __future__ import annotations  # Python 3.9 compat: enables X | Y union syntax

import re

from app.graph.state import PromptOptimizerState, PromptVersion, RiskReport

_RISK_HEADER = "## ⚠️ Risk Assessment"
_AGENT_HEADER = "## Target Agent"


def _format_risk_section(risk_report: RiskReport) -> str:
    safe_str = "Yes" if risk_report.safe_to_proceed else "No"

    def fmt_list(items: list[str], empty: str = "None identified") -> str:
        if not items:
            return empty
        return "\n".join(f"- {item}" for item in items)

    return (
        f"{_RISK_HEADER}\n\n"
        f"**Breaking Risk:** {risk_report.breaking_risk}\n"
        f"**Safe to Proceed:** {safe_str}\n\n"
        f"**Affected Files:**\n{fmt_list(risk_report.affected_files)}\n\n"
        f"**Test Gaps:**\n{fmt_list(risk_report.test_gaps)}\n\n"
        f"**Required Actions Before Implementation:**\n"
        f"{fmt_list(risk_report.required_actions_before_implementation, empty='None')}\n\n"
        f"**Rationale:** {risk_report.rationale}"
    )


def _find_section_bounds(text: str, header: str) -> tuple[int, int] | None:
    """
    Locate a markdown section by its exact header line.
    Returns (start_char, end_char) or None if not found.
    The range covers from the header line to just before the next ## heading (or EOF).
    """
    lines = text.splitlines(keepends=True)
    header_stripped = header.rstrip()
    start_line: int | None = None

    for i, line in enumerate(lines):
        if line.rstrip("\r\n").rstrip() == header_stripped:
            start_line = i
            break

    if start_line is None:
        return None

    end_line = len(lines)
    for i in range(start_line + 1, len(lines)):
        if re.match(r"^#{1,6}\s", lines[i]):
            end_line = i
            break

    start_pos = sum(len(ln) for ln in lines[:start_line])
    end_pos = sum(len(ln) for ln in lines[:end_line])
    return (start_pos, end_pos)


def _replace_or_append_section(text: str, header: str, new_section: str) -> str:
    """
    Replace the existing markdown section identified by `header`, or append it.
    `new_section` must start with the header line itself.
    """
    bounds = _find_section_bounds(text, header)

    if bounds is None:
        # Section absent — append with blank-line separator
        sep = "\n\n" if text.rstrip("\n") else ""
        return text.rstrip("\n") + sep + new_section.rstrip("\n") + "\n"

    start, end = bounds
    prefix = text[:start].rstrip("\n")
    suffix = text[end:].lstrip("\n")

    if suffix:
        return (
            prefix
            + "\n\n"
            + new_section.rstrip("\n")
            + "\n\n"
            + suffix.rstrip("\n")
            + "\n"
        )
    return prefix + "\n\n" + new_section.rstrip("\n") + "\n"


def prompt_assembler_node(state: PromptOptimizerState) -> dict:
    current_prompt = state["current_prompt"]
    risk_report = state["risk_report"]
    target_agent = state.get("target_agent")
    iteration_count = state.get("iteration_count", 0)
    prompt_versions = list(state.get("prompt_versions", []))

    # Insert / replace Target Agent section
    if target_agent:
        agent_section = f"{_AGENT_HEADER}\n\n**Agent:** {target_agent}"
        current_prompt = _replace_or_append_section(
            current_prompt, _AGENT_HEADER, agent_section
        )

    # Insert / replace Risk Assessment section
    risk_section = _format_risk_section(risk_report)
    current_prompt = _replace_or_append_section(
        current_prompt, _RISK_HEADER, risk_section
    )

    # Two-phase PromptVersion: create entry now, Reviewer will fill fail_signature
    # and reviewer_verdict. iteration = iteration_count + 1 (upcoming review cycle).
    new_version = PromptVersion(
        iteration=iteration_count + 1,
        prompt_text=current_prompt,
        fail_signature="",
        reviewer_verdict="",
    )
    prompt_versions.append(new_version)

    return {
        "current_prompt": current_prompt,
        "prompt_versions": prompt_versions,
    }
