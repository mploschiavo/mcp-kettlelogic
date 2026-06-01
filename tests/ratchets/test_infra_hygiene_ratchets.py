"""Ratchets: Docker and Kubernetes hardening.

Mirrors the media-stack infra ratchets: pinned images, non-root, healthcheck/
probes, resource bounds, replica floor, no hostPath, ClusterIP (not LoadBalancer),
and the presence of .dockerignore / CODEOWNERS.
"""

from __future__ import annotations

import re

from tests.ratchets._support import REPO_ROOT

_DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "Dockerfile"
_DEPLOYMENT = REPO_ROOT / "deploy" / "k8s" / "deployment.yaml"
_SERVICE = REPO_ROOT / "deploy" / "k8s" / "service.yaml"
_PINNED = re.compile(r"@sha256:|:\d")  # digest, or a tag beginning with a digit


def test_repo_hygiene_files_present() -> None:
    assert (REPO_ROOT / ".dockerignore").exists()
    assert (REPO_ROOT / "CODEOWNERS").exists()


def test_dockerfile_is_hardened() -> None:
    text = _DOCKERFILE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in text
    assert re.search(r"(?m)^USER ", text), "must run as a non-root USER"
    assert "apt-get upgrade" not in text
    from_lines = [line for line in text.splitlines() if line.startswith("FROM ")]
    assert from_lines, "no FROM instruction"
    for line in from_lines:
        assert ":latest" not in line
        assert _PINNED.search(line), f"base image not pinned: {line}"


def test_k8s_deployment_is_hardened() -> None:
    text = _DEPLOYMENT.read_text(encoding="utf-8")
    for token in (
        "readinessProbe",
        "livenessProbe",
        "runAsNonRoot: true",
        "readOnlyRootFilesystem: true",
        "allowPrivilegeEscalation: false",
        "requests:",
        "limits:",
    ):
        assert token in text, f"deployment missing {token}"
    assert "hostPath" not in text
    replicas = re.search(r"replicas:\s*(\d+)", text)
    assert replicas is not None and int(replicas.group(1)) >= 2
    image = re.search(r"image:\s*(\S+)", text)
    assert image is not None
    assert ":latest" not in image.group(1)
    assert _PINNED.search(image.group(1)), f"image not pinned: {image.group(1)}"


def test_k8s_service_is_not_loadbalancer() -> None:
    text = _SERVICE.read_text(encoding="utf-8")
    assert "LoadBalancer" not in text
    assert "type: ClusterIP" in text
