# PageSeeds CLI

A CLI-first automation workspace for SEO research, content operations, and Reddit engagement workflows.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## What is PageSeeds?

PageSeeds is a modular automation system that helps you:

- **Research keywords** using Ahrefs data (via CapSolver)
- **Manage content lifecycles** across multiple websites
- **Orchestrate tasks** through an interactive TUI dashboard
- **Engage with Reddit** opportunities programmatically
- **Sync SEO workflows** between automation and production repos

## Quick Start

### Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** - Python package manager
- **CapSolver API key** - for Ahrefs SEO data ([get one here](https://dashboard.capsolver.com/passport/register?inviteCode=1dTH7WQSfHD0))

### 1. Clone and Install

```bash
git clone <your-repo-url> pageseeds-cli
cd pageseeds-cli

# Install all CLI tools
./scripts/install_uv_tools.sh --update-shell

# Reload your shell or restart terminal
```

### 2. Configure Secrets

Create your secrets file:

```bash
mkdir -p ~/.config/automation
cat > ~/.config/automation/secrets.env << 'EOF'
CAPSOLVER_API_KEY=your-capsolver-api-key-here
EOF
```

### 3. Launch

```bash
pageseeds
```

## Development Workflow (Always Run Latest Local Code)

Use an editable local install plus PATH precedence so each code change in this repo is immediately used by the pageseeds command.

### 1. Install editable local CLI

```bash
cd /Users/fstrauf/01_code/pageseeds-cli
./scripts/install_uv_tools.sh --update-shell
```

### 2. Ensure uv tool bin is first on PATH

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
exec zsh
```

### 3. Verify active binary and import path

```bash
which -a pageseeds
pageseeds version
~/.local/share/uv/tools/pageseeds-cli/bin/python -c "import dashboard; print(dashboard.__file__)"
```

Expected result: dashboard import path points to this repo under dashboard_ptk/dashboard.

### 4. Daily development loop

```bash
cd /Users/fstrauf/01_code/pageseeds-cli
# edit code
pageseeds
```

No reinstall is required for normal Python source changes when using the editable install.

## What Gets Installed?

The install script adds a single `pageseeds` command to your PATH that provides:

| Subcommand | Purpose |
|------------|---------|
| `pageseeds` (no args) | Interactive task dashboard |
| `pageseeds version` | Check version and available updates |
| `pageseeds seo` | SEO research tools (keywords, backlinks, traffic) |
| `pageseeds content` | Content lifecycle management |
| `pageseeds automation` | Repo sync, workflow management |
| `pageseeds reddit` | Reddit opportunity management |
| `pageseeds geo` | Geo/place enrichment |

## Version Check

Check if PageSeeds is up to date:

```bash
pageseeds version        # Check main CLI version
pageseeds version --all  # Check all component versions
```

### Private Repositories

If your repository is private, set a GitHub token to enable version checking:

```bash
export GITHUB_TOKEN=your-github-token-here
# or
export GH_TOKEN=your-github-token-here
```

Then run the version check as normal.

## Configuration

### Project Registry

Create `~/.config/automation/projects.json` to define your websites:

```json
{
  "projects": {
    "my_site": {
      "name": "My Website",
      "path": "/path/to/your/website/repo",
      "content_dir": "content/blog"
    }
  }
}
```

### Target Repo Setup

Each target repository needs an automation workspace. Bootstrap it:

```bash
pageseeds automation repo init --to /path/to/target/repo
```

This creates `.github/automation/` with:
- `task_list.json` - your task queue
- `artifacts/` - workflow outputs
- `skills/` - reusable workflow knowledge

## Example Workflows

### SEO Keyword Research

```bash
# Generate keyword ideas
pageseeds seo keywords --keyword "expense tracking" --country us

# Check keyword difficulty
pageseeds seo difficulty --keyword "best expense tracker" --country us

# Get backlinks for a domain
pageseeds seo backlinks --domain example.com

# Get traffic estimates
pageseeds seo traffic --domain-or-url example.com
```

### Content Operations

```bash
# Validate content for issues
pageseeds content validate --website-path general/my_site

# Clean content (fix dates, remove duplicate headings)
pageseeds content clean --website-path general/my_site

# Analyze content dates
pageseeds content analyze-dates --website-path general/my_site

# View articles summary
pageseeds content articles-summary --workspace-root /path/to/workspace
```

### Reddit Engagement

```bash
# List pending opportunities
pageseeds reddit pending --project my_project

# List posted opportunities (last 30 days)
pageseeds reddit posted --project my_project

# View project stats
pageseeds reddit stats --project my_project
```

### Dashboard Tasks

The `pageseeds` dashboard provides:

- **Task Management** - Create, edit, and track SEO/content tasks
- **Orchestration** - Run automated workflows on ready tasks
- **Scheduler** - Automated task creation and monitoring
- **Multi-project** - Switch between different websites

## Project Structure

```
pageseeds-cli/
├── dashboard_ptk/          # Unified CLI + Interactive TUI dashboard
├── packages/
│   ├── automation-cli/     # Library: Repo management, Reddit, geo
│   ├── seo-cli/            # Library: Ahrefs SEO research
│   └── seo-content-cli/    # Library: Content lifecycle management
├── scripts/                # Setup and utility scripts
└── .github/skills/         # Workflow knowledge base
```

The `pageseeds` command is a unified CLI that includes all functionality. The packages under `packages/` are installed as libraries that `pageseeds` imports.

## Development

Run commands in development mode (without installing):

```bash
# SEO CLI
uv run --directory packages/seo-cli seo-cli --help

# Content CLI
uv run --directory packages/seo-content-cli seo-content-cli --help

# Automation CLI
uv run --directory packages/automation-cli automation-cli --help

# Dashboard
uv run --directory dashboard_ptk python -m dashboard
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `uv: command not found` | Install uv: `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| `CAPSOLVER_API_KEY not found` | Add to `~/.config/automation/secrets.env` |
| `pageseeds: command not found` | Run `./scripts/install_uv_tools.sh --update-shell` and restart terminal |
| No projects showing in dashboard | Create `~/.config/automation/projects.json` |

## Architecture

PageSeeds follows a two-repo model:

- **This repo** - CLI tools, dashboard, and orchestration logic
- **Target repos** - Your actual websites with content and per-project config under `.github/automation/`

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design docs.

## License

MIT
