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

## What Gets Installed?

The install script adds these commands to your PATH:

| Command | Purpose |
|---------|---------|
| `pageseeds` | Interactive task dashboard (main entrypoint) |
| `seo-cli` | SEO research tools (keywords, traffic, backlinks) |
| `seo-content-cli` | Content lifecycle management |
| `automation-cli` | Repo sync, Reddit tools, geo lookup |

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
automation-cli repo init --to /path/to/target/repo
```

This creates `.github/automation/` with:
- `task_list.json` - your task queue
- `artifacts/` - workflow outputs
- `skills/` - reusable workflow knowledge

## Example Workflows

### SEO Keyword Research

```bash
# Generate keyword ideas
seo-cli keyword-generator --keyword "expense tracking" --country us

# Check keyword difficulty
seo-cli keyword-difficulty --keyword "best expense tracker" --country us

# Get traffic estimates
seo-cli traffic --domain example.com
```

### Content Operations

```bash
# Validate content for issues
seo-content-cli validate-content --website-path general/my_site

# Clean content (fix dates, remove duplicate headings)
seo-content-cli clean-content --website-path general/my_site

# View articles summary
seo-content-cli articles-summary --website-path general/my_site
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
├── packages/
│   ├── automation-cli/     # Repo management, Reddit, geo tools
│   ├── seo-cli/            # Ahrefs SEO research
│   └── seo-content-cli/    # Content lifecycle management
├── dashboard_ptk/          # Interactive TUI dashboard
├── scripts/                # Setup and utility scripts
└── .github/skills/         # Workflow knowledge base
```

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
