# Plan: Shortcut Evidence Classifier (shortcut-evidence-classifier)

## Context

`GamePaths.ts` currently relies on substring checks for `/Emulation/roms/` and `.exe`,
while `getAppDetails.ts` collapses timeout, callback failure, and missing details into
one null result. Define a safe, pure shortcut-evidence contract that recognizes direct,
Heroic, Lutris, Bottles, and EmuDeck/SRM signatures without claiming that any payload is
installed. This unit classifies evidence only and preserves current runtime consumers
until backend resolution lands.

**Slug used throughout this plan:** `shortcut-evidence-classifier`

---

## Orchestration Contract

**Slug:** `shortcut-evidence-classifier`

**Plan file:**

```text
docs/plans/2026-08-05_shortcut-evidence-classifier.md
```

**Implementation branch:**

```text
feat/shortcut-evidence-classifier
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/shortcut-evidence-classifier_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/shortcut-evidence-classifier_finalized
```

**Review notes:**

```text
docs/review/shortcut-evidence-classifier-review-*.md
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
git checkout -b feat/shortcut-evidence-classifier
```

Commit this plan first:

```bash
git add docs/plans/2026-08-05_shortcut-evidence-classifier.md
git commit -m "docs(plan): add shortcut-evidence-classifier implementation plan"
```

---

## Implementation Tasks

1. Add frontend types for launcher kind, normalized shortcut fields, classification
   status, external identity hints, and distinct app-details failure reasons. Do not add
   inventory, availability, or recommendation semantics yet.
2. Refactor `src/steam/utils/getAppDetails.ts` so success, timeout, callback/registration
   error, missing details, and unsupported Steam runtime capability remain distinct and
   testable. Preserve a compatibility wrapper for existing nullable callers.
3. Replace substring parsing in `src/steam/utils/GamePaths.ts` with a pure token-aware
   classifier over `strFlatpakAppID`, `strShortcutExe`,
   `strShortcutLaunchOptions`, and `strShortcutStartDir`. Parse quoting, escaping, URI
   encoding, and `--` separators without shell evaluation.
4. Recognize fixture-backed hints for:
   - direct native/AppImage/Windows executable targets while excluding known shared
     Wine, Proton, Flatpak, launcher, emulator, and wrapper binaries;
   - Heroic native/AppImage/Flatpak plus current query and legacy path
     `heroic://launch` forms, preserving runner and `altExe` evidence;
   - Lutris numeric `rungameid`, slug `rungame`, Flatpak, and standalone wrapper forms;
   - Bottles native/Flatpak `bottles-cli run` with bottle and program/name/ID/executable
     options;
   - EmuDeck/SRM executable plus launch-option evidence without assuming
     `/Emulation/roms/` identifies every ROM.
5. Store sanitized command cases in one JSON fixture corpus that Bun and later Python
   tests can consume. Record the verified official repository commit/source path beside
   each case. Include spaces, nested/escaped quotes, URI encoding, separators, missing
   fields, duplicate identifiers, and unknown launchers.
6. Treat the result as an untrusted classification hint. Unknown or ambiguous commands
   fail closed and never return a launcher binary as a payload. Keep the current
   `getPathToGame`/checksum compatibility surface behaviorally stable until
   `resolver-gated-game-checksums` replaces it.

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

1. Run table-driven classifier and app-details tests for every success and failure
   reason, including input-order/quoting variants.
2. Verify no classifier path evaluates a shell command or treats a shared launcher,
   Flatpak, Wine/Proton, emulator, or wrapper binary as the game payload.
3. Verify existing checksum/path callers retain their pre-plan observable behavior.

Backend metadata and live launcher verification are deferred to the resolver plans.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished shortcut-evidence-classifier
```

This writes:

```text
/tmp/SDH-PlayTime/shortcut-evidence-classifier_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer shortcut-evidence-classifier`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/shortcut-evidence-classifier-review-*.md
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
   scripts/orchestration/clear-finished shortcut-evidence-classifier
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
   git add docs/review/shortcut-evidence-classifier-review-*.md
   git commit -m "docs(review): record shortcut-evidence-classifier review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished shortcut-evidence-classifier
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer shortcut-evidence-classifier` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed shortcut-evidence-classifier
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize shortcut-evidence-classifier
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/shortcut-evidence-classifier_finalized
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
scripts/orchestration/finalize shortcut-evidence-classifier
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/shortcut-evidence-classifier_finished
/tmp/SDH-PlayTime/shortcut-evidence-classifier_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
