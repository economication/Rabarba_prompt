"""
Repo Scanner node.

Input:  repo_path (from state)
Output: repo_context

No LLM call. Uses LocalRepoScanner (BaseRepoScanner subclass).
If repo_path is empty/None or the path is invalid, sets repo_context to None and continues.
"""

from app.graph.state import PromptOptimizerState
from app.graph.services.repo_scanner.local_scanner import LocalRepoScanner


def repo_scanner_node(state: PromptOptimizerState) -> dict:
    repo_path = state.get("repo_path")

    if not repo_path or not repo_path.strip():
        return {"repo_context": None}

    scanner = LocalRepoScanner()
    repo_context = scanner.scan(repo_path.strip())

    # If scan produced only warnings and no files, the path was likely invalid.
    # repo_context is still returned (with scan_warnings) so the UI can surface them.
    return {"repo_context": repo_context}
