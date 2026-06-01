"""Shared helpers for the ratchet checks.

Ratchets are static-analysis tests that scan ``src/`` and assert **zero**
violations — the codebase is held at the clean state, not a burn-down baseline.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "mcp_kettlelogic"
TESTS_ROOT = REPO_ROOT / "tests"


class SourceTree:
    """Enumerates and parses the package's Python sources."""

    def files(self) -> list[Path]:
        return sorted(SRC_ROOT.rglob("*.py"))

    def parse(self, path: Path) -> ast.Module:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def rel(self, path: Path) -> str:
        return str(path.relative_to(REPO_ROOT))
