#!/bin/bash
# Setup script for the dashboard when packaged
set -e

echo "=== Automation Toolkit Setup ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check Python
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Python version: $PYTHON_VERSION"

# Check pip
PIP_CMD=""
if command -v pip3 &> /dev/null; then
    PIP_CMD="pip3"
elif command -v pip &> /dev/null; then
    PIP_CMD="pip"
else
    print_error "pip is required but not installed."
    exit 1
fi
print_success "pip found: $PIP_CMD"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_ROOT="$(dirname "$SCRIPT_DIR")"

echo ""
echo "Package root: $PACKAGE_ROOT"
echo ""

# Install CLI packages
echo "Installing CLI packages..."
echo "  - automation-cli package"
$PIP_CMD install -q -e "$PACKAGE_ROOT/packages/automation-cli"
print_success "automation-cli package installed"

echo "  - seo-cli package"
$PIP_CMD install -q -e "$PACKAGE_ROOT/packages/seo-cli"
print_success "seo-cli package installed"

echo "  - seo-content-cli package"
$PIP_CMD install -q -e "$PACKAGE_ROOT/packages/seo-content-cli"
print_success "seo-content-cli package installed"

# Install dashboard
echo ""
echo "Installing dashboard..."
$PIP_CMD install -q -e "$PACKAGE_ROOT/dashboard_ptk"
print_success "dashboard installed"

# Create config directory
echo ""
echo "Setting up configuration..."
CONFIG_DIR="$HOME/.config/automation"
mkdir -p "$CONFIG_DIR"
print_success "Config directory: $CONFIG_DIR"

# Create projects.json if not exists
if [ ! -f "$CONFIG_DIR/projects.json" ]; then
    cat > "$CONFIG_DIR/projects.json" << 'EOF'
{
  "projects": []
}
EOF
    print_success "Created: projects.json"
    print_info "Edit this file to add your projects: $CONFIG_DIR/projects.json"
else
    print_warning "Already exists: projects.json"
fi

# Create secrets.env template if not exists
if [ ! -f "$CONFIG_DIR/secrets.env" ]; then
    cat > "$CONFIG_DIR/secrets.env" << 'EOF'
# ============================================================
# Automation Toolkit Secrets
# ============================================================
# Add your API keys here. This file should NOT be committed to git.

# Google Search Console
# Get service account key from: https://console.cloud.google.com/
# GSC_SERVICE_ACCOUNT_PATH=/path/to/service-account-key.json

# SEO Tools
# Get from: https://www.capsolver.com/
# CAPSOLVER_API_KEY=your_key_here

# PostHog
# Get from your PostHog project settings
# POSTHOG_API_KEY=your_key_here

# Reddit API
# Create an app at: https://www.reddit.com/prefs/apps
# REDDIT_CLIENT_ID=your_client_id
# REDDIT_CLIENT_SECRET=your_client_secret
EOF
    print_success "Created: secrets.env"
    print_info "Add your API keys to: $CONFIG_DIR/secrets.env"
else
    print_warning "Already exists: secrets.env"
fi

# Check for kimi-code
echo ""
if command -v kimi &> /dev/null; then
    print_success "kimi-code CLI found"
else
    print_warning "kimi-code CLI not found"
    echo ""
    echo "  The dashboard requires kimi-code for AI-powered tasks."
    echo "  Install it from: https://github.com/moonshot-ai/kimi-code"
    echo ""
fi

# Verify installation
echo ""
echo "Verifying installation..."
ALL_GOOD=true

if command -v task-dashboard &> /dev/null; then
    print_success "task-dashboard command available"
else
    print_error "task-dashboard command not found"
    print_info "You may need to restart your shell or add pip's bin dir to PATH"
    ALL_GOOD=false
fi

for cmd in automation-cli seo-cli seo-content-cli; do
    if command -v $cmd &> /dev/null; then
        print_success "$cmd command available"
    else
        print_error "$cmd command not found"
        ALL_GOOD=false
    fi
done

echo ""
echo "=========================================="
if [ "$ALL_GOOD" = true ]; then
    print_success "Installation complete!"
    echo ""
    echo "Next steps:"
    echo "  1. Add your projects to: $CONFIG_DIR/projects.json"
    echo "  2. Add your API keys to: $CONFIG_DIR/secrets.env"
    echo "  3. Run: task-dashboard"
else
    print_warning "Installation incomplete"
    echo ""
    echo "Some commands were not found. Try:"
    echo "  1. Restart your shell"
    echo "  2. Or run: source ~/.bashrc (or ~/.zshrc)"
    echo "  3. Then verify with: task-dashboard --version"
fi
echo "=========================================="
