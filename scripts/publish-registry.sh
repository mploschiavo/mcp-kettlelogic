#!/usr/bin/env bash
# Publish this server to the MCP registry — LOCALLY, no GitHub Actions minutes.
#
# This is the PRIMARY publish path (GitHub-hosted runners burn quota fast, so the
# release workflow is manual-only). Run it from your machine whenever you cut a
# new version. Idempotent except that registry versions are immutable — bump the
# version first (pass it as $1 and this updates version.py + server.json for you).
#
# Usage:
#   scripts/publish-registry.sh            # publish server.json as-is
#   scripts/publish-registry.sh 1.2.0      # set version to 1.2.0 everywhere, then publish
#
# Requires: the private signing key at .secrets/mcp-registry-key.pem (gitignored)
# and that https://kettlelogic.com/.well-known/mcp-registry-auth serves its public key.
set -euo pipefail
cd "$(dirname "$0")/.."

KEY=".secrets/mcp-registry-key.pem"
BIN="./mcp-publisher"
DOMAIN="kettlelogic.com"

if [[ ! -f "$KEY" ]]; then
  echo "ERROR: $KEY not found — that's the publish credential (see README)." >&2
  exit 1
fi

# Optional version bump (keeps version.py + server.json in lockstep).
if [[ "${1:-}" != "" ]]; then
  VER="${1#v}"
  echo "Setting version to $VER in version.py + server.json…"
  sed -i "s/^VERSION: str = .*/VERSION: str = \"$VER\"/" src/mcp_kettlelogic/version.py
  tmp="$(mktemp)"; jq --arg v "$VER" '.version = $v' server.json > "$tmp" && mv "$tmp" server.json
fi

# Fetch the CLI if it isn't here yet.
if [[ ! -x "$BIN" ]]; then
  echo "Downloading mcp-publisher…"
  curl -fsSL https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz \
    | tar xz mcp-publisher
fi

echo "Validating server.json…"
"$BIN" validate

echo "Authenticating via HTTP domain ownership ($DOMAIN)…"
"$BIN" login http --domain "$DOMAIN" \
  --private-key "$(openssl pkey -in "$KEY" -outform DER | tail -c 32 | xxd -p -c 64)"

echo "Publishing…"
"$BIN" publish
echo "Done. Verify: https://registry.modelcontextprotocol.io/v0/servers?search=com.kettlelogic/mcp-kettlelogic"
