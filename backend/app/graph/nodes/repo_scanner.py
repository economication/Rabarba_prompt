"""
Repo Scanner node.

Input:  repo_path or github_url (from state)
Output: repo_context

No LLM call. Uses LocalRepoScanner or GitHubRepoScanner depending on input.
If neither is provided, sets repo_context to None and continues.
"""

from app.graph.state import PromptOptimizerState
from app.graph.services.repo_scanner.local_scanner import LocalRepoScanner
from app.graph.services.repo_scanner.github_scanner import GitHubRepoScanner
from app.core.config import get_settings


def repo_scanner_node(state: PromptOptimizerState) -> dict:
    github_url = state.get("github_url")
    repo_path = state.get("repo_path")

    if github_url and github_url.strip():
        settings = get_settings()
        scanner = GitHubRepoScanner(token=settings.github_token)
        repo_context = scanner.scan(github_url.strip())
    elif repo_path and repo_path.strip():
        scanner = LocalRepoScanner()
        repo_context = scanner.scan(repo_path.strip())
    else:
        return {"repo_context": None}

    return {"repo_context": repo_context}
