# Plan: Game Parent Presence and Ranking (game-parent-presence-ranking)

## Context

Parent selection needs live evidence that distinguishes a current library listing from
an installed/reachable payload and a retained historical record. Build a point-in-time
candidate snapshot and a pure, fail-closed recommendation engine. Do not persist live
presence or change associations in this unit. This plan depends on
`zero-time-association-candidates`, `shortcut-evidence-classifier`,
and `game-resolution-core` being merged to `remix`. Direct executables and Heroic are
the implemented non-Steam resolver paths. Lutris, Bottles, and EmuDeck/Steam ROM Manager
are deliberately out of scope here and must remain fail-closed.

**Slug used throughout this plan:** `game-parent-presence-ranking`

---

## Orchestration Contract

**Slug:** `game-parent-presence-ranking`

**Plan file:**

```text
docs/plans/2026-08-05_game-parent-presence-ranking.md
```

**Implementation branch:**

```text
feat/game-parent-presence-ranking
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/game-parent-presence-ranking_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/game-parent-presence-ranking_finalized
```

**Review notes:**

```text
docs/review/game-parent-presence-ranking-review-*.md
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
git checkout -b feat/game-parent-presence-ranking
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_game-parent-presence-ranking.md
git commit -m "docs(plan): add game-parent-presence-ranking implementation plan"
```

---

## Implementation Tasks

1. Define separate inventory (`current`, `historical`, `unknown`) and availability
   (`running`, `reachable`, `unreachable`, `unknown`) DTOs plus structured reason codes.
   Use `Installed` only for reliable native Steam install evidence and `Available on this
   Deck` for resolved non-Steam payloads.
2. Add `src/app/gamePresence.ts` to build one snapshot by joining raw backend candidates,
   live native/non-Steam app stores, `SteamUIStore.RunningApps`, app details/native install
   evidence, and batched resolver results. Include live library entries with no tracked
   row; do not write them to the database during a read/refresh.
3. Track completeness independently for the authoritative native Steam and non-Steam
   inventories. Mark a tracked record historical only when its own authoritative source
   completed successfully and omitted its ID. Missing/loading/failed sources produce
   unknown, never historical.
4. Preserve both axes: a shortcut may be current while its payload reports
   `drive_disconnected` or `payload_missing`; a removed shortcut may be historical; a
   failed resolver/store remains unknown.
5. Capability-detect a reliable native Steam install-state probe and type it narrowly.
   When the runtime does not expose reliable evidence, return availability unknown rather
   than inferring installation from ownership, library membership, disk-usage fields, or
   a shortcut.
6. Bound app-details concurrency, batch resolver calls, and per-snapshot cache lifetime.
   Add an explicit refresh operation that rebuilds the snapshot and performs no database
   writes. Scrub full commands/personal paths from normal logs and UI DTOs.
7. Add pure `src/app/associationRanking.ts`. Keep a confirmed parent effective and return
   an advisory recommendation only for exactly one running member, otherwise exactly one
   current-and-reachable member. Multiple best-tier members, unknown/unreachable current
   entries, all historical members, incomplete inventory, ambiguity, and conflicts return
   `review_required` with reasons.
8. Source type, recent playtime, total time, numeric ID, and lexical ID may produce stable
   display order but must not break a semantic tie or become an implicit recommendation.
   Fuzzy title similarity is never authoritative.
9. Add pure Bun tests for source completeness, current/historical/unknown derivation,
   native/launcher reachability, drive disconnect/reconnect refresh, exactly-one rules,
   multiple reachable ties, all-historical groups, confirmed-parent stability, input-order
   independence, and no-write refresh behavior.

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

1. Present one historical high-playtime member and one current reachable member; verify
   only the latter is recommended.
2. Present two current reachable members and verify both remain a semantic tie requiring
   review regardless of source, playtime, or ID.
3. Fail one inventory source and verify only candidates governed by that source become
   unknown; none become historical from another store's success.
4. Disconnect/reconnect a current shortcut's external volume and verify availability
   changes while inventory and confirmed parent remain stable and no database call writes.
5. Remove a shortcut from a complete inventory and verify the tracked row becomes
   historical; repeat with incomplete inventory and verify unknown.

Live Steam install-state capability and store-loading behavior are deferred to integration
hardening.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished game-parent-presence-ranking
```

This writes:

```text
/tmp/SDH-PlayTime/game-parent-presence-ranking_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer game-parent-presence-ranking`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/game-parent-presence-ranking-review-*.md
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
   scripts/orchestration/clear-finished game-parent-presence-ranking
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
   git add docs/review/game-parent-presence-ranking-review-*.md
   git commit -m "docs(review): record game-parent-presence-ranking review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished game-parent-presence-ranking
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer game-parent-presence-ranking` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed game-parent-presence-ranking
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize game-parent-presence-ranking
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/game-parent-presence-ranking_finalized
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
scripts/orchestration/finalize game-parent-presence-ranking
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/game-parent-presence-ranking_finished
/tmp/SDH-PlayTime/game-parent-presence-ranking_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
