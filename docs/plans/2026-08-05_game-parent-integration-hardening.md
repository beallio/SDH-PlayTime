# Plan: Game Parent Integration Hardening (game-parent-integration-hardening)

## Context

The implemented identity, direct/Heroic resolver, presence, confirmation, checksum, and
UI units must agree on one canonical parent without security or packaging regressions.
Add cross-layer regression fences, production archive checks, support documentation,
and a precise deferred live Deck checklist. This final unit depends on the implemented
game-parent sub-plans being merged to `remix` and must not add a new feature surface.
Lutris, Bottles, and EmuDeck/SRM resolution remain explicitly out of scope.

**Slug used throughout this plan:** `game-parent-integration-hardening`

---

## Orchestration Contract

**Slug:** `game-parent-integration-hardening`

**Plan file:**

```text
docs/plans/2026-08-05_game-parent-integration-hardening.md
```

**Implementation branch:**

```text
feat/game-parent-integration-hardening
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/game-parent-integration-hardening_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/game-parent-integration-hardening_finalized
```

**Review notes:**

```text
docs/review/game-parent-integration-hardening-review-*.md
```

Each review note ends with exactly one status trailer:

```text
STATUS: CHANGES_REQUESTED
```

or:

```text
STATUS: APPROVED
```

---

## Required Agent Protocol

1. Use the **implementer** skill.
2. Work from the repository root.
3. Branch from `remix`.
4. Commit this plan as the first commit on the implementation branch.
5. Follow TDD where behavior changes are testable.
6. Run quality gates before marking any round complete.
7. Do not write your own review.
8. Do not create files under `docs/review/`.
9. Do not delete files under `docs/review/`.
10. Review notes are durable audit records and must be committed.
11. Resolving a review note means:
    - implement the requested changes;
    - run quality gates;
    - commit the code/docs changes;
    - commit the review note itself if it is not already committed;
    - recreate the round-complete marker.
12. After finalization, stop polling and exit cleanly.

---

## Scope discipline

- Implement only the units the plan lists. Do not modify files outside the plan's scope.
- Do not change runtime behavior beyond what the plan specifies. A `refactor` or
  `cleanup` commit must preserve observable behavior.
- Never edit a test's expected value to make a behavior change pass. If a test
  legitimately must change, that change must be required by the plan or a review
  note, and you must record the rationale in the session log.
- If you spot an unrelated improvement, do not make it here — note it in the
  session log for a separate plan.

---

## Setup

Start from `remix`:

```bash
git checkout remix
git pull --ff-only origin remix
git checkout -b feat/game-parent-integration-hardening
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_game-parent-integration-hardening.md
git commit -m "docs(plan): add game-parent-integration-hardening implementation plan"
```

---

## Implementation Tasks

1. Add cross-layer tests that drive grouped confirmation through the RPC boundary and
   verify the selected canonical ID across overall, daily, per-game, games dictionary,
   caches, checksum aliases, and Steam overview patch projections.
2. Cover the historic failure shapes end to end: explicit parent not equal to lexical
   checksum leader, child hidden beneath a third leader, representative child chosen
   first, multiple explicit parents joined by later checksum evidence, zero-time current
   parent, stale confirmation, and transactional rollback.
3. Add disconnect/reconnect scenarios for direct and Heroic fixtures. Verify a confirmed
   parent remains canonical, status changes without a DB write, and checksum generation
   stops while the payload is unavailable. Do not add Lutris, Bottles, or EmuDeck/SRM
   adapters or claim support for them.
4. Exercise release archive creation/validation in a clean extracted directory. Verify
   every shipped direct/Heroic resolver module and vendored dependency/license is
   present, no test fixtures or caches leak into production, and backend imports succeed
   without system PyYAML.
5. Add or update user documentation for the two independent status axes, recommendation
   and confirmation behavior, historical records, refresh, external drives, supported
   launcher variants, and why a shortcut is not proof of installation.
6. Add developer documentation with a fixture-backed direct/Heroic support matrix citing
   the verified upstream repository commits, safe-parser/no-execution guarantees,
   privacy/logging rules, deferred-adapter extension procedure, archive dependency update
   procedure, and focused test commands. Mark custom roots and unverified variants
   unknown rather than supported.
7. Audit all new code for unbounded scans, subprocess/shell/URL activation, unsafe YAML,
   arbitrary caller paths, leaked personal paths, first-match ambiguity, and implicit
   reparenting. Add a regression test for every corrected finding.
8. Run the complete repository quality gates from a clean tree and record focused red-to-
   green evidence in the commit/session history. Do not release, deploy, or modify a live
   Deck database in this plan.

---

## Quality Gates

Run before marking any round complete:

```bash
scripts/orchestration/run-quality-gates
scripts/orchestration/check-review-notes-not-deleted
git status --short
```

The round is not complete unless:

1. all requested implementation work is done;
2. all relevant tests pass;
3. build/typecheck gates pass;
4. review notes have not been deleted;
5. the working tree is clean;
6. all code/docs changes are committed.

---

## Verification

1. Run the full quality-gate script, review-note deletion check, release archive build and
   validator, and `git diff --check` from a clean branch.
2. Inspect one end-to-end test result per native Steam, direct shortcut, and Heroic path
   and verify parent, aliases, status, and checksum behavior agree. Confirm Lutris,
   Bottles, and EmuDeck/SRM remain unsupported and fail closed.
3. Verify unsupported or ambiguous launchers remain visible, reviewable, unhashed, and
   never automatically selected.
4. Review the final archive contents and dependency/license metadata manually.

Deferred live verification requires a Steam Deck with representative native, direct,
and Heroic shortcut installations plus an external drive. The handoff checklist must
cover gamepad navigation, long/duplicate labels, native install-state capability,
supported launcher variants, disconnect/reconnect, refresh, warning, confirmation,
reparent, detach, dissolve, and removal. Record exact launcher versions/config variants
when that verification occurs; do not advertise unverified variants as supported.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished game-parent-integration-hardening
```

This writes:

```text
/tmp/SDH-PlayTime/game-parent-integration-hardening_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer game-parent-integration-hardening`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/game-parent-integration-hardening-review-*.md
```

When a review note exists or a new review note appears:

1. Read the full review note.
2. If the note ends with:

   ```text
   STATUS: CHANGES_REQUESTED
   ```

   then resume work.

3. Clear the round-complete marker:

   ```bash
   scripts/orchestration/clear-finished game-parent-integration-hardening
   ```

4. Address every requested change.
5. Run quality gates:

   ```bash
   scripts/orchestration/run-quality-gates
   scripts/orchestration/check-review-notes-not-deleted
   ```

6. Commit code/docs fixes.
7. Commit the review-note file itself if it is not already committed:

   ```bash
   git add docs/review/game-parent-integration-hardening-review-*.md
   git commit -m "docs(review): record game-parent-integration-hardening review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished game-parent-integration-hardening
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer game-parent-integration-hardening` after the next review note is created.

---

## Approval Handling

If the latest review note ends with:

```text
STATUS: APPROVED
```

then:

1. Confirm every previous review item has been addressed.
2. Confirm all review notes are committed:

   ```bash
   scripts/orchestration/check-review-notes-committed game-parent-integration-hardening
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize game-parent-integration-hardening
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/game-parent-integration-hardening_finalized
   ```

6. Stop polling and exit cleanly.

---

## Review Rules

Do not write your own review.

Do not create files under:

```text
docs/review/
```

Do not delete files under:

```text
docs/review/
```

Only the orchestrator writes review notes. Your job is to read them, resolve them, commit them as audit records, and continue the loop.

---

## Finalization Rules

Only finalize after a review note with:

```text
STATUS: APPROVED
```

Finalization is performed with:

```bash
scripts/orchestration/finalize game-parent-integration-hardening
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/game-parent-integration-hardening_finished
/tmp/SDH-PlayTime/game-parent-integration-hardening_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
