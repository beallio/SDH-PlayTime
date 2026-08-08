# Plan: Accept Heroic flatpak shortcuts with bare exe and extra launch flags (heroic-shortcut-validation)

## Context

Non-Steam games launched through the Heroic Games Launcher report "Status unavailable" in the
association UI even when they are installed and their payload is present on a mounted drive. The
cause is `HeroicAdapter._validated_identity` in `py_modules/game_resolution/heroic.py`, which
rejects the shortcut shape Heroic actually writes. Measured against the live plugin on a Steam
Deck for `Transformers Devastation` (Steam shortcut appid `3015223078`), Steam reports
`strShortcutExe` as `"flatpak"` (quoted, bare, not a path), `strFlatpakAppID` as the empty string,
and `strShortcutLaunchOptions` as
`run com.heroicgameslauncher.hgl --no-gui --no-sandbox "heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload"`.
Three independent gates reject that: `heroic.py:206` requires an absolute executable path and
raises immediately on a bare name; `heroic.py:219-223` computes `is_flatpak`, which is `False`
unless `flatpak_app_id` is non-`None` and equal to `HEROIC_FLATPAK_APP_ID`, so control falls
through to the native branch and raises at `heroic.py:239-242`; and `heroic.py:224-231` accepts
only three launch-option tokens (or four when the third is `--`), while Heroic emits five.
Validation raises before metadata lookup runs, so the adapter returns
`payload_status="unknown"` with `reason_code="malformed"` and Heroic's config is never read. The
frontend is not at fault: running `classifyShortcutEvidence` against those exact values returns
`recognized` / `heroic` with the `heroicAppName` and `heroicRunner` hints intact.

The data is sound. Heroic's `sideload_apps/library.json` records the game as installed, and the
payload exists on a mounted drive. Feeding the adapter evidence that satisfies all three gates
returns `payload_status="reachable"` with the correct `.exe` path, so only validation needs to
change.

Intended outcome: `_validated_identity` accepts the flatpak-launched Heroic shortcut shape Steam
actually reports, without weakening the assertion that the launcher really is Heroic. Three
decisions are settled and must be implemented as specified: skip option-like (leading `-`) tokens
before applying the launch-option shape check, in the same spirit as `parseFlatpakAppId` in
`src/steam/utils/GamePaths.ts:361-379`, which `continue`s past `-`-prefixed tokens (note it
`break`s at a bare `--` rather than skipping it, so this is a parallel rule, not identical
behavior); accept a bare `flatpak` executable only on the flatpak-launcher branch, keeping the
absolute-path requirement for native Heroic executables; and when `flatpak_app_id` is `None`,
derive the identity from the first non-flag launch-option token after `run` and still require it
to equal `HEROIC_FLATPAK_APP_ID`.

Scope is `py_modules/game_resolution/heroic.py` and its tests. No TypeScript change is in scope —
the classifier already emits correct evidence. Do not modify `FlatpakExecutableAdapter` or
`py_modules/game_resolution/direct.py`. Do not add Lutris, Bottles, or EmuDeck/SRM support. Do not
relax the native (non-flatpak) Heroic branch, the `metadata_candidates` guard, the `command_tokens`
consistency check, or the start-directory validation.

**Working-tree precondition.** At the time this plan was written the repository had eight modified
tracked files (including an unrelated, uncommitted `LD_LIBRARY_PATH` fix in
`py_modules/game_resolution/direct.py`) plus untracked `docs/notes/` and `release/*.zip` artifacts.
Per `AGENTS.md`, those are user-owned and out of scope. Before running Setup, the repository owner
must commit or stash them so the implementation branch starts clean; the implementer must not
commit, stash, revert, or `git add` any of them, and must stop and report if the tree is still
dirty when Setup begins.

**Slug used throughout this plan:** `heroic-shortcut-validation`

---

## Orchestration Contract

**Slug:** `heroic-shortcut-validation`

**Plan file:**

```text
docs/plans/2026-08-07_heroic-shortcut-validation.md
```

**Implementation branch:**

```text
feat/heroic-shortcut-validation
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/heroic-shortcut-validation_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/heroic-shortcut-validation_finalized
```

**Review notes:**

```text
docs/review/heroic-shortcut-validation-review-*.md
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
git checkout -b feat/heroic-shortcut-validation
```

Commit this plan first:

```bash
git add docs/plans/2026-08-07_heroic-shortcut-validation.md
git commit -m "docs(plan): add heroic-shortcut-validation implementation plan"
```

---

## Implementation Tasks

Work test-first. Each behavior task below must start with a failing test that demonstrates the
current rejection, and you must record the observed failure output before making it pass.

1. Extend the existing test helper first. `py_modules/tests/heroic_game_resolution_test.py:24-44`
   defines `heroic_entry(*, executable, launch_options, flatpak_app_id=None)`, which every test in
   that file passes to `resolve_batch`; no test constructs a `ResolutionRequest` directly, so
   follow the dict/helper style. The helper currently derives `executableTokens` as `[executable]`
   and hardcodes `shortcutStartDir` to `None` and `startDirTokens` to `[]`, which cannot express
   the real shortcut. Add optional keyword parameters — `executable_tokens`, `shortcut_start_dir`,
   and `start_dir_tokens` — each defaulting to today's behavior so all existing call sites keep
   passing unchanged.

2. Add a failing test for the real shortcut shape using that helper: `executable` of `"flatpak"`
   including the literal double quotes, `executable_tokens` of `["flatpak"]`, `flatpak_app_id` of
   `None`, `shortcut_start_dir` of `"\"/usr/bin\""`, `start_dir_tokens` of `["/usr/bin"]`, and
   `launch_options` of `("run", "com.heroicgameslauncher.hgl", "--no-gui", "--no-sandbox",
   "heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload")`. These are the values the
   frontend classifier actually produces for this shortcut. Assert the adapter resolves it to the
   sideload payload. Run the test and record the failure: it must currently fail with
   `payload_status="unknown"` and `reason_code="malformed"`.

3. Add a failing test asserting each of the three gates independently, so a later change cannot
   silently re-break one of them. One request with an absolute `/usr/bin/flatpak` exe and a
   matching `flatpak_app_id` but five launch tokens; one with an absolute exe and three tokens but
   `flatpak_app_id` of `None`; one with three tokens and a matching `flatpak_app_id` but a bare
   quoted `"flatpak"` exe. All three must currently fail with `reason_code="malformed"`. Record
   the three failure outputs.

4. In `py_modules/game_resolution/heroic.py`, introduce a helper that filters option-like tokens
   out of a launch-option token tuple: drop every token that begins with `-`. Apply it inside the
   flatpak branch before the existing shape check so that the surviving tokens are validated by
   the current three-token rule. Keep the existing four-token `--` form working — after filtering,
   `--` is removed and the remaining tokens are the three-token shape. Do not change the rule that
   the first surviving token is `run` and the second is the Heroic flatpak app id, and do not
   change how the URI is parsed by `_parse_heroic_uri`.

5. In the same file, allow a bare `flatpak` executable on the flatpak-launcher branch only. The
   current `executable = _single_literal_absolute_path(normalized.shortcut_exe)` at `heroic.py:206`
   runs before the branch is chosen and raises on a bare name, so restructure so a bare executable
   whose basename casefolds to `flatpak` is accepted and carried into the flatpak branch, while any
   other non-absolute executable still raises `RequestValidationError("malformed")`. Preserve the
   `normalized.executable_tokens != (str(executable),)` consistency check for both paths — with a
   bare `flatpak` exe the token tuple is `("flatpak",)`, so the comparison must still hold.

6. In the same file, derive the Heroic flatpak identity when `normalized.flatpak_app_id` is `None`.
   Inside the flatpak branch, take the first surviving non-flag token after `run` and require it to
   casefold-equal `HEROIC_FLATPAK_APP_ID`; when `flatpak_app_id` is present it must still match as
   it does today. Do not let this derivation leak into the native branch: `heroic.py:239` must
   continue to reject a request that carries a non-`None` `flatpak_app_id` on the non-flatpak path.

7. Make the tests from tasks 2 and 3 pass without weakening any assertion. Confirm the previously
   recorded `malformed` outputs are gone and the sideload payload path is returned.

8. Add a regression test proving the guards still fail closed. At minimum: a non-flatpak executable
   given as a bare name still raises `malformed`; a flatpak-launcher shortcut whose second
   surviving token is some other flatpak app id (not Heroic) still raises `malformed`; and a
   flatpak-launcher shortcut carrying two `heroic://` URIs after filtering still raises `malformed`.
   These must fail if the relaxation is written too permissively.

9. Do not modify any TypeScript source, `py_modules/game_resolution/direct.py`, or the flatpak
   adapter. If you find an unrelated defect, record it in the session log for a separate plan
   rather than fixing it here.

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

Verification steps must follow `references/verification-standards.md` in the
`orchestration-plan-author` skill. Report actual command output and tallies, not conclusions. Run
the failure cases before the negative control.

1. Record the red state. Before the fix, run the focused Heroic suite and paste its output:
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest py_modules.tests.heroic_game_resolution_test`.
   The new tests from tasks 2 and 3 must appear as failures, and the recorded reason code must be
   `malformed`. If they pass before the implementation exists, the tests are not exercising the
   defect — fix the tests before continuing.

2. Confirm the helper change from task 1 broke nothing. After adding the optional parameters but
   before touching `heroic.py`, run the same focused suite and paste the tally: every pre-existing
   test in that file must still pass. A failure here means the defaults were not preserved.

3. Prove each gate independently went from red to green. For the three task-3 cases, state the
   before and after `payload_status` and `reason_code` for each. A case that was already green
   before the change proves nothing and must be rewritten.

4. Mutation-test the implementation, one change at a time, reverting each before the next. Revert
   the option-token filter and confirm the five-token test fails. Revert the bare-executable
   acceptance and confirm the quoted-`"flatpak"` test fails. Revert the derived flatpak identity
   and confirm the `flatpak_app_id is None` test fails. Paste the failing output for each of the
   three mutations. If any mutation leaves the suite green, the corresponding test is not covering
   its behavior.

5. Confirm the guards still fail closed by running the task-8 regression tests and pasting the
   result. Then prove that regression test can actually catch an over-permissive relaxation:
   temporarily truncate the surviving token tuple to its first three entries after filtering, so a
   command carrying two `heroic://` URIs is wrongly accepted, and confirm the two-URI test flips
   from pass to fail. Paste that failure, then revert the mutation. (Do not instead try stripping
   non-flag tokens — that removes `run`, the app id, and both URIs, leaving nothing to validate, so
   the case still raises `malformed` and the step would prove nothing.)

6. Negative control, run after steps 1-5: with the implementation in place and all mutations
   reverted, run the full Python suites and paste the pass/fail tallies:
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s py_modules/tests -p '*_test.py'` and
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`. Both must be
   green with no skipped Heroic tests.

7. Run `scripts/orchestration/run-quality-gates` and paste its final result line, then run
   `git status --short` and paste its output. The status output must be empty. Do not substitute
   `git diff --check` for this: once the tree is clean it inspects nothing and cannot fail.

8. Confirm scope was respected with an exact-set check, not a subset check. Run
   `git diff --name-only remix...HEAD` and paste the full list. It must contain exactly:
   `py_modules/game_resolution/heroic.py`, `py_modules/tests/heroic_game_resolution_test.py`, and
   `docs/plans/2026-08-07_heroic-shortcut-validation.md`, plus
   `py_modules/tests/fixtures/heroic_game_resolution.json` only if you changed the fixture, plus
   any `docs/review/heroic-shortcut-validation-review-*.md` notes committed during review rounds.
   A missing entry means the work was not done; an extra entry means scope was exceeded. Both fail
   the step.

Deferred and explicitly not verified by this plan: on-device behavior. No step here proves the
association UI shows "Available on this Deck" for a Heroic game, because that requires building the
plugin, installing it on Steam Deck hardware, reloading Decky, and reading the live UI. That
confirmation is the user's, after this plan lands. Also not covered: whether every other
Heroic-launched shortcut on the user's device shares this exact shape — only
`Transformers Devastation` (appid `3015223078`) was measured, and the other Heroic titles are
believed but not proven to share it. Non-sideload Heroic runners (`legendary`, `gog`, `nile`) are
exercised only through existing fixtures, not against real device data.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished heroic-shortcut-validation
```

This writes:

```text
/tmp/SDH-PlayTime/heroic-shortcut-validation_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer heroic-shortcut-validation`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/heroic-shortcut-validation-review-*.md
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
   scripts/orchestration/clear-finished heroic-shortcut-validation
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
   git add docs/review/heroic-shortcut-validation-review-*.md
   git commit -m "docs(review): record heroic-shortcut-validation review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished heroic-shortcut-validation
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer heroic-shortcut-validation` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed heroic-shortcut-validation
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize heroic-shortcut-validation
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/heroic-shortcut-validation_finalized
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
scripts/orchestration/finalize heroic-shortcut-validation
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/heroic-shortcut-validation_finished
/tmp/SDH-PlayTime/heroic-shortcut-validation_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
