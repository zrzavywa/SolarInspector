# Phase 09 agent-development pilot

## Status

This document prepares Phase 09 as the first agent-assisted development pilot.
It is a bounded work package, not approval to implement Phase 09 before its
acceptance criteria have been reviewed.

## Objective

Design and implement the whole-site energy-balance and source-selection work
deferred from Phase 08, using normalized, validated measurements and their
quality metadata as the only source-selection inputs.

## Candidate scope from completed Phase 08

- complete whole-site energy-balance model;
- final source-priority and fallback policy;
- balance-specific contradiction rules;
- use of validation quality in source scoring;
- explicit treatment of overlapping measurement positions;
- review the Phase 06 findings assigned to Phase 09.

Each item must be converted into explicit acceptance criteria before
implementation. If the items are too large for one reviewable pull request,
split them into numbered Phase 09 work packages.

## Required analysis before implementation

1. Inventory every normalized measurement position that may enter the balance.
2. Document units, sign conventions, timestamps, freshness limits, and quality
   states.
3. Define the balance equations with worked examples.
4. Identify overlapping or alternative sources and document when each is
   eligible.
5. Define deterministic priority, scoring, and fallback behavior.
6. Define behavior for missing, stale, rejected, warning-classified, or
   contradictory values.
7. Confirm whether persistence or public API changes are required.
8. Turn the approved behavior into testable acceptance criteria.

## Initial acceptance criteria for the analysis work package

- The existing Phase 08 behavior remains unchanged.
- No unvalidated measurement enters source selection.
- Units and sign conventions are explicit for every balance term.
- Source selection is deterministic and explainable.
- Missing or invalid inputs produce an explicit result; values are not silently
  invented.
- Overlapping measurement positions cannot be double-counted.
- Warning-quality handling is specified separately from rejected input.
- Normal, boundary, missing-data, stale-data, contradiction, and fallback
  scenarios are represented as test cases.
- Database, API, configuration, and migration impacts are documented before
  implementation.
- The complete `./scripts/verify.sh` check remains green.

## Out of scope without separate approval

- automatic changes to productive thresholds or configuration;
- access to a real SolarInspector installation or private device network;
- productive secrets or copied Office-computer configuration;
- destructive or irreversible database migration;
- new production dependencies;
- dashboard redesign unrelated to balance explainability;
- updater or release-process changes;
- automatic merge, release, deployment, or hardware control.

## Decision gates

Stop for Walter's decision before implementation if:

- competing balance equations or sign conventions are plausible;
- source priority changes existing measurement or energy semantics;
- warning-quality measurements could either be accepted or excluded;
- persistence requires a schema migration;
- the public configuration or API needs a breaking change;
- real installation data or hardware is required to establish correctness.

## Pilot delivery

The first Phase 09 task should be performed in a Codex worktree or dedicated
`feature/4.5-09-*` branch. Codex may analyze, implement, test, document, and
prepare an atomic commit. Push and draft pull request creation require an
explicit user request. Walter reviews and merges manually.

The draft pull request must state:

- problem and approved scope;
- implemented behavior and important design decisions;
- balance equations, units, and sign conventions;
- source priority and fallback behavior;
- tests and `./scripts/verify.sh` result;
- compatibility, migration, and hardware implications;
- unresolved risks and deliberately deferred work.
