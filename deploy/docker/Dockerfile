# Pinned to an immutable version tag (not :latest). CI re-pins to the digest
# (FROM python@sha256:...) at release time.
FROM python:3.12.7-slim

# Non-root runtime user.
RUN useradd --create-home --uid 10001 appuser
WORKDIR /app

# Install the package (deps resolved from pyproject). Build context is repo root.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache

# Served over the network in containers: streamable-http transport + metrics.
ENV KETTLELOGIC_BASE_URL=https://kettlelogic.com \
    KETTLELOGIC_TRANSPORT=streamable-http \
    KETTLELOGIC_HTTP_HOST=0.0.0.0 \
    KETTLELOGIC_HTTP_PORT=8080 \
    KETTLELOGIC_METRICS_PORT=9464

EXPOSE 8080 9464
USER appuser

# Liveness/readiness signal: the always-on metrics endpoint.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9464/metrics', timeout=3)"]

ENTRYPOINT ["mcp-kettlelogic"]
