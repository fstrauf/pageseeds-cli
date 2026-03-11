#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found on PATH"
  exit 1
fi

UPDATE_SHELL=0
if [[ "${1:-}" == "--update-shell" ]]; then
  UPDATE_SHELL=1
fi

uv tool install -e "$ROOT/packages/seo-content-cli"
uv tool install -e "$ROOT/packages/seo-cli"
uv tool install -e "$ROOT/packages/automation-cli"
uv tool install -e "$ROOT/dashboard_ptk"

if [[ "$UPDATE_SHELL" == "1" ]]; then
  uv tool update-shell
fi

echo "Installed tools live in: $(uv tool dir --bin)"
echo "Launch with: pageseeds"

# Best-effort auth check (do not print secrets).
if [[ -f "$ROOT/.env" ]] && grep -q '^CAPSOLVER_API_KEY=' "$ROOT/.env" 2>/dev/null; then
  echo "Auth: CAPSOLVER_API_KEY found in $ROOT/.env (seo-cli will auto-load it when needed)."
else
  echo "Auth: CAPSOLVER_API_KEY not found in $ROOT/.env."
  echo "  Set it as an environment variable, or put it in ~/.config/automation/secrets.env (CAPSOLVER_API_KEY=...)."
fi
