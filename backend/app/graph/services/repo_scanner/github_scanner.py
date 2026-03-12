"""
GitHub repository scanner stub.

EXTENSION POINT: Implement GitHubRepoScanner to support remote GitHub repos.
Steps:
  1. Accept a GitHub URL or "owner/repo" string as `source`
  2. Use the GitHub API (or git clone) to retrieve the file tree
  3. Implement the same scan() interface as LocalRepoScanner
  4. Instantiate based on input type in the repo_scanner node
"""

from app.graph.state import RepoContext
from app.graph.services.repo_scanner.base import BaseRepoScanner


class GitHubRepoScanner(BaseRepoScanner):
    # TODO: implement GitHub repo scanning
    # Suggested approach:
    #   - Accept GITHUB_TOKEN from settings for authenticated requests
    #   - Use https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1
    #     to retrieve the full file tree without cloning
    #   - Fetch key config files (package.json, requirements.txt, etc.) via raw content API
    #   - Parse them with the same heuristics used in LocalRepoScanner

    def scan(self, source: str) -> RepoContext:
        raise NotImplementedError(
            "GitHubRepoScanner is not implemented yet. "
            "Use a local path for now, or implement this class."
        )
