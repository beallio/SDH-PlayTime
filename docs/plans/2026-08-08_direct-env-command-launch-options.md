# Plan: Accept env-prefixed %command% launch options for direct shortcuts (direct-env-command-launch-options)

## Context

Non-Steam shortcuts that Steam launches directly through a Proton prefix report
"Status unavailable" in the association UI even though the game is installed and its `.exe`
is present on a mounted drive. Measured on a Steam Deck on 2026-08-08 against plugin version
`3.3.1-beallio.11`, two real shortcuts have this shape:

| Game | Steam appid | `strShortcutLaunchOptions` |
| --- | --- | --- |
| Transformers Fall of Cybertron | `3276984150` | `STEAM_COMPAT_DATA_PATH="/run/media/deck/sdcard_1tb/heroic/prefixes/default/Transformers Fall of Cybertron" %command%` |
| X-Men Origins Wolverine | (non-Steam shortcut) | `STEAM_COMPAT_DATA_PATH="/run/media/deck/sdcard_1tb/heroic/prefixes/default/X-Men Origins Wolverine" %command%` |

Their `strShortcutExe` is a single quoted absolute `.exe` path — for Fall of Cybertron,
`"/run/media/deck/sdcard_1tb/heroic/prefixes/default/Transformers Fall of Cybertron/drive_c/Program Files (x86)/Transformers Fall of Cybertron/Binaries/TFOC.exe"`.

**The frontend is not at fault and no TypeScript change is in scope.** Running the real
`classifyShortcutEvidence` against these values returns `status: "recognized"`,
`launcherKind: "direct"`. Measured token output for the Fall of Cybertron shortcut:

```json
"executableTokens": ["/run/media/deck/.../Binaries/TFOC.exe"],
"launchOptionTokens": [
  "STEAM_COMPAT_DATA_PATH=/run/media/deck/sdcard_1tb/heroic/prefixes/default/Transformers Fall of Cybertron",
  "%command%"
],
"commandTokens": ["/run/media/deck/.../Binaries/TFOC.exe", "STEAM_COMPAT_DATA_PATH=/run/...", "%command%"]
```

Note the tokenizer strips the quotes inside the assignment, so the whole
`KEY=/path with spaces` is a single token.

Two independent backend gates reject that shape:

1. `DirectExecutableAdapter._validated_candidate`
   (`py_modules/game_resolution/direct.py:287-303`) raises `RequestValidationError("malformed")`
   when `normalized.launch_option_tokens` is non-empty, when
   `normalized.shortcut_launch_options is not None`, or when `command_tokens != (candidate,)`.
   All three trip here. This is the gate the live frontend hits: the measured on-device
   snapshot for `3276984150` is
   `{"source":"non_steam","launcherKind":"direct","inventory":{"status":"current"},"availability":{"status":"unknown","reasons":[{"code":"malformed","source":"resolver"}]}}`.
2. `_request_from_record` (`py_modules/game_resolution/steam_shortcuts.py:277-284`) takes the
   `direct` branch only when `not launch_tokens`, so it returns `None` and the shortcut is
   never eligible for the VDF/checksum path either.

### Settled decisions

Both are settled and must be implemented as specified; do not substitute your own judgement:

1. **Any valid environment-variable name is accepted**, not an allowlist. A leading token is
   an environment assignment when it matches `^[A-Za-z_][A-Za-z0-9_]*=` — this covers
   `STEAM_COMPAT_DATA_PATH`, `PROTON_*`, `MANGOHUD`, `DXVK_*`. The executable itself is still
   fully validated, so this grants no new trust.
2. **Tokens after `%command%` are allowed.** `ENV=v %command% -nointro -windowed` must
   resolve. `%command%` itself is still required to be present exactly once.

### Intended outcome

`DirectExecutableAdapter` resolves a direct shortcut whose launch options are zero or more
leading environment assignments, then exactly one `%command%`, then any number of trailing
argument tokens — returning `payload_status="reachable"` with the `.exe` path when the
payload is present. `_request_from_record` marks the same shape eligible as `direct`.

### What must not be weakened

The executable must still be a single literal absolute path, still equal to the sole entry
in `executable_tokens`. `command_tokens` must still be exactly
`executable_tokens + launch_option_tokens`. `flatpak_app_id` must still be absent. The
start-directory rule, `_is_rejected_path`, `_direct_payload_type`, and
`_has_direct_payload_evidence` must all keep working exactly as they do now — a shortcut
pointing at a launcher, wrapper, Proton, or a `/usr/bin`-style system path must still be
rejected, and a missing payload must still be `unreachable`, not `reachable`.

### Out of scope

Do not modify any TypeScript. Do not touch `HeroicAdapter`, `FlatpakExecutableAdapter`, or
the Heroic/Lutris/Bottles classifiers. Do not add Lutris, Bottles, or EmuDeck support. Do not
bump the plugin version or cut a release — that is a separate step the user performs after
this lands.

### Working-tree precondition

At authoring time the only uncommitted path was an untracked `uv.lock`. Per `AGENTS.md` §3 it
is user-owned and out of scope: do not commit, stage, stash, or delete it. Stop and report if
any other tracked modification is present when Setup begins.

**Slug used throughout this plan:** `direct-env-command-launch-options`

---

## Orchestration Contract

**Slug:** `direct-env-command-launch-options`

**Plan file:**

```text
docs/plans/2026-08-08_direct-env-command-launch-options.md
```

**Implementation branch:**

```text
feat/direct-env-command-launch-options
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/direct-env-command-launch-options_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/direct-env-command-launch-options_finalized
```

**Review notes:**

```text
docs/review/direct-env-command-launch-options-review-*.md
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
git checkout -b feat/direct-env-command-launch-options
```

Commit this plan first:

```bash
git add docs/plans/2026-08-08_direct-env-command-launch-options.md
git commit -m "docs(plan): add direct-env-command-launch-options implementation plan"
```

---

## Implementation Tasks

Files you may modify. Any other path is out of scope:

```text
py_modules/game_resolution/direct.py
py_modules/game_resolution/steam_shortcuts.py
py_modules/tests/game_resolution_test.py
py_modules/tests/steam_shortcuts_test.py
docs/plans/2026-08-08_direct-env-command-launch-options.md
```

Read the existing tests in those two test files before writing new ones, and follow their
established fixture and helper style rather than inventing a new one.

### Task 1 — Add the shared launch-option parser

Add one helper, used by both gates so they cannot drift apart. Put it in
`py_modules/game_resolution/direct.py` and import it from `steam_shortcuts.py` (that module
already imports `_direct_payload_type` and `_has_direct_payload_evidence` from `direct.py`,
so the dependency direction is established).

```python
_ENVIRONMENT_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _direct_launch_options_accepted(tokens: tuple[str, ...]) -> bool:
    """Return True for zero or more env assignments, then one %command%, then any args.

    An empty tuple is accepted: a shortcut with no launch options at all is the
    pre-existing supported shape.
    """
    if not tokens:
        return True
    index = 0
    while index < len(tokens) and _ENVIRONMENT_ASSIGNMENT.match(tokens[index]):
        index += 1
    if index >= len(tokens) or tokens[index] != "%command%":
        return False
    return "%command%" not in tokens[index + 1 :]
```

Requirements this encodes, all of which must hold:

- zero env assignments is fine (`%command%` alone is accepted);
- a token before `%command%` that is not an env assignment rejects the shortcut;
- `%command%` must appear exactly once;
- trailing tokens after `%command%` are unrestricted except that none may be `%command%`;
- launch options with no `%command%` at all are rejected.

### Task 2 — Relax `DirectExecutableAdapter._validated_candidate` (RED first)

Before editing `direct.py`, add failing tests to `py_modules/tests/game_resolution_test.py`
covering the measured shortcut. Use the exact Fall of Cybertron values from Context. Assert
`payload_status == "reachable"` and that `payload_path` is the `.exe`.

Run the focused suite and record the output; the new test **must fail** with
`reason_code == "malformed"` before the fix. If it does not fail, the test is not exercising
the gate — fix the test first.

Then in `_validated_candidate` (`direct.py:287-303`) replace the launch-option rejection so
it:

- still requires `normalized.flatpak_app_id is None`;
- still requires `normalized.executable_tokens == (candidate,)`;
- requires `normalized.command_tokens == (candidate, *normalized.launch_option_tokens)`
  instead of `== (candidate,)`;
- requires `_direct_launch_options_accepted(normalized.launch_option_tokens)`;
- drops the `normalized.shortcut_launch_options is not None` rejection, but still rejects
  when `shortcut_launch_options` is `None` while `launch_option_tokens` is non-empty, and
  when it is a non-empty string while `launch_option_tokens` is empty — the two must agree;
- leaves the start-directory comparison exactly as it is.

### Task 3 — Relax the `_request_from_record` direct branch

In `py_modules/game_resolution/steam_shortcuts.py:277-284`, replace the `not launch_tokens`
condition with `_direct_launch_options_accepted(normalized.launch_option_tokens)`. Keep
`flatpak_app_id is None`, `len(executable_tokens) == 1`, and `len(start_dir_tokens) <= 1`
unchanged. Keep this branch below the Heroic and flatpak branches so their precedence is
unchanged.

### Task 4 — Cover the rejection cases

Add tests to `py_modules/tests/game_resolution_test.py` for shapes that must **stay**
rejected or unreachable. Each needs its own assertion:

| Launch options | Expected |
| --- | --- |
| `STEAM_COMPAT_DATA_PATH="/p" %command%` on a payload that does not exist | `unreachable`, not `reachable` |
| `STEAM_COMPAT_DATA_PATH="/p" %command%` with exe `/usr/bin/foo` | still rejected by `_is_rejected_path` |
| `--flag %command%` (leading non-assignment token) | `malformed` |
| `STEAM_COMPAT_DATA_PATH="/p"` (no `%command%`) | `malformed` |
| `%command% %command%` | `malformed` |
| `ENV=1 %command% -nointro -windowed` | `reachable` |
| `%command%` alone | `reachable` |
| no launch options at all | `reachable` (pre-existing behavior, must not regress) |

Add a matching pair to `py_modules/tests/steam_shortcuts_test.py`: a VDF record with the
measured Fall of Cybertron shape yields a `direct` `ResolutionRequest`, and a record with
`--flag %command%` still yields `None`.

### Task 5 — Confirm no TypeScript change is needed

Do not edit any `.ts`/`.tsx` file. The frontend already classifies all these shapes as
`recognized` / `direct`; this was measured before the plan was written. If you believe a
frontend change is required, stop and report rather than making one.

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

Verification steps follow `references/verification-standards.md` in the
`orchestration-plan-author` skill. Report captured output and tallies, not conclusions. Run
from the repository root with `set -o pipefail` in effect for any pipeline.

### 1. Record the RED evidence

Paste the failing output captured in Task 2, before the `direct.py` change. It must show the
Fall of Cybertron test failing with `reason_code == "malformed"`. A missing RED record fails
this step; so does a record showing the test passing before the fix.

### 2. Focused suites

```bash
uv run --no-project --with pytest pytest py_modules/tests/game_resolution_test.py \
  py_modules/tests/steam_shortcuts_test.py
```

Record the pass/fail tallies. Any failure fails this step.

### 3. Mutation control — the parser is load-bearing

Temporarily make `_direct_launch_options_accepted` unconditionally permissive:

```python
def _direct_launch_options_accepted(tokens: tuple[str, ...]) -> bool:
    return True
```

Run the focused suites again. The `--flag %command%`, the no-`%command%`, and the
`%command% %command%` cases **must fail**. Record the failing test names, then revert the
mutation and re-run to confirm green.

If the suites stay green under this mutation, the rejection cases are not being exercised.

### 4. Mutation control — the fix is load-bearing

Temporarily restore the original rejection in `_validated_candidate` by re-adding:

```python
            or normalized.launch_option_tokens
```

Run the focused suites. The Fall of Cybertron test and the trailing-args test **must fail**.
Record the failing names, then revert and confirm green.

### 5. Scope check

```bash
git diff --name-only remix...HEAD
```

Paste the full list. It must contain exactly:

```text
docs/plans/2026-08-08_direct-env-command-launch-options.md
py_modules/game_resolution/direct.py
py_modules/game_resolution/steam_shortcuts.py
py_modules/tests/game_resolution_test.py
py_modules/tests/steam_shortcuts_test.py
```

plus any `docs/review/direct-env-command-launch-options-review-*.md` note committed during a
review round. No `.ts`/`.tsx` file may appear. `uv.lock` must not appear. A missing entry
means the work was not done; an extra entry means scope was exceeded.

### 6. Full quality gates

```bash
scripts/orchestration/run-quality-gates
```

Record the exit status and the tail of the output. A non-zero exit fails this step.

### 7. Negative control (run last)

Runs after every failure case above, including both mutation reverts, so it cannot pass by
not having been exercised. Steps 3 and 4 already proved these tests can go red.

Re-run only the decisive tests by name, capturing each exit status in its own assignment
rather than through a pipeline:

```bash
uv run --no-project --with pytest pytest py_modules/tests/game_resolution_test.py \
  -k "fall_of_cybertron or trailing_args or rejects_non_assignment"
focused_status=$?

if [[ "$focused_status" -eq 0 ]]; then
	printf 'NEGATIVE CONTROL: PASS\n'
else
	printf 'NEGATIVE CONTROL: FAIL status=%s\n' "$focused_status"
	exit 1
fi
```

Substitute the real test names you used. Paste the full pytest output, not just the last
line: a `-k` filter that matches nothing reports `no tests ran` and can still exit 0 on some
configurations, so the collected count is the evidence. If it reports zero collected tests,
the filter is wrong and this step fails.

### Deferred and explicitly not verified

- **On-device behavior.** No step here proves the association UI shows
  "Available on this Deck" for Transformers Fall of Cybertron or X-Men Origins Wolverine.
  That needs a build, an install on Steam Deck hardware, a Decky reload, and a look at the
  live UI. That confirmation is the user's, after this plan lands.
- **X-Men Origins Wolverine specifically.** Only the Fall of Cybertron shortcut's exact
  token output was measured. Wolverine is believed to share the shape but was not captured
  token-by-token.
- **Real-world env-var variety.** Only `STEAM_COMPAT_DATA_PATH` was observed on device.
  `PROTON_*`, `MANGOHUD`, and friends are covered by the regex and by synthetic tests, not by
  measured shortcuts.
- **Trailing arguments.** No measured shortcut on the device has arguments after
  `%command%`; that support is covered by synthetic tests only.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished direct-env-command-launch-options
```

This writes:

```text
/tmp/SDH-PlayTime/direct-env-command-launch-options_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer direct-env-command-launch-options`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/direct-env-command-launch-options-review-*.md
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
   scripts/orchestration/clear-finished direct-env-command-launch-options
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
   git add docs/review/direct-env-command-launch-options-review-*.md
   git commit -m "docs(review): record direct-env-command-launch-options review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished direct-env-command-launch-options
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer direct-env-command-launch-options` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed direct-env-command-launch-options
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize direct-env-command-launch-options
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/direct-env-command-launch-options_finalized
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
scripts/orchestration/finalize direct-env-command-launch-options
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/direct-env-command-launch-options_finished
/tmp/SDH-PlayTime/direct-env-command-launch-options_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
