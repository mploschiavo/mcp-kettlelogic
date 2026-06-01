FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml requirements.txt README.md ./
COPY server.py ./
RUN pip install --no-cache-dir .

# Content is fetched live over HTTP from KETTLELOGIC_BASE_URL — nothing to bake in.
ENV KETTLELOGIC_BASE_URL=https://kettlelogic.com

# MCP speaks over stdio; the client launches the container with `-i`.
ENTRYPOINT ["mcp-kettlelogic"]
