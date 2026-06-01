"""Ratchets: test-suite and dependency hygiene.

- No skipped tests.
- Every ``test_*`` function makes an assertion (``assert`` or ``pytest.raises``).
- Every declared dependency carries a version specifier (no unpinned deps).
"""

from __future__ import annotations

import ast
import tomllib

from tests.ratchets._support import REPO_ROOT, TESTS_ROOT

_SPECIFIERS = (">=", "==", "~=", "<=", ">", "<", "!=")


def _test_files() -> list[ast.Module]:
    modules: list[ast.Module] = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        modules.append(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    return modules


def test_no_skipped_tests() -> None:
    offenders: list[str] = []
    for path in sorted(TESTS_ROOT.rglob("test_*.py")):
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                if any(_is_skip_marker(dec) for dec in node.decorator_list):
                    offenders.append(f"{path.name}::{node.name}")
            elif isinstance(node, ast.Call) and _is_skip_call(node):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == [], f"skipped tests are not allowed: {offenders}"


def test_every_test_has_an_assertion() -> None:
    offenders: list[str] = []
    for module in _test_files():
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith(
                "test_"
            ):
                if not _has_assertion(node):
                    offenders.append(node.name)
    assert offenders == [], f"tests without assertions: {offenders}"


def test_dependencies_are_pinned() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    declared: list[str] = list(project.get("dependencies", []))
    for extras in project.get("optional-dependencies", {}).values():
        declared.extend(extras)
    unpinned = [dep for dep in declared if not any(spec in dep for spec in _SPECIFIERS)]
    assert unpinned == [], f"unpinned dependencies: {unpinned}"


def _is_skip_marker(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return isinstance(target, ast.Attribute) and target.attr in {"skip", "skipif"}


def _is_skip_call(node: ast.Call) -> bool:
    # pytest.skip(...) — but not pytest.importorskip(...)
    return isinstance(node.func, ast.Attribute) and node.func.attr == "skip"


def _has_assertion(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Assert):
            return True
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute):
            if inner.func.attr == "raises":
                return True
    return False
