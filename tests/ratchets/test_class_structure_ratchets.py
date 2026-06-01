"""Ratchets: class-based architecture.

- No loose functions: behaviour lives in classes, never module-level functions.
- No god classes: a class stays under method/line ceilings.
"""

from __future__ import annotations

import ast

from tests.ratchets._support import SourceTree

_MAX_METHODS_PER_CLASS = 18
_MAX_LINES_PER_CLASS = 220
_TREE = SourceTree()


def test_no_module_level_functions() -> None:
    offenders: list[str] = []
    for path in _TREE.files():
        module = _TREE.parse(path)
        for node in module.body:  # top-level only
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                offenders.append(f"{_TREE.rel(path)}::{node.name}")
    assert offenders == [], f"module-level functions are not allowed: {offenders}"


def test_no_god_classes() -> None:
    offenders: list[str] = []
    for path in _TREE.files():
        for node in ast.walk(_TREE.parse(path)):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = [
                n for n in node.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
            ]
            span = (node.end_lineno or node.lineno) - node.lineno
            if len(methods) > _MAX_METHODS_PER_CLASS or span > _MAX_LINES_PER_CLASS:
                offenders.append(
                    f"{_TREE.rel(path)}::{node.name} "
                    f"(methods={len(methods)}, lines={span})"
                )
    assert offenders == [], f"god classes detected: {offenders}"
