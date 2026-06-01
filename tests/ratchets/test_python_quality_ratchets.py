"""Ratchets: Python quality.

- No broad/bare excepts (catch specific exceptions).
- Every function/method is fully type-annotated (args + return).
- No ``# type: ignore`` and no ``print(`` in the package.
"""

from __future__ import annotations

import ast

from tests.ratchets._support import SourceTree

_BROAD = {"Exception", "BaseException"}
_SELF_PARAMS = {"self", "cls"}
_TREE = SourceTree()


def test_no_broad_or_bare_except() -> None:
    offenders: list[str] = []
    for path in _TREE.files():
        for node in ast.walk(_TREE.parse(path)):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                offenders.append(f"{_TREE.rel(path)}:{node.lineno} bare except")
            elif isinstance(node.type, ast.Name) and node.type.id in _BROAD:
                offenders.append(f"{_TREE.rel(path)}:{node.lineno} except {node.type.id}")
    assert offenders == [], f"broad excepts: {offenders}"


def test_every_def_is_typed() -> None:
    offenders: list[str] = []
    for path in _TREE.files():
        for node in ast.walk(_TREE.parse(path)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                offenders.extend(_untyped(_TREE.rel(path), node))
    assert offenders == [], f"untyped defs: {offenders}"


def test_no_type_ignore_or_print() -> None:
    offenders: list[str] = []
    for path in _TREE.files():
        text = path.read_text(encoding="utf-8")
        if "type: ignore" in text:
            offenders.append(f"{_TREE.rel(path)}: type: ignore")
        for node in ast.walk(_TREE.parse(path)):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "print":
                offenders.append(f"{_TREE.rel(path)}:{node.lineno} print()")
    assert offenders == [], f"forbidden constructs: {offenders}"


def _untyped(rel: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    found: list[str] = []
    if node.returns is None:
        found.append(f"{rel}::{node.name} (no return type)")
    args = node.args
    positional = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    for arg in positional:
        if arg.arg in _SELF_PARAMS:
            continue
        if arg.annotation is None:
            found.append(f"{rel}::{node.name}({arg.arg})")
    for variadic in (args.vararg, args.kwarg):
        if variadic is not None and variadic.annotation is None:
            found.append(f"{rel}::{node.name}(*{variadic.arg})")
    return found
