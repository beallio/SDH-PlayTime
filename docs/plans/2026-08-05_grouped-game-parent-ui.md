# Plan: Grouped Game Parent UI (grouped-game-parent-ui)

## Context

The association screens currently show unranked name/ID dropdowns, save immediately, and
repeat the same parent on one row per child. Replace them with one grouped, status-rich,
explicit confirmation experience that consumes the shared presence/ranking and atomic
backend APIs. This plan depends on `atomic-game-parent-confirmation` and
`game-parent-presence-ranking` being merged to `remix`.

**Slug used throughout this plan:** `grouped-game-parent-ui`

---

## Orchestration Contract

**Slug:** `grouped-game-parent-ui`

**Plan file:**

```text
docs/plans/2026-08-05_grouped-game-parent-ui.md
```

**Implementation branch:**

```text
feat/grouped-game-parent-ui
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/grouped-game-parent-ui_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/grouped-game-parent-ui_finalized
```

**Review notes:**

```text
docs/review/grouped-game-parent-ui-review-*.md
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
git checkout -b feat/grouped-game-parent-ui
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_grouped-game-parent-ui.md
git commit -m "docs(plan): add grouped-game-parent-ui implementation plan"
```

---

## Implementation Tasks

1. Extract pure association candidate/group view-model and status presentation helpers.
   Reuse the visual conventions of `StatusBadge.tsx`, but keep tracking status separate
   from inventory and availability semantics.
2. Refactor `src/pages/association/hooks/useGamesForAssociation.ts` and
   `src/pages/AssociationAddPage.tsx` to select explicit members and render candidate
   cards showing title, Steam ID, source/launcher, tracked time, inventory status,
   availability status, and recommendation/review reasons. Never treat the entire
   inventory as one group.
3. Preselect a reliable recommendation for convenience, but do not persist it until the
   user confirms. Permit manual selection of a known-unreachable/unknown candidate only
   with a prominent warning; never claim it is installed.
4. Before creation or reparenting, show a confirmation summary with old parent when
   present, proposed parent, all affected members, reasons, and warnings. Submit the
   expected fingerprint/member snapshot and handle stale/conflict errors by refreshing
   instead of retrying silently.
5. Refactor `src/pages/AssociationListPage.tsx`,
   `src/pages/association/hooks/useAssociations.ts`, and
   `src/pages/association/components/AssociationListItem.tsx` to one card per logical
   component, confirmed parent first and children beneath it. Include status refresh,
   `Change parent`, detach child, and dissolve group actions.
6. Match backend removal rules: detaching retains history; dissolving removes explicit
   edges; removing a confirmed parent requires a replacement confirmation or explicit
   dissolution. Never auto-promote the first remaining child.
7. Update `src/components/showOptionsMenu.tsx` and navigation so context-menu association
   actions open or reuse the same grouped selection and confirmation path. Do not retain
   a second unranked parent algorithm.
8. Use explicit labels: `Running now`, `Current library entry`,
   `Available on this Deck`, `Drive disconnected`, `Installation missing`,
   `Historical record`, and `Status unavailable`.
9. The repository lacks a React rendering harness. Test extracted view models, status
   mappings, event decisions, modal payloads, and backend service interactions with Bun;
   do not add a new component-testing framework solely for this plan.
10. Cover duplicate names, long labels, preselection, semantic ties, manual warning,
    stale confirmation, grouped rendering, refresh, detach, dissolve, parent removal, and
    context-menu parity.

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

1. Create a group from duplicate-name candidates and verify every card exposes enough
   ID/source/status evidence to distinguish them.
2. Verify a sole current/reachable candidate is preselected but not saved before the
   confirmation summary is accepted.
3. Verify two reachable candidates require manual selection and a known-unreachable
   parent displays a warning.
4. Reparent a multi-child group and verify list, add, and context-menu flows show the same
   grouped result and statuses.
5. Exercise detach, dissolve, and confirmed-parent removal and verify no implicit
   promotion or history deletion.

Gamepad layout and live Steam Deck rendering are deferred to integration hardening.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished grouped-game-parent-ui
```

This writes:

```text
/tmp/SDH-PlayTime/grouped-game-parent-ui_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer grouped-game-parent-ui`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/grouped-game-parent-ui-review-*.md
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
   scripts/orchestration/clear-finished grouped-game-parent-ui
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
   git add docs/review/grouped-game-parent-ui-review-*.md
   git commit -m "docs(review): record grouped-game-parent-ui review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished grouped-game-parent-ui
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer grouped-game-parent-ui` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed grouped-game-parent-ui
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize grouped-game-parent-ui
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/grouped-game-parent-ui_finalized
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
scripts/orchestration/finalize grouped-game-parent-ui
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/grouped-game-parent-ui_finished
/tmp/SDH-PlayTime/grouped-game-parent-ui_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
