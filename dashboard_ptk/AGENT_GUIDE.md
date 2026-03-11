# Dashboard Agent Guide

Practical guide for agents adding or changing dashboard functionality.

## What the Dashboard Is
The dashboard is a task UI on top of a backend engine.

- UI shell: menus, prompts, rendering
- Engine: task execution, tool calls, agent runtime, normalization, workflow routing

Rule: keep business/workflow logic in engine modules, not in UI menu code.

## Canonical Runtime Path
`cli.py / batch.py -> ExecutionEngine -> WorkflowHandler -> TaskRunner base -> ToolRegistry / AgentRuntime`

If you add behavior, fit it into this path. Do not introduce parallel execution paths.

## Where to Make Changes
- UI behavior only: `dashboard/cli.py`, `dashboard/cli_verification.py`, `dashboard/cli_articles.py`, `dashboard/cli_task_actions.py`, `dashboard/cli_projects.py`, `dashboard/batch.py`
- Execution routing: `dashboard/engine/executor.py`, `dashboard/engine/workflows/`
- Deterministic tool execution: `dashboard/engine/tool_registry.py`
- Project activation checks/init: `dashboard/engine/preflight.py`
- Orchestration loop/policy/ledger: `dashboard/engine/orchestrator.py`, `dashboard/engine/policy.py`, `dashboard/engine/ledger.py`, `dashboard/engine/reporter.py`
- Agent calls: `dashboard/engine/agent_runtime.py`
- Output normalization: `dashboard/engine/normalizers.py`
- Task schema/state: `dashboard/engine/types.py`, `dashboard/engine/task_store.py`, `dashboard/engine/migration.py`, `dashboard/storage/task_list.py`
- Scheduler cycle execution: `dashboard/engine/scheduler_service.py` (must use canonical runner registry, not ad-hoc runner wiring)
- Scheduler daemon setup/verification (macOS launchd): `dashboard/engine/scheduler_system_service.py`

## Adding a New Capability
1. Define task type and acceptance criteria.
2. Decide step split:
- deterministic tool step(s)
- optional agent step(s)
- optional normalization step
3. Add workflow handler support in `dashboard/engine/workflows/handlers.py`.
4. If deterministic command is new, route it through `ToolRegistry`.
5. If agent output must become structured data, add/update normalizer.
6. Add tests for the changed layer(s).
7. Update docs in place.

## Changing Existing Behavior
1. Preserve task compatibility unless schema change is intentional.
2. For schema change:
- update type contract
- add migration behavior
- keep backup/rollback semantics
3. Preserve user-facing menu flow unless explicitly changing UX.

## Two-Agent Collaboration Pattern
Use this when one agent plans and another implements.

### Planner agent should provide
- objective and constraints
- exact modules to change
- execution/contract decisions
- tests to add/run

### Implementer agent should provide
- concrete diffs
- verification results
- risks or follow-up items

## Guardrails
- No direct `subprocess.run` outside `dashboard/engine`.
- Do not hardcode machine-specific paths.
- Keep secrets out of repo files.
- Keep deterministic commands explicit and auditable.
- Keep normalized artifacts machine-readable.
- Use `dashboard/engine/env_resolver.py` for env/secrets lookup; do not duplicate env-file parsing in task runners.

## Verification
Minimum checks for non-trivial changes:
- `python -m py_compile` on touched dashboard modules
- `cd dashboard_ptk && python tests/run_tests.py`
- if scheduler behavior changed: run `python tests/test_scheduler_due_and_dedupe.py` and `python tests/test_scheduler_service_cycle.py`
- targeted task flow smoke check in dashboard if runtime behavior changed
