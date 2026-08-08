# Plan: Report drive_disconnected for GOG records with an empty executable (heroic-gog-drive-verdict)

## Context

Heroic GOG games installed on a removable drive report "Status unavailable" in the association UI
when that drive is disconnected, instead of "Drive disconnected". Measured on a Steam Deck against
the live plugin: `Assassin's Creed: Director's Cut` (`appName=1207659023`) and
`Star Wars: The Force Unleashed II` (`appName=1174280500`), both `runner=gog`, resolve to
`payload_status="unknown"`, `metadata_status="invalid"`, `reason_code="malformed"`. Their records
in Heroic's `gog_store/installed.json` carry a valid `install_path` under
`/run/media/deck/ssd_1tb/...` but an **empty** `executable` field, and that drive is genuinely
absent (`/run/media/deck/` holds only `sdcard_1tb`).

The cause is `_installed_payload` at `py_modules/game_resolution/heroic.py:546-552`, which raises
`RequestValidationError("malformed")` as soon as `executable` is empty. That happens during
metadata lookup, before any filesystem probe runs, so the drive check never executes. The
drive-disconnected machinery itself is correct and would return the right answer if reached:
`FilesystemProbe._missing_reason` (`py_modules/game_resolution/filesystem.py:109-128`) maps a
missing path to `drive_disconnected` when `_expected_removable_volume`
(`filesystem.py:171-178`) recognises the `/run/media/<user>/<volume>` shape and no mount entry
matches — and `/run/media/deck/ssd_1tb` satisfies exactly that.

Sideload records avoid this entirely because `_sideload_payload` (`heroic.py:564-568`) reads a
single absolute `install.executable`, which Heroic always populates. Non-sideload runners join
`install_path / executable`, and Heroic's GOG records routinely leave `executable` empty because it
resolves the binary at launch from files inside the install directory — which live on the absent
drive.

Intended outcome: when a non-sideload record has an empty or missing `executable` but a valid
`install_path`, resolution reaches the filesystem probe using `install_path` as the candidate, so a
disconnected removable volume yields `payload_status="unreachable"` with
`reason_code="drive_disconnected"`. Two decisions are settled and must be implemented as specified.
First, reach the verdict by probing `install_path` through the existing probe path — do not add a
new filesystem API, and do not modify `py_modules/game_resolution/filesystem.py`. Second, when the
drive **is** present and the executable is still unknown, preserve today's behavior exactly:
`payload_status="unknown"`, `metadata_status="invalid"`, `reason_code="malformed"`. Only the
disconnected case changes.

Scope is `py_modules/game_resolution/heroic.py` and its tests. Only an empty or missing
`executable` takes the new path; every other malformed cause in `_installed_payload` — a non-string
value, an absolute path, a `..` or empty path part, a backslash, or a value over 4096 characters —
must keep raising `malformed` immediately, even when the drive is disconnected, because those are
bad records rather than a drive problem. Do not change the sideload path, the flatpak or direct
adapters, `_validated_identity`, or any TypeScript. Do not add Lutris, Bottles, or EmuDeck/SRM
support. Do not introduce a directory payload kind or change what `payload_kind` means for checksum
detection.

**Working-tree precondition.** Before running Setup the repository owner must ensure the tree is
clean; at authoring time two untracked `release/*.zip` artifacts were present. The implementer must
not commit, stash, revert, or `git add` anything it did not itself create, and must stop and report
if the tree is dirty when Setup begins.

**Slug used throughout this plan:** `heroic-gog-drive-verdict`

---

## Orchestration Contract

**Slug:** `heroic-gog-drive-verdict`

**Plan file:**

```text
docs/plans/2026-08-08_heroic-gog-drive-verdict.md
```

**Implementation branch:**

```text
feat/heroic-gog-drive-verdict
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/heroic-gog-drive-verdict_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/heroic-gog-drive-verdict_finalized
```

**Review notes:**

```text
docs/review/heroic-gog-drive-verdict-review-*.md
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
git checkout -b feat/heroic-gog-drive-verdict
```

Commit this plan first:

```bash
git add docs/plans/2026-08-08_heroic-gog-drive-verdict.md
git commit -m "docs(plan): add heroic-gog-drive-verdict implementation plan"
```

---

## Implementation Tasks

Work test-first. Each behavior task must start with a failing test that demonstrates the current
wrong verdict, and you must record the observed failure output before making it pass.

1. Add a failing test for the disconnected case in `py_modules/tests/heroic_game_resolution_test.py`.
   Use a `gog` runner record whose `install_path` is under `/run/media/deck/ssd_1tb/...` and whose
   `executable` is the empty string. Drive it with a real `FilesystemProbe` constructed so the mount
   table is empty (no entry matches `/run/media/deck/ssd_1tb`), so the assertion exercises the whole
   chain — `_expected_removable_volume` recognising the `/run/media/<user>/<volume>` shape and
   `_missing_reason` finding no matching mount — rather than a stub that returns the answer. Assert
   `payload_status == "unreachable"` and `reason_code == "drive_disconnected"`. Run it and record the
   failure: it must currently fail with `payload_status="unknown"`, `metadata_status="invalid"`,
   `reason_code="malformed"`. For reference, `TogglePayloadProbe`
   (`heroic_game_resolution_test.py:54-67`) is the existing stub, injected into a coordinator at
   `heroic_game_resolution_test.py:688-691` inside the test beginning at line 677; follow that
   injection pattern, but prefer the real probe here.

2. Add a second failing test pinning the connected case to today's behavior: the same record, but
   with the toggle probe set to connected. Assert `payload_status == "unknown"`,
   `metadata_status == "invalid"`, and `reason_code == "malformed"`. This test must pass both before
   and after your change — it is the guard that stops the fix from leaking into the connected case.
   Record its result before you touch `heroic.py`.

3. Add a third failing test covering the probe outcomes neither existing helper can produce.
   `TogglePayloadProbe` emits only `drive_disconnected` or success, so nothing currently exercises
   `payload_missing`, `kind_mismatch`, `permission_denied`, or `probe_failure` on the new candidate.
   Add a small test probe that returns a caller-chosen reason code, and assert that for an
   empty-`executable` record each of those four outcomes still resolves to
   `payload_status="unknown"` / `metadata_status="invalid"` / `reason_code="malformed"` — only
   `drive_disconnected` may produce the new verdict. Without this test, an implementation that
   forwards every probe failure unchanged passes every other test in this plan while violating
   task 6.

4. In `py_modules/game_resolution/heroic.py`, make `_installed_payload` distinguish "executable is
   empty or absent" from every other malformed cause. Keep the existing validation for a non-string
   value, an absolute path, a part in `{"", ".", ".."}`, a backslash, and a length over 4096 —
   those must still raise `RequestValidationError("malformed")` from inside `_installed_payload`,
   unchanged. Signal only the empty/missing case back to the caller in a way that carries the valid
   `install_path` with it; a distinct internal exception type or a sentinel return value are both
   acceptable, but do not widen the module's public surface.

5. In `_candidates_from_data` (around `heroic.py:329`), handle that signal by building a
   `_MetadataCandidate` whose payload path is the record's `install_path`, flagged so `_probe_payload`
   can recognise it. `_MetadataCandidate` (`heroic.py:106-112`) is a frozen slots dataclass with
   exactly `runner`, `payload_path`, `install_path`, `source_root`, and `sideload` — none of which
   can carry this — so add a sixth boolean field defaulting to `False`. You must also add it to the
   key in `_deduplicate_candidates` (`heroic.py:505-519`), which currently keys on
   `(runner, payload_path, install_path, sideload)`: without that, a flagged and an unflagged
   candidate with the same paths collapse into one and the ambiguity handling is bypassed. Do not
   infer the flag from `payload_path == install_path` — `_select_payload` can legitimately produce
   that equality — and do not call `_select_payload` for this candidate, since there is no executable
   to select and the `settings`/`alternate_executable` logic does not apply.

6. In `_probe_payload` (around `heroic.py:359`), branch on that flag. When the probe reports
   `drive_disconnected`, return the existing probe-failure result so the outcome is
   `payload_status="unreachable"`, `metadata_status="resolved"`, `reason_code="drive_disconnected"`.
   For **every** other outcome on such a candidate — a successful probe, or a reason code of
   `payload_missing`, `kind_mismatch`, `permission_denied`, or `probe_failure`, or the probe itself
   raising, which `heroic.py:364-367` already converts to `probe_failure` before any reason-code
   branch — return `payload_status="unknown"`, `metadata_status="invalid"`, `reason_code="malformed"`,
   matching today's behavior exactly. A connected drive must never yield `reachable` for a record with
   no executable.

7. Make the tests from tasks 1, 2, and 3 pass without weakening any of them. Confirm the recorded
   `malformed` output for the disconnected case is gone and the connected case is untouched.

8. Add regression tests proving the other malformed causes are unaffected. With the probe in its
   disconnected state — the state that would otherwise produce the new verdict — assert that a
   record whose `executable` is an absolute path, one containing `..`, one containing a backslash,
   and one that is a non-string value each still resolve to `reason_code="malformed"` and never to
   `drive_disconnected`. These fail if the new branch is applied too broadly.

9. Add a regression test that a `sideload` record is entirely unaffected: an existing sideload
   fixture must still resolve exactly as it does today.

10. Do not modify `py_modules/game_resolution/filesystem.py`, any TypeScript source, or any other
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

1. Record the red state. Before touching `heroic.py`, run
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest py_modules.tests.heroic_game_resolution_test` and
   paste the output. The task-1 test must fail, and the recorded values must be
   `payload_status="unknown"` / `metadata_status="invalid"` / `reason_code="malformed"`. The task-2
   test must already pass. If task 1 passes before the fix exists, it is not exercising the defect —
   rewrite it before continuing.

2. State the before and after triple (`payload_status`, `metadata_status`, `reason_code`) for both
   the disconnected and the connected case. The disconnected one must change from
   `unknown/invalid/malformed` to exactly `unreachable/resolved/drive_disconnected`; the connected one must
   be byte-identical before and after. A connected case that changed is a regression, not a fix.

3. Mutation-test the implementation, reverting each mutation before the next, and paste the failing
   output for each. (a) Make the new branch fire for every `RequestValidationError` rather than only
   the empty-executable signal, and confirm at least one task-8 regression test goes red. (b) Make
   `_probe_payload` return the probe result unfiltered for the new candidate, and confirm the task-2
   connected-case test goes red because a connected drive now reports `reachable` instead of
   `malformed`. (c) Make `_probe_payload` forward **every** probe failure on a flagged candidate to
   `_result_from_probe_failure`, not just `drive_disconnected`, and confirm a task-3 test goes red —
   this is the mutation that a plan without task 3 would miss entirely, because it passes every other
   test here. If any mutation leaves the suite green, the corresponding test is not covering its
   behavior and must be strengthened.

4. Prove the sideload path is untouched: run the pre-existing sideload tests and paste the tally.
   Then mutate `_candidates_from_data` so the sideload arm (`heroic.py:327-328`) also builds a
   flagged candidate, confirm those sideload tests go red, and paste the failure. Revert it.

5. Negative control, run after steps 1-4 with all mutations reverted: run both Python suites and
   paste the pass/fail tallies —
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s py_modules/tests -p '*_test.py'` and
   `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_*.py'`. Both must be
   green with no skipped Heroic tests.

6. Run `scripts/orchestration/run-quality-gates` and paste its final result line, then run
   `git status --short` and paste its output, which must be empty. Do not substitute
   `git diff --check`: once the tree is clean it inspects nothing and cannot fail.

7. Confirm scope with an exact-set check, not a subset check. Run
   `git diff --name-only remix...HEAD` and paste the full list. It must contain exactly
   `py_modules/game_resolution/heroic.py`, `py_modules/tests/heroic_game_resolution_test.py`, and
   `docs/plans/2026-08-08_heroic-gog-drive-verdict.md`, plus
   `py_modules/tests/fixtures/heroic_game_resolution.json` only if you changed the fixture, plus any
   `docs/review/heroic-gog-drive-verdict-review-*.md` committed during review rounds. A missing entry
   means the work was not done; an extra entry means scope was exceeded. Both fail the step.
   `py_modules/game_resolution/filesystem.py` appearing in that list is an automatic failure.

Deferred and explicitly not verified by this plan: on-device behavior. No step here proves the
association UI shows "Drive disconnected" for a GOG game on an absent drive — that needs a build,
an install, a Decky reload, and the external drive physically detached. That confirmation is the
user's, after this plan lands. Also not verified: the connected-drive outcome for these specific
records, since the drive was absent when the defect was measured and no observation of these games
with the drive attached exists. Because the flagged candidate skips `_select_payload`, a `targetExe`
override in `GamesConfig/<appId>.json` is deliberately ignored for these records; no test covers a
record that has both an empty `executable` and a `targetExe`, and none of the measured records had
one. Whether Heroic ever populates `executable` for GOG records under other install flows is
likewise unknown — the fix deliberately keeps `malformed` for that state
rather than guessing. Epic (`legendary`) and Amazon (`nile`) records were not exercised at all;
both their `installed.json` files are absent on the measured device, so those runners return
`missing`/`not_found` through a different path and are untouched by this change.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished heroic-gog-drive-verdict
```

This writes:

```text
/tmp/SDH-PlayTime/heroic-gog-drive-verdict_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer heroic-gog-drive-verdict`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/heroic-gog-drive-verdict-review-*.md
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
   scripts/orchestration/clear-finished heroic-gog-drive-verdict
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
   git add docs/review/heroic-gog-drive-verdict-review-*.md
   git commit -m "docs(review): record heroic-gog-drive-verdict review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished heroic-gog-drive-verdict
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer heroic-gog-drive-verdict` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed heroic-gog-drive-verdict
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize heroic-gog-drive-verdict
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/heroic-gog-drive-verdict_finalized
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
scripts/orchestration/finalize heroic-gog-drive-verdict
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/heroic-gog-drive-verdict_finished
/tmp/SDH-PlayTime/heroic-gog-drive-verdict_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
