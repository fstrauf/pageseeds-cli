#!/bin/bash
# Campaign Dashboard using python-prompt-toolkit

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

# Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt 2>/dev/null
if ! pip install -q -e "$REPO_ROOT/packages/automation-cli" -e "$REPO_ROOT/packages/seo-cli" -e "$REPO_ROOT/packages/seo-content-cli" 2>/dev/null; then
    echo "Warning: Could not install local CLI package dependencies; continuing with source-only mode."
fi

# Ensure local CLI package modules are importable without needing network installs.
export PYTHONPATH="$REPO_ROOT/packages/automation-cli/src:$REPO_ROOT/packages/seo-cli/src:$REPO_ROOT/packages/seo-content-cli/src:${PYTHONPATH:-}"

# Ensure venv-local wrappers exist so dashboard subprocess calls resolve consistently.
if [ ! -x ".venv/bin/automation-cli" ]; then
cat > ".venv/bin/automation-cli" <<'EOF'
#!/usr/bin/env python3
import sys
from automation_mcp.cli import main
if __name__ == "__main__":
    sys.exit(main())
EOF
chmod +x ".venv/bin/automation-cli"
fi

if [ ! -x ".venv/bin/seo-cli" ]; then
cat > ".venv/bin/seo-cli" <<'EOF'
#!/usr/bin/env python3
import sys
from seo_mcp.cli import main
if __name__ == "__main__":
    sys.exit(main())
EOF
chmod +x ".venv/bin/seo-cli"
fi

if [ ! -x ".venv/bin/seo-content-cli" ]; then
cat > ".venv/bin/seo-content-cli" <<'EOF'
#!/usr/bin/env python3
import sys
from seo_content_mcp.cli import main
if __name__ == "__main__":
    sys.exit(main())
EOF
chmod +x ".venv/bin/seo-content-cli"
fi

if [ -x ".venv/bin/pageseeds" ]; then
    exec ".venv/bin/pageseeds" "$@"
fi

if [ -x ".venv/bin/task-dashboard" ]; then
    exec ".venv/bin/task-dashboard" "$@"
fi

python main.py "$@"
