"""Abstract base class for repository scanners."""

from abc import ABC, abstractmethod

from app.graph.state import RepoContext


class BaseRepoScanner(ABC):
    """
    Abstract interface for repository scanners.
    LocalRepoScanner and future GitHubRepoScanner must both implement this.

    EXTENSION POINT: To add GitHub support, implement GitHubRepoScanner(BaseRepoScanner)
    in github_scanner.py and instantiate it based on config/input.
    """

    @abstractmethod
    def scan(self, source: str) -> RepoContext:
        """
        Scan the given source (local path or remote URL) and return a RepoContext.
        Must never raise — on failure, return a RepoContext with scan_warnings populated
        and all other fields as empty lists.
        """
        ...
