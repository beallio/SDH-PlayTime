# Plan: Zero-Time Association Candidates (zero-time-association-candidates)

## Context

A newly installed or newly created Steam shortcut may be the correct parent before it
has any tracked playtime. Current DAO reads inner-join `overall_time`, and the current
game dictionary hides existing association children, so those valid candidates cannot
participate safely. Add a raw candidate surface and zero-duration identity handling
without synthesizing playtime. This plan depends on
`atomic-game-parent-confirmation` being merged to `remix`.

**Slug used throughout this plan:** `zero-time-association-candidates`

---

## Orchestration Contract

**Slug:** `zero-time-association-candidates`

**Plan file:**

```text
docs/plans/2026-08-05_zero-time-association-candidates.md
```

**Implementation branch:**

```text
feat/zero-time-association-candidates
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/zero-time-association-candidates_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/zero-time-association-candidates_finalized
```

**Review notes:**

```text
docs/review/zero-time-association-candidates-review-*.md
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
git checkout -b feat/zero-time-association-candidates
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_zero-time-association-candidates.md
git commit -m "docs(plan): add zero-time-association-candidates implementation plan"
```

---

## Implementation Tasks

1. Begin with DAO/manager/RPC tests showing that a `game_dict` identity with no
   `overall_time` row is readable with duration zero and can be explicitly confirmed as
   parent.
2. Change the internal DAO game read from `INNER JOIN overall_time` to a left join with
   `COALESCE(duration, 0)`. Audit callers so the absence of a playtime row remains
   distinguishable from a stored correction where needed.
3. Add an unfiltered backend association-candidate read containing every tracked
   identity and association member, including children hidden by the legacy games
   dictionary. Do not alter the legacy filtered dictionary response.
4. Allow the atomic confirmation transaction to upsert an explicitly selected current
   ID/name into `game_dict`. Never create a fake `overall_time` row and never add an
   arbitrary unselected inventory entry to the component.
5. Add matching response types and frontend backend-client method so later presence/UI
   work can union raw tracked candidates with live Steam inventory entries.
6. Cover missing names, duplicate upserts, zero duration, existing children, and legacy
   dictionary compatibility in tests. Keep live Steam-store enumeration out of this
   backend-focused unit.

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

1. Read a `game_dict` row without overall time and verify its duration is zero.
2. Confirm that identity as a parent and verify the association star is created without
   inserting an overall-time row.
3. Verify the raw candidate API includes children while the legacy dictionary continues
   hiding them as before.

Live Steam inventory verification is deferred to `game-parent-presence-ranking`.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished zero-time-association-candidates
```

This writes:

```text
/tmp/SDH-PlayTime/zero-time-association-candidates_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer zero-time-association-candidates`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/zero-time-association-candidates-review-*.md
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
   scripts/orchestration/clear-finished zero-time-association-candidates
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
   git add docs/review/zero-time-association-candidates-review-*.md
   git commit -m "docs(review): record zero-time-association-candidates review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished zero-time-association-candidates
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer zero-time-association-candidates` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed zero-time-association-candidates
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize zero-time-association-candidates
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/zero-time-association-candidates_finalized
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
scripts/orchestration/finalize zero-time-association-candidates
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/zero-time-association-candidates_finished
/tmp/SDH-PlayTime/zero-time-association-candidates_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
