# Plan: Resolver-Gated Game Checksums (resolver-gated-game-checksums)

## Context

The current checksum flow accepts a frontend-derived path and can hash a launcher,
emulator, Wine/Proton binary, or stale shortcut target instead of the actual game.
Require a backend-confirmed reachable payload before hashing while preserving fail-closed
behavior for unsupported games. This plan depends on `game-resolution-core` and the Heroic
adapter being merged to `remix`. This unit supports direct executables and Heroic only;
Lutris, Bottles, and EmuDeck/Steam ROM Manager remain explicitly unsupported.

**Slug used throughout this plan:** `resolver-gated-game-checksums`

---

## Orchestration Contract

**Slug:** `resolver-gated-game-checksums`

**Plan file:**

```text
docs/plans/2026-08-05_resolver-gated-game-checksums.md
```

**Implementation branch:**

```text
feat/resolver-gated-game-checksums
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/resolver-gated-game-checksums_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/resolver-gated-game-checksums_finalized
```

**Review notes:**

```text
docs/review/resolver-gated-game-checksums-review-*.md
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
git checkout -b feat/resolver-gated-game-checksums
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_resolver-gated-game-checksums.md
git commit -m "docs(plan): add resolver-gated-game-checksums implementation plan"
```

---

## Implementation Tasks

1. Start with Python and Bun regression tests proving arbitrary frontend paths and shared
   launcher/emulator/Flatpak/Wine/Proton binaries cannot reach the hash function.
2. Refactor `src/app/games.ts` and `src/app/backend.ts` so checksum requests carry the
   normalized shortcut evidence/app ID required by the resolver, not a caller-trusted
   filesystem path. Keep stable UI error handling for unsupported entries.
3. Add a backend coordinator operation that revalidates and resolves the shortcut, then
   passes only a reachable adapter-confirmed payload to `py_modules/files.py`. Do not
   return the trusted path to an untrusted caller and do not allow a second unchecked
   path parameter.
4. Preserve existing digest algorithm/version semantics. Treat resolver unknown,
   ambiguous, disconnected, missing, permission-denied, and probe-failed results as no
   checksum with structured diagnostic status; never fall back to the shortcut target.
5. Update checksum settings UI/types only enough to distinguish unsupported shortcut,
   missing metadata, unavailable payload, and hash failure. Do not add parent-selection
   UI in this unit.
6. Cover direct and Heroic fixtures; payload changes; game updates; external drive
   disconnect/reconnect; directories; symlinks; malformed RPCs; and first-match ambiguity.
   Cover Lutris, Bottles, and EmuDeck/Steam ROM Manager as explicitly unsupported,
   fail-closed sources. Verify existing reachable direct-executable checksum flows continue
   working.

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

1. Generate checksums for one reachable direct fixture and one reachable Heroic fixture and
   verify the digest is of the game payload, never the launcher or runner. Verify Lutris,
   Bottles, and EmuDeck/Steam ROM Manager return no checksum as unsupported sources.
2. Submit an arbitrary path alongside an unrelated app ID and verify the backend rejects
   it rather than hashing.
3. Disconnect a fixture volume and verify no digest is returned; reconnect it and verify
   hashing resumes only after resolver confirmation.
4. Verify all existing checksum grouping tests retain their digest/algorithm behavior.

Live large-file performance and launcher installations are deferred to integration
hardening.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished resolver-gated-game-checksums
```

This writes:

```text
/tmp/SDH-PlayTime/resolver-gated-game-checksums_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer resolver-gated-game-checksums`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/resolver-gated-game-checksums-review-*.md
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
   scripts/orchestration/clear-finished resolver-gated-game-checksums
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
   git add docs/review/resolver-gated-game-checksums-review-*.md
   git commit -m "docs(review): record resolver-gated-game-checksums review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished resolver-gated-game-checksums
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer resolver-gated-game-checksums` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed resolver-gated-game-checksums
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize resolver-gated-game-checksums
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/resolver-gated-game-checksums_finalized
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
scripts/orchestration/finalize resolver-gated-game-checksums
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/resolver-gated-game-checksums_finished
/tmp/SDH-PlayTime/resolver-gated-game-checksums_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
