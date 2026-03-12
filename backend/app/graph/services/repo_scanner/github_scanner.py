"""
GitHub repository scanner.

Supports public repositories via the GitHub API tree endpoint.
GITHUB_TOKEN is optional but increases rate limit from 60 → 5000 req/hour.
Private repository support is Wave 3.
"""

import json
import logging
import os
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.graph.state import RepoContext
from app.graph.services.repo_scanner.base import BaseRepoScanner
from app.graph.services.repo_scanner.local_scanner import (
    _INCLUDED_EXTENSIONS,
    _PACKAGE_MANAGER_FILES,
    _TEST_FRAMEWORK_HINTS,
    _ENTRY_POINT_NAMES,
)

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_GITHUB_RAW = "https://raw.githubusercontent.com"

_KEY_FILE_NAMES = {
    "package.json", "requirements.txt", "pyproject.toml",
    "go.mod", "Cargo.toml",
}

_MAX_FILES = 600
_REQUEST_TIMEOUT = 15.0


class GitHubRepoScanner(BaseRepoScanner):
    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token

    def scan(self, source: str) -> RepoContext:
        scan_warnings: list[str] = []

        try:
            owner, repo = self._parse_owner_repo(source)
        except ValueError as exc:
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=[str(exc)],
            )

        headers = self._get_headers()

        # Fetch file tree via git trees API
        tree_url = f"{_GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        try:
            resp = httpx.get(tree_url, headers=headers, timeout=_REQUEST_TIMEOUT)
        except httpx.RequestError as exc:
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=[f"GitHub API request failed: {exc}"],
            )

        if resp.status_code in (403, 404):
            # Check for rate limit
            if resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0":
                scan_warnings.append(
                    "GitHub API rate limit exceeded. Set GITHUB_TOKEN to increase limit to 5000 req/hour."
                )
            else:
                scan_warnings.append(
                    "Repository not found or access denied. Private repository support "
                    "requires a GITHUB_TOKEN with repo scope — this will be available "
                    "in a future release."
                )
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=scan_warnings,
            )

        if not resp.is_success:
            scan_warnings.append(f"GitHub API returned HTTP {resp.status_code} for {owner}/{repo}.")
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=scan_warnings,
            )

        try:
            tree_data = resp.json()
        except Exception:
            scan_warnings.append("Failed to parse GitHub API response.")
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=scan_warnings,
            )

        if tree_data.get("truncated"):
            scan_warnings.append(
                f"GitHub tree truncated at {_MAX_FILES} files — large repository."
            )

        raw_tree = tree_data.get("tree", [])
        file_tree: list[str] = []
        entry_points: list[str] = []
        package_managers: list[str] = []
        test_frameworks: list[str] = []
        key_files: list[str] = []
        file_count = 0

        for item in raw_tree:
            if item.get("type") != "blob":
                continue
            path: str = item.get("path", "")
            if not path:
                continue

            filename = path.split("/")[-1]
            ext = os.path.splitext(filename)[1].lower()

            if ext not in _INCLUDED_EXTENSIONS and filename not in _PACKAGE_MANAGER_FILES:
                continue

            if file_count >= _MAX_FILES:
                if not tree_data.get("truncated"):
                    scan_warnings.append(f"Scan truncated at {_MAX_FILES} files — large repository.")
                break

            file_tree.append(path)
            file_count += 1

            # Package manager detection
            if filename in _PACKAGE_MANAGER_FILES:
                label = _PACKAGE_MANAGER_FILES[filename]
                if label not in package_managers:
                    package_managers.append(label)
                if path not in key_files and filename in _KEY_FILE_NAMES:
                    key_files.append(path)

            # Entry point detection
            if filename in _ENTRY_POINT_NAMES and path not in entry_points:
                entry_points.append(path)

            # Test framework detection
            for framework, hints in _TEST_FRAMEWORK_HINTS.items():
                if framework not in test_frameworks:
                    if any(hint in path for hint in hints):
                        test_frameworks.append(framework)

        # Fetch key file contents and extract dependency clues
        dependency_clues = self._extract_dependency_clues(owner, repo, key_files, headers)

        return RepoContext(
            file_tree=sorted(file_tree),
            entry_points=entry_points,
            package_managers=package_managers,
            test_frameworks=test_frameworks,
            key_files=key_files,
            dependency_clues=dependency_clues,
            scan_warnings=scan_warnings,
        )

    def _parse_owner_repo(self, source: str) -> tuple[str, str]:
        """
        Accept "https://github.com/owner/repo" or "owner/repo".
        Strips trailing slash, .git suffix, and query strings.
        """
        s = source.strip().rstrip("/")
        if s.endswith(".git"):
            s = s[:-4]

        if s.startswith("https://") or s.startswith("http://"):
            parsed = urlparse(s)
            parts = [p for p in parsed.path.split("/") if p]
            if len(parts) < 2:
                raise ValueError(f"Cannot parse owner/repo from GitHub URL: {source}")
            return parts[0], parts[1]

        # "owner/repo" format
        parts = s.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Cannot parse owner/repo from: {source}")
        return parts[0], parts[1]

    def _get_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _extract_dependency_clues(
        self,
        owner: str,
        repo: str,
        key_files: list[str],
        headers: dict[str, str],
    ) -> list[str]:
        """Fetch up to 5 key files and extract dependency names."""
        clues: list[str] = []

        for rel in key_files[:5]:
            url = f"{_GITHUB_RAW}/{owner}/{repo}/HEAD/{rel}"
            try:
                resp = httpx.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
                if not resp.is_success:
                    continue
                text = resp.text
            except Exception:
                continue

            filename = rel.split("/")[-1]
            try:
                if filename == "requirements.txt":
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and not line.startswith("-"):
                            pkg = line.split(">=")[0].split("==")[0].split("~=")[0].strip()
                            if pkg:
                                clues.append(f"dep:{pkg}")
                            if len(clues) >= 20:
                                break

                elif filename == "package.json":
                    data = json.loads(text)
                    for dep in list(data.get("dependencies", {}).keys())[:15]:
                        clues.append(f"dep:{dep}")
                    for dep in list(data.get("devDependencies", {}).keys())[:8]:
                        clues.append(f"devDep:{dep}")

                elif filename == "pyproject.toml":
                    in_deps = False
                    for line in text.splitlines():
                        if "[tool.poetry.dependencies]" in line or "[project]" in line:
                            in_deps = True
                        elif in_deps and line.strip().startswith("["):
                            in_deps = False
                        elif in_deps and "=" in line and not line.strip().startswith("#"):
                            name = line.split("=")[0].strip().strip('"')
                            if name and name not in ("python", "requires-python"):
                                clues.append(f"dep:{name}")

            except Exception:
                pass

        return clues[:30]
