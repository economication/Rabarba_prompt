"""
Local filesystem repository scanner.

Uses lightweight heuristics only:
  - directory walk with extension filtering
  - package manager config file detection
  - test framework indicator detection
  - entry point detection
  - shallow dependency list extraction from package files

Per spec: NO AST parsing, NO language server, NO full static analyzers.
"""

import json
import os
from pathlib import Path

from app.graph.state import RepoContext
from app.graph.services.repo_scanner.base import BaseRepoScanner

# Source file extensions worth including in the tree
_INCLUDED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".rb",
    ".cpp", ".c", ".h", ".cs", ".php", ".swift", ".kt", ".scala",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".md", ".html",
    ".css", ".scss", ".sql", ".env",
}

# Directories that should not be walked
_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".venv", "venv", "env",
    "dist", "build", "out", ".next", "target", ".cache", "coverage",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

# Map config filename → package manager label
_PACKAGE_MANAGER_FILES: dict[str, str] = {
    "package.json": "npm/yarn/pnpm",
    "pyproject.toml": "pip/poetry/uv",
    "requirements.txt": "pip",
    "Cargo.toml": "cargo",
    "go.mod": "go modules",
    "pom.xml": "maven",
    "build.gradle": "gradle",
    "Gemfile": "bundler",
    "composer.json": "composer",
    "Package.swift": "swift package manager",
}

# Test framework detection: framework label → filename fragments
_TEST_FRAMEWORK_HINTS: dict[str, list[str]] = {
    "pytest": ["pytest.ini", "conftest.py", "setup.cfg"],
    "jest": ["jest.config.js", "jest.config.ts", "jest.setup"],
    "vitest": ["vitest.config"],
    "mocha": [".mocharc"],
    "rspec": [".rspec", "spec_helper.rb"],
    "go test": ["_test.go"],
    "cargo test": ["#[cfg(test)]"],
}

# Likely entry point filenames
_ENTRY_POINT_NAMES = {
    "main.py", "app.py", "server.py", "run.py", "wsgi.py", "asgi.py",
    "index.ts", "main.ts", "index.js", "main.js",
    "main.go", "main.rs", "Main.java", "Program.cs",
}

_MAX_FILES = 600


class LocalRepoScanner(BaseRepoScanner):
    """Scans a local directory using lightweight heuristics."""

    def scan(self, source: str) -> RepoContext:
        path = Path(source)

        if not path.exists() or not path.is_dir():
            return RepoContext(
                file_tree=[],
                entry_points=[],
                package_managers=[],
                test_frameworks=[],
                key_files=[],
                dependency_clues=[],
                scan_warnings=[f"Path does not exist or is not a directory: {source}"],
            )

        file_tree: list[str] = []
        entry_points: list[str] = []
        package_managers: list[str] = []
        test_frameworks: list[str] = []
        key_files: list[str] = []
        scan_warnings: list[str] = []
        file_count = 0

        try:
            for root, dirs, files in os.walk(path, followlinks=False):
                # Prune skipped directories in-place to prevent descending
                dirs[:] = [
                    d for d in sorted(dirs)
                    if not d.startswith(".") and d not in _SKIP_DIRS
                ]

                for filename in sorted(files):
                    if file_count >= _MAX_FILES:
                        scan_warnings.append(
                            f"Scan truncated at {_MAX_FILES} files — large repository."
                        )
                        break

                    file_path = Path(root) / filename
                    try:
                        rel = str(file_path.relative_to(path))
                    except ValueError:
                        continue

                    ext = file_path.suffix.lower()

                    if ext not in _INCLUDED_EXTENSIONS and filename not in _PACKAGE_MANAGER_FILES:
                        continue

                    file_tree.append(rel)
                    file_count += 1

                    # Package manager detection
                    if filename in _PACKAGE_MANAGER_FILES:
                        label = _PACKAGE_MANAGER_FILES[filename]
                        if label not in package_managers:
                            package_managers.append(label)
                        if rel not in key_files:
                            key_files.append(rel)

                    # Entry point detection
                    if filename in _ENTRY_POINT_NAMES and rel not in entry_points:
                        entry_points.append(rel)

                    # Test framework detection by filename fragment
                    for framework, hints in _TEST_FRAMEWORK_HINTS.items():
                        if framework not in test_frameworks:
                            if any(hint in rel for hint in hints):
                                test_frameworks.append(framework)

                if file_count >= _MAX_FILES:
                    break

        except PermissionError as exc:
            scan_warnings.append(f"Permission denied while scanning: {exc}")
        except Exception as exc:  # noqa: BLE001
            scan_warnings.append(f"Unexpected scan error: {exc}")

        dependency_clues = _extract_dependency_clues(path, key_files)

        return RepoContext(
            file_tree=sorted(file_tree),
            entry_points=entry_points,
            package_managers=package_managers,
            test_frameworks=test_frameworks,
            key_files=key_files,
            dependency_clues=dependency_clues,
            scan_warnings=scan_warnings,
        )


def _extract_dependency_clues(base_path: Path, key_files: list[str]) -> list[str]:
    """
    Shallow extraction of dependency names from package files.
    Returns up to 30 clues total. Does not parse deeply — pattern matching only.
    """
    clues: list[str] = []

    for rel in key_files[:5]:
        file_path = base_path / rel
        try:
            if rel.endswith("requirements.txt"):
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        # Strip version specifiers
                        pkg = line.split(">=")[0].split("==")[0].split("~=")[0].strip()
                        if pkg:
                            clues.append(f"dep:{pkg}")
                        if len(clues) >= 20:
                            break

            elif rel.endswith("package.json"):
                data = json.loads(file_path.read_text(encoding="utf-8", errors="ignore"))
                for dep in list(data.get("dependencies", {}).keys())[:15]:
                    clues.append(f"dep:{dep}")
                for dep in list(data.get("devDependencies", {}).keys())[:8]:
                    clues.append(f"devDep:{dep}")

            elif rel.endswith("pyproject.toml"):
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                in_deps = False
                for line in text.splitlines():
                    if "[tool.poetry.dependencies]" in line or (
                        "[project]" in line
                    ):
                        in_deps = True
                    elif in_deps and line.strip().startswith("["):
                        in_deps = False
                    elif in_deps and "=" in line and not line.strip().startswith("#"):
                        name = line.split("=")[0].strip().strip('"')
                        if name and name not in ("python", "requires-python"):
                            clues.append(f"dep:{name}")

        except Exception:  # noqa: BLE001
            pass

    return clues[:30]
