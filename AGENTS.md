# Zrzavy Energy Monitor agent instructions

## Mission

Develop Zrzavy Energy Monitor incrementally according to the approved roadmap.
Prefer small, reviewable, backward-compatible changes. Preserve measurement,
validation, persistence, source-selection, and energy-integration semantics
unless the task explicitly changes them.

## Repository map

- Application code: `app/`
- Canonical core modules: `app/zrzavy_energy_monitor_core/`
- Canonical entry point: `app/zrzavy_energy_monitor.py`
- Temporary 4.5 compatibility: `app/solarinspector.py` and
  `app/solarinspector_core/`
- Tests: `tests/`
- Documentation: `docs/`
- Development plans and reports: `docs/development/`
- Release history: `CHANGELOG.md`
- Canonical local verification: `./scripts/verify.sh`
- Local Python environment: `.venv/` (never commit it)

Read a more specific nested `AGENTS.md` if one is added below the repository
root in the future.

## Mandatory workflow

1. Read the task, relevant roadmap material, existing documentation, tests,
   and implementation before changing files.
2. Inspect the current branch, worktree, and recent commits.
3. Work on a dedicated feature branch or Codex worktree. Never develop
   directly on `main`.
4. State the smallest coherent implementation that satisfies the task.
5. Implement only the defined scope.
6. Add or update tests for every changed behavior.
7. Run focused tests while iterating.
8. Run `./scripts/verify.sh` before declaring the task complete.
9. Fix failures autonomously and rerun the affected check followed by the
   complete verification.
10. Update documentation and `CHANGELOG.md` when public behavior changes.
11. Review `git diff`, `git diff --check`, and `git status --short` for
    unintended or generated files.
12. Create an atomic commit only when explicitly requested or when the task
    explicitly includes delivery by commit.
13. Push and open a draft pull request only when explicitly requested.

## Definition of done

A development task is complete only when:

- all acceptance criteria are implemented;
- all existing and new automated checks pass;
- public behavior and configuration are documented;
- backward compatibility and measurement semantics were evaluated;
- no secrets, generated files, virtual environments, databases, or local
  configuration are tracked;
- the final diff contains only task-related changes;
- unresolved risks, limitations, and hardware checks are reported honestly.

## Autonomous decisions

Do not ask the user about implementation details that can be resolved from
existing code, tests, documentation, established conventions, or the smallest
backward-compatible implementation.

Make reasonable technical decisions within scope and record non-obvious
decisions in documentation or the draft pull request.

## Stop and ask only when

Request a decision when:

- acceptance criteria contradict each other;
- measurement, validation, source-selection, persistence, or energy-balance
  semantics would materially change without an explicit requirement;
- a destructive or irreversible database migration is required;
- a new production dependency is necessary;
- credentials, private network access, real devices, or external accounts are
  required;
- a requested hardware result cannot be reproduced or verified;
- work outside the defined scope is required;
- the same blocking failure remains after three materially different attempts.

When blocked, report the exact blocker, attempts already made, available
options, the recommended option, and the consequences of each option.

## Safety boundaries

- Never merge into `main`.
- Never enable auto-merge.
- Never force-push.
- Never create or publish a release unless the user explicitly requests it in
  a dedicated release task.
- Never delete branches, tags, releases, databases, configuration, or user
  data.
- Never copy or commit productive secrets, private addresses, real
  configuration files, or customer data.
- Never access a production Zrzavy Energy Monitor installation.
- Never change database schemas unless explicitly required.
- Never suppress or weaken a failing test to make verification pass.
- Never modify unrelated code merely to satisfy a check.
- Hardware tests and deployment checks are manual unless the task explicitly
  provides a safe test environment.

## Code quality

- Follow `docs/development.md` and `pyproject.toml`.
- Use Python 3.11-compatible syntax unless supported versions change.
- Use PEP 8, Google-style PEP 257 docstrings, and consistent type annotations
  for new or substantially changed code.
- Keep modules and functions focused.
- Prefer explicit, readable implementations over clever shortcuts.
- Preserve separation between adapters, normalized models, validation,
  persistence, source selection, energy integration, and web presentation.
- Comments explain intent and non-obvious constraints, not obvious syntax.

## Testing

`./scripts/verify.sh` is the canonical local completion check. It mirrors the
repository's required format, lint, type, compile, and test checks. Tests must
not require productive secrets, real hardware, or external services.

If a test fails:

1. identify whether implementation, test, environment, or requirement is
   responsible;
2. fix the root cause;
3. rerun the focused check;
4. rerun `./scripts/verify.sh` before completion.

Skipped hardware tests must be reported as skipped, never as passed.

## Historical Phase 09 pilot

Only when working on the historical Phase 09 scope, read
`docs/development/4.5/phase-09-pilot.md` before planning or implementation.
Its decision gates and out-of-scope section remain binding for that work, but
are not general instructions for later development.
