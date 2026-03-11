# PageSeeds Architecture

How the pieces fit together.

## Overview

PageSeeds is designed around separation of concerns:

- **Tools** (this repo) → CLI packages and dashboard
- **Data** (target repos) → Your websites and their automation state

```
┌─────────────────┐     ┌──────────────────┐
│  pageseeds-cli  │────▶│  Your Website    │
│   (tools)       │     │  (content +      │
│                 │     │   .github/auto/) │
└─────────────────┘     └──────────────────┘
```

## Components

### CLI Layer (`packages/`)

| Package | Purpose | Key Commands |
|---------|---------|--------------|
| `seo-cli` | Ahrefs SEO research | `keyword-generator`, `traffic`, `backlinks` |
| `seo-content-cli` | Content operations | `validate-content`, `clean-content`, `sync` |
| `automation-cli` | Repo & Reddit tools | `repo init`, `reddit-search`, `geo lookup` |

All CLIs are plain Python scripts - no long-running servers required.

### Dashboard (`dashboard_ptk/`)

Interactive TUI built with prompt-toolkit:

- **UI Shell** - Menu system, user input, display
- **Engine** - Workflow execution, tool registry, task management
- **Storage** - Task state, schema migrations

The dashboard runs workflows by calling the CLI packages directly.

### Skills (`.github/skills/`)

Workflow knowledge lives here. Each skill is a markdown file describing:

- When to use it
- What inputs/outputs to expect
- How to execute the workflow

Skills are copied to target repos during `automation-cli repo init`.

## Execution Model

### 1. Deterministic Path (preferred)

```
Dashboard → ToolRegistry → CLI Command → Output
```

Explicit, testable, fast.

### 2. Agentic Path (when needed)

```
Dashboard → AgentRuntime → Raw Output → Normalizer → Structured Artifact
```

Agent outputs are always saved raw, then normalized to structured formats.

## State Management

Target repos store their own state under `.github/automation/`:

```
.github/automation/
├── task_list.json          # Task queue (schema v4)
├── orchestrator_policy.json # Automation rules
├── scheduler_state.json     # Scheduler config
├── artifacts/               # Workflow outputs
└── task_results/           # Per-task execution results
```

This keeps automation state versioned with your content.

## Environment Resolution

Secrets and config are resolved in this order (highest wins):

1. Process environment (`os.environ`)
2. `~/.config/automation/secrets.env`
3. `{target_repo}/.env.local`
4. `{target_repo}/.env`
5. `{automation_repo}/.env`

## Content Discovery

When working with content, PageSeed searches for markdown files in this order:

1. `webapp/content/blog`
2. `src/blog/posts`
3. `src/content`
4. `content/blog`
5. `content`
6. `posts`
7. `blog`

First directory with `.md` or `.mdx` files wins.

## Adding Features

1. **New capability?** Add to the appropriate CLI package
2. **New workflow?** Add to `dashboard_ptk/dashboard/engine/workflows/`
3. **New tool?** Register in `dashboard_ptk/dashboard/engine/tool_registry.py`
4. **Schema change?** Add migration in `dashboard_ptk/dashboard/engine/migration.py`

## Design Principles

1. **One execution path** - All workflows go through `dashboard/engine`
2. **CLI-first** - Deterministic steps use explicit CLI calls
3. **Observable** - Agent outputs are always persisted
4. **Local secrets** - No keys in repo files
5. **Backward compatible** - Task state migrations preserve data

## For Contributors

### Testing

```bash
cd dashboard_ptk
python tests/run_tests.py
```

Key tests:
- `test_no_subprocess_outside_engine.py` - Ensures subprocess only in engine
- `test_content_locator.py` - Content directory discovery
- `test_frontmatter_dates.py` - Date handling safety

### Project Structure

```
dashboard_ptk/
├── dashboard/
│   ├── cli*.py          # UI layer (menus, display)
│   ├── batch.py         # Batch operations
│   └── engine/          # Core logic
│       ├── workflows/   # Task execution flows
│       ├── tool_registry.py
│       ├── task_store.py
│       └── migration.py
├── tests/
└── migrate_cleanup_legacy_tasks.py
```

See [AGENTS.md](AGENTS.md) for detailed agent guidelines.
