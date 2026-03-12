"""
Stop Logic node.

Input:  review_result, iteration_count, max_iterations, previous_fail_signature
Output: stop, stop_reason, repeated_fail_signature, previous_fail_signature,
        final_prompt, final_summary  (when stopping)

Pure Python function — NO LLM call.
Source of truth: issue-level verdicts from review_result.issues (not top-level verdict string).

Stop conditions (evaluated in priority order):
  1. all_pass         — all issue verdicts are PASS
  2. repeated_fail    — same non-empty fail_signature as previous iteration
  3. max_iterations   — iteration_count >= max_iterations
  4. uncertain_only   — zero FAILs, one+ UNCERTAINs caused by missing brief context
  5. (continue)       — stop=False, route to Refiner
"""

from app.graph.state import (
    PromptOptimizerState,
    FinalSummary,
    ReviewIssue,
)


_MISSING_CONTEXT_KEYWORDS = [
    "missing",
    "not provided",
    "not specified",
    "not stated",
    "not defined",
    "not mentioned",
    "not included",
    "insufficient",
    "unclear",
    "no information",
    "brief does not",
    "context not available",
    "does not specify",
    "does not mention",
    "does not include",
    "does not state",
    "does not provide",
]


def _uncertain_from_missing_context(issues: list[ReviewIssue]) -> bool:
    """
    Return True only when every UNCERTAIN issue explicitly attributes its
    uncertainty to missing brief/context information (not model indecision).
    """
    uncertain = [i for i in issues if i.verdict == "UNCERTAIN"]
    if not uncertain:
        return False

    for issue in uncertain:
        reason_lower = issue.reason.lower()
        if not any(kw in reason_lower for kw in _MISSING_CONTEXT_KEYWORDS):
            return False  # This UNCERTAIN is due to model uncertainty, not missing context

    return True


def _derive_risk_summary(state: PromptOptimizerState) -> str:
    risk_report = state.get("risk_report")
    if risk_report is None:
        return "No risk assessment was performed."

    parts = [
        f"Breaking Risk: {risk_report.breaking_risk}",
        f"Safe to Proceed: {'Yes' if risk_report.safe_to_proceed else 'No'}",
    ]
    if risk_report.required_actions_before_implementation:
        actions = "; ".join(risk_report.required_actions_before_implementation[:3])
        parts.append(f"Required Actions: {actions}")
    if risk_report.rationale:
        parts.append(f"Rationale: {risk_report.rationale}")

    # Explicitly note absent repo context so the summary is clear
    if state.get("repo_context") is None:
        parts.append("Note: No repository was scanned — assessment based on prompt content only.")

    return " | ".join(parts)


def stop_logic_node(state: PromptOptimizerState) -> dict:
    review_result = state["review_result"]
    iteration_count = state["iteration_count"]
    max_iterations = state["max_iterations"]
    previous_fail_signature = state.get("previous_fail_signature", "")

    issues = review_result.issues
    fail_signature = review_result.fail_signature

    # Evaluate conditions from issue-level verdicts (source of truth per rule 3)
    fail_count = sum(1 for i in issues if i.verdict == "FAIL")
    uncertain_count = sum(1 for i in issues if i.verdict == "UNCERTAIN")
    all_pass = all(i.verdict == "PASS" for i in issues)

    stop = False
    stop_reason = ""

    # Priority 1: all PASS
    if all_pass:
        stop = True
        stop_reason = "all_pass"

    # Priority 2: repeated fail signature (only non-empty signatures qualify)
    elif fail_signature and fail_signature == previous_fail_signature:
        stop = True
        stop_reason = "repeated_fail"

    # Priority 3: max iterations exhausted
    elif iteration_count >= max_iterations:
        stop = True
        stop_reason = "max_iterations"

    # Priority 4: zero FAILs, one+ UNCERTAINs caused by missing context
    elif (
        fail_count == 0
        and uncertain_count > 0
        and _uncertain_from_missing_context(issues)
    ):
        stop = True
        stop_reason = "uncertain_only"

    # Track repeated-fail state (True only when non-empty signatures match)
    repeated = bool(fail_signature) and fail_signature == previous_fail_signature

    updates: dict = {
        "stop": stop,
        "stop_reason": stop_reason if stop else "",
        "previous_fail_signature": fail_signature,
        "repeated_fail_signature": repeated,
    }

    if stop:
        final_summary = FinalSummary(
            risk_summary=_derive_risk_summary(state),
            review_summary=review_result.summary,
            fail_signature=fail_signature,
            stop_reason=stop_reason,
            iteration_count=iteration_count,
        )
        updates["final_prompt"] = state["current_prompt"]
        updates["final_summary"] = final_summary

    return updates
