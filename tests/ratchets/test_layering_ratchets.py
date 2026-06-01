"""Ratchets: hexagonal layering chokepoints.

- The environment is read only in the config layer.
- Outbound HTTP (httpx) lives only in the HTTP client layer.
- JSON serialization lives only in the serializer layer.
"""

from __future__ import annotations

from tests.ratchets._support import SourceTree

_TREE = SourceTree()


def test_env_access_only_in_config() -> None:
    offenders = _scan(allowed="config.py", needles=("os.environ", "os.getenv", "getenv("))
    assert offenders == [], f"env access outside config layer: {offenders}"


def test_httpx_only_in_http_client() -> None:
    offenders = _scan(allowed="http_client.py", needles=("import httpx", "httpx."))
    assert offenders == [], f"network access outside client layer: {offenders}"


def test_json_only_in_serializer() -> None:
    offenders = _scan(allowed="serializer.py", needles=("import json", "json."))
    assert offenders == [], f"json usage outside serializer layer: {offenders}"


def _scan(allowed: str, needles: tuple[str, ...]) -> list[str]:
    offenders: list[str] = []
    for path in _TREE.files():
        if path.name == allowed:
            continue
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                offenders.append(f"{_TREE.rel(path)}: {needle}")
    return offenders
