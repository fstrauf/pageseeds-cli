# AI Constitution for PageSeeds CLI

Primary guide for AI agents working on the PageSeeds CLI project.

## Purpose

PageSeeds CLI is an **open-source automation toolkit** for:
- SEO research and content operations
- Reddit opportunity search and engagement workflows
- Deterministic utility automations with agent-assisted workflows

**Design goal:** Provide a complete, installable tool (`pageseeds`) that users can install via uv/pip and use to manage their website automation workflows.

## Architecture Snapshot

```
pageseeds-cli/
├── packages/
│   ├── automation-cli/     → Core automation commands (reddit, gsc, posthog)
│   ├── seo-cli/            → SEO research tools (ahrefs, keywords)
│   └── seo-content-cli/    → Content lifecycle operations
├── dashboard_ptk/          → Interactive TUI + orchestration engine
└── .github/skills/         → Workflow knowledge source of truth
```

**Command entry point:** `pageseeds` (unified CLI)

**Execution context:** Target repos under `.github/automation/`

## User Installation

Users install PageSeeds CLI in their workspace:

```bash
# Using uv (recommended)
uv tool install git+https://github.com/fstrauf/pageseeds-cli

# Or using pip
pip install git+https://github.com/fstrauf/pageseeds-cli
```

Then configure in their target website repos:
```bash
cd /path/to/website
git init  # if not already a git repo
pageseeds automation repo init --site-id my-site
```

## Two-Agent Operating Model

Use this model whenever two agents collaborate on work in this repo.

### Agent A: Planner/Architect

Responsibilities:
- Clarify objective, constraints, acceptance criteria
- Define interfaces and boundaries before edits
- Identify migration and rollback implications
- Produce decision-complete change plan

Must deliver:
- scope
- affected files/modules
- invariants to preserve
- test/verification plan

### Agent B: Implementer

Responsibilities:
- Execute against the plan
- Keep changes minimal and cohesive
- Preserve backward compatibility unless explicitly changing schema/contracts
- Validate behavior with tests/checks

Must deliver:
- working code
- updated docs
- verification results
- known limitations

### Handoff Contract

Before coding handoff, Agent A provides:
1. exact modules to create/modify
2. expected data contracts
3. success/failure behavior
4. test scenarios

After implementation handoff, Agent B provides:
1. what changed
2. what was verified
3. residual risks

## Core Rules

1. **Skills are source of truth.**
   - Workflow logic belongs in `.github/skills/*/SKILL.md`.
   - Prompts are launchers, not full workflow specs.

2. **Deterministic steps use CLIs.**
   - Prefer explicit `pageseeds automation seo ...`, `pageseeds reddit ...` calls.
   - Avoid shell parsing pipelines for core logic.

3. **Agentic steps must be observable.**
   - Persist raw agent output artifacts.
   - Normalize to structured artifacts deterministically.

4. **Secrets stay machine-local.**
   - Use env vars or `~/.config/pageseeds/secrets.env`.
   - Never embed keys in repo files.

5. **No mock data unless explicitly requested.**

6. **One content-dir resolver.**
   - Use `dashboard_ptk/dashboard/engine/content_locator.py` for content directory discovery.
   - Do not reimplement candidate path scans in UI/runners/utils.
   - Project `content_dir` override must take precedence when valid.

7. **No direct subprocess outside engine.**
   - `subprocess.run` is only allowed in `dashboard_ptk/dashboard/engine/*`.
   - UI (`dashboard/cli.py`) and task runners must call engine services/tool registry instead.

8. **Date edits must be frontmatter-safe.**
   - For markdown date fixes, update YAML frontmatter deterministically first, then sync task metadata/JSON.
   - Do not use broad regex replacements that can modify body content.

## Where to Change Things

- Dashboard orchestration: `dashboard_ptk/dashboard/engine/`
- Dashboard UI shell: `dashboard_ptk/dashboard/cli.py`, `dashboard_ptk/dashboard/batch.py`
- Task runners: `dashboard_ptk/dashboard/tasks/`
- Task persistence/schema migration: `dashboard_ptk/dashboard/storage/`, `dashboard_ptk/dashboard/engine/task_store.py`, `dashboard_ptk/dashboard/engine/migration.py`
- CLI implementations: `packages/*/src/`
- Workflow knowledge: `.github/skills/`

## Adding Functionality (Standard Path)

1. Define capability and acceptance criteria.
2. Decide deterministic vs agentic split.
3. Add/extend deterministic CLI command first (if needed).
4. Wire orchestration in dashboard engine workflows.
5. Add/update task schema mappings only when required.
6. Add tests for:
   - migration/compatibility (if schema touched)
   - deterministic execution path
   - normalization behavior (if agent output used)
7. Update docs in place (`AGENTS.MD`, `ARCHITECTURE.md`, dashboard guide).

## Changing Existing Behavior Safely

1. Preserve task state compatibility by default.
2. If schema changes, provide migration + backup + rollback behavior.
3. Keep UI behavior stable unless change is intentional.
4. Do not introduce parallel/duplicate runtime paths.
   - one canonical execution path through `dashboard/engine`
5. If project setup/validation behavior changes, update preflight checks and interactive fix paths together.

## Pre-Commit Checklist

- No secrets added
- No hardcoded absolute machine paths in runtime logic
- Deterministic calls go through centralized tool execution
- Agent outputs are persisted and normalized when structured results are required
- Docs updated in existing files (no duplicate guidance)
- Tests executed and reported
- `test_no_subprocess_outside_engine.py` passes
- If content directory logic changed: `test_content_locator.py` and `test_project_preflight.py` updated/passing
- If date-fix logic changed: `test_frontmatter_dates.py` (and affected workflow tests) updated/passing
