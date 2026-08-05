# Plan: Game Resolution Core and Direct Executables (game-resolution-core)

## Context

A shortcut classifier can identify launcher evidence, but only backend filesystem and
metadata resolution can establish that an actual game payload is reachable. Build the
security-sensitive resolver coordinator, batched RPC, mount-aware probe, and direct
executable adapter. All unsupported launcher kinds must return structured unknown
results until their dedicated adapters land. This plan depends on
`shortcut-evidence-classifier` being merged to `remix`.

**Slug used throughout this plan:** `game-resolution-core`

---

## Orchestration Contract

**Slug:** `game-resolution-core`

**Plan file:**

```text
docs/plans/2026-08-05_game-resolution-core.md
```

**Implementation branch:**

```text
feat/game-resolution-core
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/game-resolution-core_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/game-resolution-core_finalized
```

**Review notes:**

```text
docs/review/game-resolution-core-review-*.md
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
git checkout -b feat/game-resolution-core
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_game-resolution-core.md
git commit -m "docs(plan): add game-resolution-core implementation plan"
```

---

## Implementation Tasks

1. Add matching Python/TypeScript contracts for launcher kind, normalized shortcut
   evidence, metadata status, payload status/kind, provenance, and structured reason
   codes: missing, ambiguous, unsupported, permission denied, malformed, disconnected
   volume, payload missing, and probe failure.
2. Add `py_modules/game_resolution/` with typed internal models, coordinator, adapter
   registry, safe path helpers, filesystem/mount probe, and direct-executable adapter.
   Keep adapters deterministic and dependency-injected for tests.
3. Treat every frontend classification as an untrusted hint. Revalidate field lengths,
   launcher signatures, identifiers, and path syntax at the backend boundary. Reject
   traversal when locating metadata, but permit resolved game payloads and safe symlinks
   on external volumes.
4. Implement direct target resolution for native binaries, AppImages, and Windows game
   executables when the shortcut directly identifies the payload. Exclude known shared
   Wine/Proton, Flatpak, launcher, emulator, shell, and wrapper executables. Never infer
   a game path from arbitrary shell fragments.
5. Implement an injectable filesystem/mount probe. Return reachable only for the
   adapter's expected file/directory kind. Return `drive_disconnected` only when a path
   lies below a recognized removable-media root and the mount table proves the expected
   volume absent; otherwise distinguish missing payload, directory/file mismatch,
   permission error, and unknown probe failure.
6. Add a bounded batched resolver RPC in `main.py` and matching frontend backend client
   and constants. Enforce maximum batch size, string lengths, per-entry metadata candidates,
   and deterministic response order. The RPC must not scan unrelated directories.
7. Prohibit `subprocess`, shell evaluation, URL activation, mounting, launcher CLI calls,
   and game launch. Do not log full commands or personal payload paths at normal levels.
8. Add backend and RPC tests using temporary files and an injected mount table for valid
   direct payloads, shared runners, quoted paths, files/directories, symlinks, absent
   volumes, mounted-but-missing payloads, traversal, permission errors, unknown launchers,
   malformed requests, and batch limits.

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

1. Resolve direct native/AppImage/Windows fixtures and verify only the actual game target
   becomes reachable.
2. Verify shared Wine, Proton, Flatpak, shell, and launcher executables return unknown and
   are never probed as game payloads.
3. Simulate an absent external mount, a mounted volume with a missing file, and a
   permission failure; verify their reason codes remain distinct.
4. Submit oversized and malformed batches and verify deterministic structured rejection
   without filesystem scanning or process execution.

Live mount-table behavior on SteamOS is deferred to integration hardening.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished game-resolution-core
```

This writes:

```text
/tmp/SDH-PlayTime/game-resolution-core_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer game-resolution-core`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/game-resolution-core-review-*.md
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
   scripts/orchestration/clear-finished game-resolution-core
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
   git add docs/review/game-resolution-core-review-*.md
   git commit -m "docs(review): record game-resolution-core review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished game-resolution-core
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer game-resolution-core` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed game-resolution-core
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize game-resolution-core
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/game-resolution-core_finalized
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
scripts/orchestration/finalize game-resolution-core
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/game-resolution-core_finished
/tmp/SDH-PlayTime/game-resolution-core_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
