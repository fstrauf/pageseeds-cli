# AI Constitution for Automation Repository

Primary guide for AI agents working in this repository.

## Purpose
This repository is a CLI-first automation workspace for:
- SEO research and content operations
- Reddit opportunity search and engagement workflows
- Small deterministic + agent-assisted automations

Design goal: one maintainable system where deterministic tool calls and agent interpretation are clearly separated.

## Architecture Snapshot
- `packages/automation-cli` -> `automation-cli`
- `packages/seo-cli` -> `seo-cli`
- `packages/seo-content-cli` -> `seo-content-cli`
- `dashboard_ptk` -> task dashboard TUI + orchestration engine
- `.github/skills` -> workflow knowledge source of truth

Execution context is in target repos under `.github/automation/`.

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
1. Skills are source of truth.
- Workflow logic belongs in `.github/skills/*/SKILL.md`.
- Prompts are launchers, not full workflow specs.

2. Deterministic steps use CLIs.
- Prefer explicit `automation-cli`, `seo-cli`, `seo-content-cli` calls.
- Avoid shell parsing pipelines for core logic.

3. Agentic steps must be observable.
- Persist raw agent output artifacts.
- Normalize to structured artifacts deterministically.

4. Secrets stay machine-local.
- Use env vars or `~/.config/automation/secrets.env`.
- Never embed keys in repo files.

5. No mock data unless explicitly requested.

6. One content-dir resolver.
- Use `dashboard_ptk/dashboard/engine/content_locator.py` for content directory discovery.
- Do not reimplement candidate path scans in UI/runners/utils.
- Project `content_dir` override must take precedence when valid.

7. No direct subprocess outside engine.
- `subprocess.run` is only allowed in `dashboard_ptk/dashboard/engine/*`.
- UI (`dashboard/cli.py`) and task runners must call engine services/tool registry instead.

8. Date edits must be frontmatter-safe.
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

## Legacy Task Migration

### Cleanup Legacy Custom Keyword Research Tasks

After the schema v4 refactor (commit 4b6502b), old `custom_keyword_research` tasks created before the refactor lack the required `custom_themes` metadata. These tasks will fail with:

```
✗ Task has no product/context configured. Add themes/criteria to task metadata.
```

**Migration tool:** `dashboard_ptk/migrate_cleanup_legacy_tasks.py`

```bash
# Check all projects for legacy tasks (dry run)
cd dashboard_ptk
python migrate_cleanup_legacy_tasks.py --dry-run

# Check specific project
python migrate_cleanup_legacy_tasks.py --project expense --dry-run

# Remove legacy tasks (creates backups)
python migrate_cleanup_legacy_tasks.py --apply

# Remove from specific project only
python migrate_cleanup_legacy_tasks.py --project expense --apply
```

The tool:
- Scans all projects for `custom_keyword_research` tasks without `custom_themes`
- Creates backups before modification (`task_list.backup_YYYYMMDD_HHMMSS.json`)
- Reports what was removed
- After cleanup, create new tasks via dashboard (option 'x' for Custom Keywords)

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
