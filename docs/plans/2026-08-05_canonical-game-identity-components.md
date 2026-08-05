# Plan: Canonical Game Identity Components (canonical-game-identity-components)

## Context

Checksum grouping, explicit game associations, and statistics projections currently
choose representatives through separate algorithms. Lexical SQL ordering and first-row
encounter order can therefore select different parent IDs for the same logical game.
Create one pure backend identity-component model that all read paths share. This unit
changes canonical read behavior only; it must not add launcher detection, UI, schema
migrations, or write/reparent APIs.

**Slug used throughout this plan:** `canonical-game-identity-components`

---

## Orchestration Contract

**Slug:** `canonical-game-identity-components`

**Plan file:**

```text
docs/plans/2026-08-05_canonical-game-identity-components.md
```

**Implementation branch:**

```text
feat/canonical-game-identity-components
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/canonical-game-identity-components_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/canonical-game-identity-components_finalized
```

**Review notes:**

```text
docs/review/canonical-game-identity-components-review-*.md
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
git checkout -b feat/canonical-game-identity-components
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_canonical-game-identity-components.md
git commit -m "docs(plan): add canonical-game-identity-components implementation plan"
```

---

## Implementation Tasks

1. Start with failing tests in a new `py_modules/tests/game_identity_test.py` for
   unordered checksum edges, explicit association edges, transitive mixed components,
   aliases, and conflicts.
2. Add `py_modules/game_identity.py` with a deterministic union/find implementation.
   Normalize and sort inputs before unioning. Return each component's sorted unique
   members, complete alias set, canonical ID, explicit-parent set, and status.
3. Apply these canonical rules:
   - one explicit parent wins, even when its ID is larger than the checksum fallback;
   - no explicit parent uses the existing lexically smallest checksum member for
     compatibility and is marked unconfirmed;
   - multiple explicit parents in one checksum-connected component return `conflict`
     with a deterministic display fallback and never mutate data.
4. Replace the recursive/lexical checksum leader code in `py_modules/db/dao.py` with
   the shared component builder while retaining existing DAO response shapes where
   callers require them.
5. Refactor every association/checksum aggregation path in
   `py_modules/statistics.py` and `py_modules/games.py` to consume the same component
   map. Eliminate first-encountered representatives. Emit every explicit and checksum
   alias exactly once.
6. Extend the existing statistics/association regression tests for an explicit parent
   that is not the checksum leader, a child hidden under a third checksum leader,
   input-order changes, and the representative-child disappearance case.
7. Preserve migration-10 storage and the existing flat association RPCs. Do not write
   association rows from the canonicalizer and do not introduce migration 11.

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

1. Run the focused identity, DAO, games, and statistics tests and confirm randomized
   input ordering produces identical components and canonical IDs.
2. Verify a checksum-only family retains the previous lexical parent, while adding one
   explicit association selects the explicit parent across every report projection.
3. Verify a component with two explicit parents reports conflict and leaves the
   database unchanged.

No on-device verification is required for this pure backend unit.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished canonical-game-identity-components
```

This writes:

```text
/tmp/SDH-PlayTime/canonical-game-identity-components_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer canonical-game-identity-components`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/canonical-game-identity-components-review-*.md
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
   scripts/orchestration/clear-finished canonical-game-identity-components
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
   git add docs/review/canonical-game-identity-components-review-*.md
   git commit -m "docs(review): record canonical-game-identity-components review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished canonical-game-identity-components
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer canonical-game-identity-components` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed canonical-game-identity-components
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize canonical-game-identity-components
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/canonical-game-identity-components_finalized
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
scripts/orchestration/finalize canonical-game-identity-components
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/canonical-game-identity-components_finished
/tmp/SDH-PlayTime/canonical-game-identity-components_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
