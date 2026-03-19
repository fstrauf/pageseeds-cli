#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV_BIN="$(uv tool dir --bin)"
UV_TOOLS_DIR="$(uv tool dir)"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found on PATH"
  exit 1
fi

UPDATE_SHELL=0
if [[ "${1:-}" == "--update-shell" ]]; then
  UPDATE_SHELL=1
fi

# Install unified PageSeeds CLI (includes dashboard + all tool functionality)
uv tool install -e "$ROOT"

# Also install the dependent packages so they're available as libraries
uv tool install -e "$ROOT/packages/seo-content-cli" 2>/dev/null || echo "Note: seo-content-cli installed as library dependency"
uv tool install -e "$ROOT/packages/seo-cli" 2>/dev/null || echo "Note: seo-cli installed as library dependency"
uv tool install -e "$ROOT/packages/automation-cli" 2>/dev/null || echo "Note: automation-cli installed as library dependency"

if [[ "$UPDATE_SHELL" == "1" ]]; then
  uv tool update-shell
fi

active_pageseeds="$(command -v pageseeds 2>/dev/null || true)"
expected_pageseeds="$UV_BIN/pageseeds"
PATH_SEPARATOR=":"

if [[ -n "$active_pageseeds" && "$active_pageseeds" != "$expected_pageseeds" ]]; then
  echo ""
  echo "⚠ PATH precedence warning"
  echo "   Active pageseeds: $active_pageseeds"
  echo "   Editable/local pageseeds: $expected_pageseeds"
  echo ""
  echo "To always run latest local code, put uv tool bin first in PATH:"
  echo "  export PATH=\"$UV_BIN${PATH_SEPARATOR}\$PATH\""
  echo ""
  echo "Persist for zsh:"
  echo "  echo 'export PATH=\"$UV_BIN:\$PATH\"' >> ~/.zshrc"
  echo "  exec zsh"
fi

if [[ -x "$expected_pageseeds" && -x "$UV_TOOLS_DIR/pageseeds-cli/bin/python" ]]; then
  local_import_path="$($UV_TOOLS_DIR/pageseeds-cli/bin/python - <<'PY' 2>/dev/null
import dashboard
print(dashboard.__file__)
PY
)"
  if [[ -n "$local_import_path" ]]; then
    echo ""
    echo "Dev check: pageseeds imports dashboard from:"
    echo "  $local_import_path"
  fi
fi

echo ""
echo "✅ PageSeeds CLI installed!"
echo "   Binary location: $UV_BIN"
echo ""
echo "Usage:"
echo "   pageseeds                    # Launch interactive dashboard"
echo "   pageseeds version            # Check version"
echo "   pageseeds version --all      # Check all package versions"
echo "   pageseeds seo keywords ...   # SEO keyword research"
echo "   pageseeds content validate ... # Content validation"
echo "   pageseeds reddit pending ... # Reddit opportunities"
echo ""

# Best-effort auth check (do not print secrets).
if [[ -f "$ROOT/.env" ]] && grep -q '^CAPSOLVER_API_KEY=' "$ROOT/.env" 2>/dev/null; then
  echo "Auth: CAPSOLVER_API_KEY found in $ROOT/.env (SEO tools will auto-load it when needed)."
else
  echo "Auth: CAPSOLVER_API_KEY not found in $ROOT/.env."
  echo "  Set it as an environment variable, or put it in ~/.config/automation/secrets.env (CAPSOLVER_API_KEY=...)."
fi
