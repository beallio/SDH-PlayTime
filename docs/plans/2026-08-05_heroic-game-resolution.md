# Plan: Heroic Game Resolution (heroic-game-resolution)

## Context

A Heroic shortcut can remain in Steam while its launcher metadata or external game
payload is absent. Add a Heroic adapter that maps a validated shortcut identity through
Heroic metadata to the actual executable or ROM. The Heroic/Flatpak binary, Wine prefix,
and `GamesConfig` file are evidence only, never proof of reachability. This plan depends
on `game-resolution-core` being merged to `remix`.

**Slug used throughout this plan:** `heroic-game-resolution`

---

## Orchestration Contract

**Slug:** `heroic-game-resolution`

**Plan file:**

```text
docs/plans/2026-08-05_heroic-game-resolution.md
```

**Implementation branch:**

```text
feat/heroic-game-resolution
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/heroic-game-resolution_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/heroic-game-resolution_finalized
```

**Review notes:**

```text
docs/review/heroic-game-resolution-review-*.md
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
git checkout -b feat/heroic-game-resolution
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_heroic-game-resolution.md
git commit -m "docs(plan): add heroic-game-resolution implementation plan"
```

---

## Implementation Tasks

1. Add sanitized fixtures derived from
   `Heroic-Games-Launcher/HeroicGamesLauncher@d6366b3408`, retaining source-file/commit
   provenance for native/AppImage/Flatpak commands, current query and legacy pathname
   `heroic://launch` URIs, normal installed-game metadata, settings, and sideload data.
2. Add a Heroic adapter under `py_modules/game_resolution/` that revalidates the Heroic
   launcher signature and extracts app ID, runner, and optional `altExe` without
   executing or activating the URI.
3. Locate `$XDG_CONFIG_HOME/heroic` and the Flatpak host equivalent beneath
   `~/.var/app/com.heroicgameslauncher.hgl/config/heroic`. Keep root discovery injectable
   and bounded; custom/unverified roots return unknown unless the shortcut supplies a
   validated supported root contract.
4. Resolve normal installs through the runner's `InstalledInfo.install_path + executable`.
   Resolve sideloads through the absolute executable in
   `sideload_apps/library.json`. Use `GamesConfig/<app>.json` only for launch settings,
   prefix, and alternate-executable evidence; its existence alone is not a payload.
5. Require runner disambiguation when identical IDs can exist across runners. Honor
   fixture-backed `altExe` semantics. Return ambiguous for runnerless duplicates,
   conflicting metadata, multiple payload candidates, or inconsistent identities.
6. Pass the resolved executable/ROM to the shared payload/mount probe and retain metadata
   provenance/status separately from payload status. Never return the Heroic executable,
   Flatpak binary, Wine prefix, or directory alone as the game.
7. Add tests for normal native/Flatpak installs, sideloads, external drives, current and
   legacy URIs, alternate executable, encoded values, missing/malformed metadata,
   runnerless duplicates, traversal, permission failure, and launcher-present/payload-
   missing behavior.

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

1. Resolve one normal and one sideloaded Heroic fixture to the actual payload and verify
   launcher and prefix paths are never selected.
2. Remove the payload while retaining shortcut and metadata; verify inventory evidence
   remains resolvable but availability reports payload missing.
3. Place the payload on an injected disconnected volume and verify
   `drive_disconnected`; reconnect it and verify reachable without metadata mutation.
4. Verify runnerless duplicate and malformed cases fail closed as ambiguous/unknown.

Live Heroic native and Flatpak installations are deferred to integration hardening.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished heroic-game-resolution
```

This writes:

```text
/tmp/SDH-PlayTime/heroic-game-resolution_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer heroic-game-resolution`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/heroic-game-resolution-review-*.md
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
   scripts/orchestration/clear-finished heroic-game-resolution
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
   git add docs/review/heroic-game-resolution-review-*.md
   git commit -m "docs(review): record heroic-game-resolution review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished heroic-game-resolution
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer heroic-game-resolution` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed heroic-game-resolution
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize heroic-game-resolution
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/heroic-game-resolution_finalized
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
scripts/orchestration/finalize heroic-game-resolution
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/heroic-game-resolution_finished
/tmp/SDH-PlayTime/heroic-game-resolution_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
