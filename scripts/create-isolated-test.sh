#!/bin/bash
#
# Create an isolated test environment for the packaged dashboard
# This allows dogfooding without breaking your main setup
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_success() { echo -e "${GREEN}✓${NC} $1"; }
print_info() { echo -e "${BLUE}ℹ${NC} $1"; }
print_warning() { echo -e "${YELLOW}⚠${NC} $1"; }
print_error() { echo -e "${RED}✗${NC} $1"; }

# Configuration
TEST_ROOT="${TEST_ROOT:-/tmp/automation-pkg-test}"
SOURCE_REPO="${SOURCE_REPO:-$(cd "$(dirname "$0")/.." && pwd)}"

echo "=========================================="
echo "Creating Isolated Test Environment"
echo "=========================================="
echo ""
echo "Test root: $TEST_ROOT"
echo "Source: $SOURCE_REPO"
echo ""

# Step 1: Clean up any previous test environment
if [ -d "$TEST_ROOT" ]; then
    print_warning "Previous test environment found"
    read -p "Remove and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$TEST_ROOT"
        print_success "Removed old test environment"
    else
        print_info "Keeping existing environment"
        exit 0
    fi
fi

# Step 2: Create directory structure
print_info "Creating directory structure..."
mkdir -p "$TEST_ROOT"/{venv,config/automation,test-repos}
print_success "Directories created"

# Step 3: Create virtual environment
print_info "Creating virtual environment..."
cd "$TEST_ROOT"
python3 -m venv venv
print_success "Virtual environment created"

# Step 4: Copy source code
print_info "Copying source code..."
cp -r "$SOURCE_REPO" "$TEST_ROOT/automation-toolkit"
print_success "Source copied to $TEST_ROOT/automation-toolkit"

# Step 5: Create package files
print_info "Setting up package structure..."
cd "$TEST_ROOT/automation-toolkit"

# Create pyproject.toml
cat > pyproject.toml << 'EOF'
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "automation-toolkit"
version = "1.0.0-alpha.1"
description = "SEO automation toolkit with multi-agent support"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "prompt-toolkit>=3.0.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
api = ["openai>=1.0.0", "anthropic>=0.18.0"]
dev = ["pytest>=7.0.0", "black>=23.0.0", "ruff>=0.1.0"]

[project.scripts]
task-dashboard = "dashboard:main"

[project.urls]
Homepage = "https://github.com/yourusername/automation-toolkit"
Repository = "https://github.com/yourusername/automation-toolkit"

[tool.setuptools]
packages = ["dashboard"]
package-dir = {"dashboard" = "dashboard_ptk/dashboard"}

[tool.black]
line-length = 100

[tool.ruff]
line-length = 100
EOF

# Create setup script
cat > setup.sh << 'EOF'
#!/bin/bash
# Setup script for automation-toolkit
set -e

echo "Installing automation-toolkit and dependencies..."

# Install MCP packages
pip install -q -e packages/automation-cli
pip install -q -e packages/seo-cli  
pip install -q -e packages/seo-content-cli

# Install dashboard
pip install -q -e .

echo "Installation complete!"
echo ""
echo "Available commands:"
echo "  task-dashboard     - Run the TUI dashboard"
echo "  automation-cli     - General automation CLI"
echo "  seo-cli            - SEO research CLI"
echo "  seo-content-cli    - Content management CLI"
EOF
chmod +x setup.sh

print_success "Package files created"

# Step 6: Install everything
print_info "Installing package (this may take a minute)..."
source "$TEST_ROOT/venv/bin/activate"
./setup.sh
print_success "Package installed"

# Step 7: Create test configuration
print_info "Creating test configuration..."

# Projects config
cat > "$TEST_ROOT/config/automation/projects.json" << EOF
{
  "projects": [],
  "_comment": "Add your test projects here"
}
EOF

# Agent config
cat > "$TEST_ROOT/config/automation/agent.conf" << 'EOF'
# Agent Configuration
# Options: copilot, claude, kimi, opencode, aider, openai, anthropic
AGENT_PROVIDER=kimi
TIMEOUT=600
EOF

# Secrets (symlink to real secrets)
if [ -f "$HOME/.config/automation/secrets.env" ]; then
    ln -s "$HOME/.config/automation/secrets.env" "$TEST_ROOT/config/automation/secrets.env"
    print_success "Linked secrets from main config"
else
    touch "$TEST_ROOT/config/automation/secrets.env"
    print_warning "No secrets found - create $TEST_ROOT/config/automation/secrets.env"
fi

# Step 8: Create launcher script
cat > "$TEST_ROOT/run-dashboard" << EOF
#!/bin/bash
# Run dashboard with isolated config
source "$TEST_ROOT/venv/bin/activate"

# Use isolated config
export AUTOMATION_CONFIG_DIR="$TEST_ROOT/config/automation"

# Run dashboard
task-dashboard "\$@"
EOF
chmod +x "$TEST_ROOT/run-dashboard"

# Step 9: Create helper scripts
cat > "$TEST_ROOT/switch-to-kimi" << 'EOF'
#!/bin/bash
echo "AGENT_PROVIDER=kimi" > config/automation/agent.conf
echo "Switched to Kimi"
EOF
chmod +x "$TEST_ROOT/switch-to-kimi"

cat > "$TEST_ROOT/switch-to-claude" << 'EOF'
#!/bin/bash
echo "AGENT_PROVIDER=claude" > config/automation/agent.conf
echo "Switched to Claude"
EOF
chmod +x "$TEST_ROOT/switch-to-claude"

cat > "$TEST_ROOT/switch-to-copilot" << 'EOF'
#!/bin/bash
echo "AGENT_PROVIDER=copilot" > config/automation/agent.conf
echo "Switched to Copilot"
EOF
chmod +x "$TEST_ROOT/switch-to-copilot"

# Step 10: Create test project
cd "$TEST_ROOT"
mkdir -p test-repos/demo-site
cd test-repos/demo-site
git init 2>/dev/null || true

mkdir -p .github/automation
mkdir -p content

cat > .github/automation/manifest.json << 'EOF'
{
  "website": "demo",
  "url": "https://demo.example.com",
  "gsc_site": "sc-domain:demo.example.com",
  "sitemap": "https://demo.example.com/sitemap.xml"
}
EOF

cat > .github/automation/articles.json << 'EOF'
{
  "nextArticleId": 1,
  "articles": []
}
EOF

mkdir -p .github/skills/hello-world
cat > .github/skills/hello-world/SKILL.md << 'EOF'
# Hello World Skill

## Purpose
Test that the agent interface is working.

## Instructions
1. Read the context data
2. Say hello
3. Confirm you can see the test data

## Expected Output
A friendly greeting that references the test data.
EOF

# Add demo project to config
cat > "$TEST_ROOT/config/automation/projects.json" << EOF
{
  "projects": [
    {
      "name": "Demo Site",
      "website_id": "demo",
      "repo_root": "$TEST_ROOT/test-repos/demo-site"
    }
  ]
}
EOF

print_success "Test project created"

# Step 11: Create README
cat > "$TEST_ROOT/README.md" << 'EOF'
# Isolated Test Environment

This is an isolated test environment for the packaged automation toolkit.

## Quick Start

```bash
# Run the dashboard
./run-dashboard

# Switch agents
./switch-to-kimi
./switch-to-claude
./switch-to-copilot

# Edit config
nano config/automation/agent.conf
nano config/automation/projects.json
```

## Directory Structure

```
.
├── venv/                      # Isolated Python environment
├── automation-toolkit/        # Source code
├── config/automation/         # Isolated config
│   ├── agent.conf            # Agent selection
│   ├── projects.json         # Project list
│   └── secrets.env           # API keys (symlinked)
├── test-repos/               # Test projects
│   └── demo-site/           # Demo project
├── run-dashboard            # Launcher script
└── switch-to-*              # Agent switchers
```

## Testing Different Agents

```bash
# Test with Kimi
./switch-to-kimi
./run-dashboard

# Test with Claude
./switch-to-claude
./run-dashboard

# Test with Copilot
./switch-to-copilot
./run-dashboard

# Test with OpenAI
echo "AGENT_PROVIDER=openai" > config/automation/agent.conf
echo "OPENAI_API_KEY=sk-..." >> config/automation/agent.conf
./run-dashboard
```

## Making Changes

Edit files in `automation-toolkit/` then reinstall:

```bash
cd automation-toolkit
pip install -e .
```

## Syncing Back

To sync changes back to main repo:

```bash
cd automation-toolkit
git diff HEAD > /tmp/my-changes.patch

cd "$SOURCE_REPO"
git apply /tmp/my-changes.patch
```
EOF

# Step 12: Verify installation
print_info "Verifying installation..."
source "$TEST_ROOT/venv/bin/activate"

# Check CLIs
for cmd in task-dashboard pageseeds; do
    if which $cmd > /dev/null 2>&1; then
        print_success "$cmd available"
    else
        print_error "$cmd not found"
    fi
done

# Check imports
if python -c "from dashboard import Dashboard; from dashboard.core.agent_config import AgentConfig; print('OK')" 2>/dev/null; then
    print_success "Dashboard imports work"
else
    print_warning "Some imports may need attention"
fi

echo ""
echo "=========================================="
echo "Isolated Test Environment Ready!"
echo "=========================================="
echo ""
echo "Location: $TEST_ROOT"
echo ""
echo "Quick commands:"
echo "  cd $TEST_ROOT"
echo "  ./run-dashboard              # Start dashboard"
echo "  ./switch-to-kimi             # Use Kimi agent"
echo "  ./switch-to-claude           # Use Claude agent"
echo ""
echo "Files to edit:"
echo "  config/automation/agent.conf     # Choose your agent"
echo "  config/automation/projects.json  # Add your repos"
echo ""
echo "Test project ready at:"
echo "  test-repos/demo-site/"
echo ""
echo "See README.md for more details."
