# Plan: Atomic Game Parent Confirmation (atomic-game-parent-confirmation)

## Context

Migration 10 stores a logical group as a star of `game_association` rows, but current
validation and insertion occur across separate transactions and cannot safely switch
the parent of a complete checksum/association component. Add grouped reads and one
optimistic, atomic confirmation operation while preserving migration 10 and legacy
callers. This plan depends on `canonical-game-identity-components` being present on
`remix`; stop without editing if `py_modules/game_identity.py` is absent.

**Slug used throughout this plan:** `atomic-game-parent-confirmation`

---

## Orchestration Contract

**Slug:** `atomic-game-parent-confirmation`

**Plan file:**

```text
docs/plans/2026-08-05_atomic-game-parent-confirmation.md
```

**Implementation branch:**

```text
feat/atomic-game-parent-confirmation
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/atomic-game-parent-confirmation_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/atomic-game-parent-confirmation_finalized
```

**Review notes:**

```text
docs/review/atomic-game-parent-confirmation-review-*.md
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
git checkout -b feat/atomic-game-parent-confirmation
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_atomic-game-parent-confirmation.md
git commit -m "docs(plan): add atomic-game-parent-confirmation implementation plan"
```

---

## Implementation Tasks

1. Add failing DAO and manager tests for grouped reads, idempotent confirmation, a full
   parent switch, stale component evidence, nonmembers, mixed checksum members, and
   rollback after an injected insertion failure.
2. Define grouped association request/response and structured error DTOs in
   `py_modules/schemas/` and matching frontend types in
   `src/types/association.d.ts`. Include anchor ID, proposed parent ID/name, expected
   parent, sorted existing members or fingerprint, explicitly selected members,
   confirmed parent, status, and aliases.
3. Add DAO grouped reads that derive components exclusively through
   `py_modules/game_identity.py`. Use a deterministic fingerprint of sorted member IDs;
   do not add a persisted group or revision table.
4. Add one `SqlLiteDb.transactional()` DAO operation that recomputes the component,
   compares the expected parent and members/fingerprint, validates explicitly selected
   additions, upserts required `game_dict` identities, deletes every explicit edge in
   the component, and recreates a complete star from the proposed parent. Any error
   must roll back the original star.
5. Treat multiple explicit parents joined by checksum evidence as a structured
   `COMPONENT_CONFLICT`; do not repair it until the user explicitly confirms the full
   submitted member set. Reject stale, invalid, and unexpected membership with stable
   error codes rather than SQLite messages.
6. Define transactional removal semantics: detach a child without deleting its history;
   dissolve a group by deleting its explicit edges; require a replacement confirmation
   or explicit dissolution before removing the parent. Never promote the first child.
7. Expose grouped reads, confirmation, detach, and dissolve through
   `py_modules/association_manager.py`, `main.py`, `src/constants.ts`, and
   `src/app/association.ts`. Keep compatibility wrappers for current create/remove and
   flat-list consumers until the UI conversion lands.
8. Add RPC/client tests for exact DTOs, malformed input, network fallback, and every
   structured conflict. Do not add UI or presence-based recommendations in this unit.

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

1. Confirm switching a three-member star rewrites all edges to the selected parent and
   every member still resolves through the canonical identity component.
2. Submit a stale fingerprint and verify no rows change.
3. Inject failure between deletion and reinsertion and verify the original complete star
   remains intact.
4. Verify compatibility create/list/remove callers retain their current successful and
   error behavior.

No on-device verification is required for this transaction/API unit.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished atomic-game-parent-confirmation
```

This writes:

```text
/tmp/SDH-PlayTime/atomic-game-parent-confirmation_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer atomic-game-parent-confirmation`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/atomic-game-parent-confirmation-review-*.md
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
   scripts/orchestration/clear-finished atomic-game-parent-confirmation
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
   git add docs/review/atomic-game-parent-confirmation-review-*.md
   git commit -m "docs(review): record atomic-game-parent-confirmation review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished atomic-game-parent-confirmation
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer atomic-game-parent-confirmation` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed atomic-game-parent-confirmation
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize atomic-game-parent-confirmation
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/atomic-game-parent-confirmation_finalized
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
scripts/orchestration/finalize atomic-game-parent-confirmation
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/atomic-game-parent-confirmation_finished
/tmp/SDH-PlayTime/atomic-game-parent-confirmation_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
