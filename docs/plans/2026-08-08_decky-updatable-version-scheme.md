# Plan: Migrate remix versions to a Decky-updatable prerelease scheme (decky-updatable-version-scheme)

## Context

### The defect

Decky Loader never offers a remix update, because every remix release so far
encodes its identity in SemVer **build metadata** (`3.3.0+beallio.10`), and
Decky's updater discards build metadata.

Decky's `checkForPluginUpdates` (upstream `decky-loader`,
`frontend/src/store.tsx`) gates an update on:

```ts
plugin.version != remotePlugin.versions[0].name &&
validate(remotePlugin.versions[0].name) && validate(curVer) &&
compare(remotePlugin.versions[0].name, curVer, '>')
```

`compare` and `validate` come from the `compare-versions` package, whose parser
matches build metadata in a **non-capturing** group that never participates in
precedence. Measured against `compare-versions` 6.1.1:

```text
3.3.0+beallio.11        vs 3.3.0+beallio.10  -> 0   (gt = false)
3.3.0+beallio.g1a2b3c4  vs 3.3.0+beallio.10  -> 0   (gt = false)
3.4.0+beallio.1         vs 3.3.0+beallio.10  -> 1   (gt = true)
```

So the string-inequality test passes, the `compare(..., '>')` test fails, and the
plugin is dropped from the update map. Every release from `beallio.1` through
`beallio.10`, and every `+beallio.g<sha>` nightly, is invisible to the updater.
This is independent of which store URL is configured — a custom store URL
changes only where the feed is fetched from, not how versions are compared.

### The fix

Move the remix counter into the **prerelease** field, which does participate in
precedence, and forbid build metadata outright.

- Stable: `3.3.1-beallio.11` (this migration's target version).
- Nightly / PR: the stable version suffixed with `.dev.<UTC YYYYMMDD>.g<short_sha>`,
  e.g. `3.3.1-beallio.11.dev.20260808.g1a2b3c4`.

Precedence measured against `compare-versions` 6.1.1 — these are the expected
values the new tests must encode:

```text
3.3.1-beallio.11                       vs 3.3.0                ->  1
3.3.1-beallio.11                       vs 3.3.0+beallio.10     ->  1
3.3.1-beallio.12                       vs 3.3.1-beallio.11     ->  1
3.3.1-beallio.2                        vs 3.3.1-beallio.11     -> -1
3.3.1                                  vs 3.3.1-beallio.11     ->  1
3.3.1-beallio.11.dev.20260808.g1a2b3c4 vs 3.3.1-beallio.11     ->  1
3.3.1-beallio.12                       vs 3.3.1-beallio.11.dev.20260808.g1a2b3c4 ->  1
3.3.1-beallio.11.dev.20260809.g9f8e7d6 vs 3.3.1-beallio.11.dev.20260808.g1a2b3c4 ->  1
3.3.0+beallio.11                       vs 3.3.0+beallio.10     ->  0   (the defect)
```

`3.3.1-beallio.N` places remix builds above upstream `3.3.0` and below a future
upstream `3.3.1`, which is the intended semantic.

### Relevant files

| File | Role |
| --- | --- |
| `package.json`, `plugin.json` | The two hand-edited version sources; must stay byte-identical. |
| `.github/workflows/remix-release.yml` | Tag trigger glob (line 6) and the `Derive release metadata` step (lines 130-171). |
| `tests/test_remix_workflow.py` | Pins the workflow contract as string assertions; lines 17 and 86 encode the old scheme. |
| `README.md` lines 20, 34-35 | User-facing example tag and asset names in the in-place upgrade snippet. |
| `CHANGELOG.md` | Needs an additive entry; do not rewrite the upstream `## [3.3.0]` heading. |
| `DEVELOPER.md` | Maintainer release mechanics; `AGENTS.md:207-211` requires release-policy changes to be documented here. |

`tools/release_archive.py` performs **no** version parsing — it only rejects an
empty or space-padded version and then compares the string for equality against
the embedded manifests. It needs no change. Frontend code (`rollup.config.js:14`,
`src/app/settings.ts`) treats the version as an opaque string. No change there.

### Explicitly out of scope

- Creating a custom Decky store feed JSON. None exists in this repo, and
  `README.md:18` states the remix ships through GitHub Releases only. This plan
  makes the version string *capable* of driving an update; it does not stand up
  a feed.
- Retagging, deleting, or republishing the existing `v3.3.0+beallio.1` …
  `v3.3.0+beallio.10` releases. They stay as historical records.
- The upstream `master` workflows (`build-merge-request.yml`,
  `create-nightly-release.yml`, `release-on-master-push.yml`). They read
  `package.json` generically and contain no remix version literals.
- Creating or pushing the `v3.3.1-beallio.11` tag. This plan lands the scheme on
  `remix`; tagging is a separate, human-gated release action.

**Slug used throughout this plan:** `decky-updatable-version-scheme`

---

## Orchestration Contract

**Slug:** `decky-updatable-version-scheme`

**Plan file:**

```text
docs/plans/2026-08-08_decky-updatable-version-scheme.md
```

**Implementation branch:**

```text
feat/decky-updatable-version-scheme
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/decky-updatable-version-scheme_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/decky-updatable-version-scheme_finalized
```

**Review notes:**

```text
docs/review/decky-updatable-version-scheme-review-*.md
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
git checkout -b feat/decky-updatable-version-scheme
```

Commit this plan first:

```bash
git add docs/plans/2026-08-08_decky-updatable-version-scheme.md
git commit -m "docs(plan): add decky-updatable-version-scheme implementation plan"
```

---

## Implementation Tasks

Work in order. Tasks 1 and 2 are the RED step: both new test modules must exist
and fail before any production file changes.

### Task 1 — Add `tests/test_version_scheme.py` (RED)

New module. It owns the precedence rule itself, independent of the workflow.

1. Implement a module-level helper `semver_precedence(a: str, b: str) -> int`
   returning `-1 | 0 | 1`, following SemVer 2.0 §11: compare major/minor/patch
   numerically; **ignore build metadata entirely** (everything from the first
   `+`); a version with a prerelease is lower than the same version without one;
   compare prerelease identifiers left to right, numeric identifiers compare
   numerically and rank below alphanumeric ones, and a longer identifier list
   wins when all preceding identifiers are equal.

2. `test_comparator_matches_compare_versions_6_1_1` — a fidelity table. Assert
   `semver_precedence` returns exactly the values in the Context table above,
   for all nine rows including the `3.3.0+beallio.11` vs `3.3.0+beallio.10` -> `0`
   row. This row is what makes the comparator faithful to Decky's behaviour
   rather than to intuition; without it the whole module is untrustworthy.

3. `test_manifest_versions_agree` — read `package.json` and `plugin.json` from
   the repo root, assert both `version` values are equal, and assert the value
   is exactly `3.3.1-beallio.11`.

4. `test_manifest_version_carries_no_build_metadata` — assert `"+" not in version`.
   Failure message must name the reason: Decky's `compare-versions` ignores build
   metadata, so a `+` suffix can never trigger an update.

5. `test_manifest_version_supersedes_every_published_remix_tag` — for each of
   `3.3.0`, `3.3.0+beallio.1`, and `3.3.0+beallio.10`, assert
   `semver_precedence(manifest_version, published) == 1`.

6. `test_derived_nightly_orders_between_this_release_and_the_next` — build
   `nightly = f"{manifest_version}.dev.20260808.g1a2b3c4"` and assert
   `semver_precedence(nightly, manifest_version) == 1` and
   `semver_precedence("3.3.1-beallio.12", nightly) == 1`.

Run it now and record the failures. Expect at minimum failures in tests 3, 4 and
5 because the manifests still read `3.3.0+beallio.10`:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_version_scheme
```

### Task 2 — Add `tests/test_remix_workflow_metadata.py` (RED)

New module. It executes the workflow's version-derivation shell rather than
grepping it, so it fails when the derivation is wrong and not merely when its
text changes.

1. Load `.github/workflows/remix-release.yml` with the vendored safe YAML loader
   (see `tests/test_vendored_safe_yaml.py` for the import pattern already used in
   this repo). Select the step under `jobs.package.steps` whose `name` is
   `Derive release metadata` and take its `run` string. If no such step exists,
   fail with an explicit message — do not skip (an absent precondition must be a
   failure, not a pass).

2. Add a `_run(env)` helper that:
   - fails loudly with a named message if `shutil.which("bash")` or
     `shutil.which("node")` is `None`; **never** `skipTest` on a missing tool;
   - writes the `run` string to a temp file;
   - creates a temp `bin/` containing an executable `git` stub that prints
     `1a2b3c4` for any argument list, and prepends it to `PATH`;
   - points `GITHUB_OUTPUT` at a temp file;
   - executes `bash <script>` with `cwd` set to the repo root, capturing
     stdout, stderr and the return code;
   - parses the `GITHUB_OUTPUT` file into a dict and returns
     `(returncode, stdout + stderr, outputs)`.

3. Cases, each asserting on the exact `version` and `asset_name` outputs:

   | Env | Expected `version` | Expected `asset_name` |
   | --- | --- | --- |
   | `GITHUB_EVENT_NAME=push`, `GITHUB_REF_TYPE=tag`, `GITHUB_REF_NAME=v3.3.1-beallio.11` | `3.3.1-beallio.11` | `SDH-PlayTime-beallio-remix-v3.3.1-beallio.11.zip` |
   | `GITHUB_EVENT_NAME=push`, `GITHUB_REF_TYPE=branch`, `GITHUB_REF_NAME=remix` | `3.3.1-beallio.11.dev.<UTC date>.g1a2b3c4` | `SDH-PlayTime-beallio-remix-nightly.zip` |
   | `GITHUB_EVENT_NAME=pull_request`, `GITHUB_REF_TYPE=branch` | `3.3.1-beallio.11.dev.<UTC date>.g1a2b3c4` | `SDH-PlayTime-beallio-remix-pr-1a2b3c4.zip` |
   | `GITHUB_EVENT_NAME=workflow_dispatch`, `DISPATCH_VERSION=` | `3.3.1-beallio.11` | `SDH-PlayTime-beallio-remix-manual-3.3.1-beallio.11.zip` |

   For `<UTC date>`: capture `datetime.now(timezone.utc).strftime("%Y%m%d")`
   both immediately before and immediately after `_run`, and assert the observed
   version equals the expected string built from one of those two values. This
   removes the midnight race without weakening the assertion to a substring match.

4. `test_tag_version_must_match_the_manifests` — tag event with
   `GITHUB_REF_NAME=v9.9.9`; assert return code `1` **and** that the combined
   output contains the exact string
   `Tag version must exactly match package.json and plugin.json.`
   Asserting non-zero alone is not enough: a missing interpreter also exits
   non-zero with no output.

5. `test_build_metadata_in_the_manifest_is_rejected` — copy the repo to a temp
   dir (or write temp `package.json`/`plugin.json` into an isolated cwd holding
   only those two files, which is all the step reads), set both versions to
   `3.3.0+beallio.11`, run the step, and assert return code `1` **and** that the
   output contains the exact guard message from Task 3 step 2. This is the test
   that would have caught the original defect.

6. `test_mismatched_manifests_are_rejected_on_every_event` — same isolated-cwd
   technique, `package.json` at `3.3.1-beallio.11` and `plugin.json` at
   `3.3.1-beallio.12`, `GITHUB_EVENT_NAME=push` on a branch; assert return code
   `1` and the exact mismatch message from Task 3 step 3.

Run it and record the failures:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_remix_workflow_metadata
```

### Task 3 — Rewrite the workflow's version derivation (GREEN)

Edit `.github/workflows/remix-release.yml`.

1. Line 6, the tag trigger. Replace:

   ```yaml
       tags: ['v*\+beallio.*']
   ```

   with:

   ```yaml
       tags: ['v*-beallio.*']
   ```

   The `\+` escape existed only because `+` needed escaping in GitHub's tag
   filter glob (see `docs/review/independent-remix-task-02.md:30`); `-` is not a
   glob metacharacter and must not be escaped.

2. In the `Derive release metadata` step, immediately after the two
   `checked_*_version` assignments and **before** the event dispatch, add the
   build-metadata guard:

   ```bash
             case "$checked_package_version" in
               *+*)
                 echo "Remix versions must not use SemVer build metadata: Decky ignores it when comparing versions."
                 exit 1
                 ;;
             esac
   ```

3. Directly after that guard, add the cross-manifest equality guard so it applies
   on every event, not only on tags:

   ```bash
             if [ "$checked_package_version" != "$checked_plugin_version" ]; then
               echo "package.json and plugin.json versions must be identical."
               exit 1
             fi
   ```

   Leave the existing tag-versus-manifest check inside the tag branch as is.

4. Replace both `base_version` branches (current lines 149-157). `base_version`
   and its `${...%%+*}` expansion are deleted outright — with a prerelease
   scheme there is nothing to strip and the nightly must extend the stable
   version, not truncate it:

   ```bash
             elif [ "$GITHUB_EVENT_NAME" = 'push' ]; then
               build_date="$(date -u +%Y%m%d)"
               version="${checked_package_version}.dev.${build_date}.g${short_sha}"
               asset_name='SDH-PlayTime-beallio-remix-nightly.zip'
             else
               build_date="$(date -u +%Y%m%d)"
               version="${checked_package_version}.dev.${build_date}.g${short_sha}"
               asset_name="SDH-PlayTime-beallio-remix-pr-${short_sha}.zip"
             fi
   ```

   `build_date` is assigned on its own line so a `date` failure propagates
   instead of being swallowed by a larger successful command.

5. Leave the `case "$version" in '' | *[!0-9A-Za-z.+-]*)` safety check unchanged —
   its character class already permits `-` and `.`.

6. Leave `publish-stable-release`'s
   `startsWith(github.ref, 'refs/tags/v')` condition unchanged.

### Task 4 — Bump the manifests (GREEN)

Set `"version": "3.3.1-beallio.11"` in **both** `package.json` (line 3) and
`plugin.json` (line 3). Change nothing else in either file — in particular do not
reformat `plugin.json`, which is tab-indented.

Tasks 1 and 2 must now pass. Run both and record the tallies.

### Task 5 — Update `tests/test_remix_workflow.py`

1. Line 17: `self.assertIn("tags: ['v*\\+beallio.*']", WORKFLOW)` becomes
   `self.assertIn("tags: ['v*-beallio.*']", WORKFLOW)`.
2. Line 86: `self.assertIn('version="${base_version}+beallio.g${short_sha}"', WORKFLOW)`
   becomes
   `self.assertIn('version="${checked_package_version}.dev.${build_date}.g${short_sha}"', WORKFLOW)`.
3. In the same test, add `self.assertNotIn("base_version", WORKFLOW)` so the
   deleted truncating expansion cannot silently return.
4. Add a new test `test_the_workflow_rejects_build_metadata_versions` asserting
   the workflow text contains `*+*)` and the exact guard message string from
   Task 3 step 2.

These are text assertions on a YAML file; they prove the workflow *says* the
right thing. Task 2 is what proves it *does* the right thing.

### Task 6 — Update fixture version strings in existing tests

In `tests/test_release_archive.py` replace the opaque fixture literal
`3.3.0+beallio.1` with `3.3.1-beallio.11` at every occurrence (lines 124, 178,
185, 188, 191, 198, 206, 209, 219, 222, 231, 234, 263, 266, 282, 285, the loop at
347/355, and 362). In `tests/test_vendored_safe_yaml.py:52` replace
`3.3.0+beallio.vendor-test` with `3.3.1-beallio.vendor-test`. Nothing in either
module asserts on version *format*, so behaviour must not change — if any
assertion in these two modules changes meaning, stop and record why in the
session log rather than adjusting the expectation.

### Task 7 — Documentation

1. `README.md` line 20: change the example tag and asset to
   `v3.3.1-beallio.11` and `SDH-PlayTime-beallio-remix-v3.3.1-beallio.11.zip`,
   updating the release-tag URL to match.
2. `README.md` lines 34-35: `RELEASE_TAG='v3.3.1-beallio.11'` and
   `ARCHIVE_NAME='SDH-PlayTime-beallio-remix-v3.3.1-beallio.11.zip'`.
3. `CHANGELOG.md`: add a new `## [3.3.1-beallio.11] - 2026-08-08` section above
   the existing `## [3.3.0] - 2026-07-16` heading, recording the version-scheme
   migration and that it is what makes Decky offer remix updates. Do not modify
   the `3.3.0` section.
4. `DEVELOPER.md`: add a short **Remix version scheme** subsection near the
   existing release-archive material stating: stable versions are
   `MAJOR.MINOR.PATCH-beallio.N`; build metadata (`+`) is forbidden and CI
   rejects it; nightly and PR versions are the stable version plus
   `.dev.<UTC YYYYMMDD>.g<short_sha>`; the reason is that Decky Loader compares
   with `compare-versions`, which ignores build metadata. Reference
   `tests/test_version_scheme.py` as the executable statement of the rule.

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

All steps must satisfy `references/verification-standards.md` in the
`orchestration-plan-author` skill. Report actual command output and tallies, not
conclusions. Run the steps in the order given: the mutation steps come first so
the gates are proven able to fail before V6-V8 are trusted.

Use `set -o pipefail` in any step that pipes, and restore every mutated file with
`git checkout --` before moving to the next step. Run `git status --short` after
each restore and record it; a non-empty tree at that point means a mutation was
left behind.

### V1 — Focused suites pass

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v \
  tests.test_version_scheme \
  tests.test_remix_workflow_metadata \
  tests.test_remix_workflow \
  tests.test_release_archive \
  tests.test_vendored_safe_yaml
```

Record the ran/failed/errored counts verbatim.

### V2 — Mutation: the old version scheme must go red

```bash
sed -i 's/3\.3\.1-beallio\.11/3.3.0+beallio.11/' package.json plugin.json
git diff --quiet -- package.json plugin.json; echo "mutation_applied_expect_1=$?"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_version_scheme; echo "exit=$?"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_remix_workflow_metadata; echo "exit=$?"
git checkout -- package.json plugin.json
git status --short
```

`mutation_applied_expect_1` must be `1`. If it is `0` the `sed` matched nothing,
the files are untouched, and any subsequent "the suite went red" reading is
false — fix the mutation before interpreting the result.

Both suites must report `exit=1`. Record which test names failed. Required:
`test_manifest_version_carries_no_build_metadata` and
`test_manifest_version_supersedes_every_published_remix_tag` from V1's module,
and `test_build_metadata_in_the_manifest_is_rejected` from the metadata module.
If either suite reports `exit=0`, the gate is decoration — fix the test, do not
proceed.

### V3 — Mutation: reverting the nightly derivation must go red

```bash
sed -i 's/version="${checked_package_version}\.dev\.${build_date}\.g${short_sha}"/version="${checked_package_version}+beallio.g${short_sha}"/' \
  .github/workflows/remix-release.yml
git diff --quiet -- .github/workflows/remix-release.yml; echo "mutation_applied_expect_1=$?"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_remix_workflow_metadata; echo "exit=$?"
git checkout -- .github/workflows/remix-release.yml
git status --short
```

`mutation_applied_expect_1` must be `1` before the suite result means anything.
Then `exit=1` is required, with the nightly and PR cases failing on the exact
`version` output. Record the assertion diff.

### V4 — Mutation: deleting the build-metadata guard must go red

Delete the `case "$checked_package_version" in *+*)` block from the workflow,
then:

```bash
git diff --quiet -- .github/workflows/remix-release.yml; echo "mutation_applied_expect_1=$?"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_remix_workflow_metadata; echo "exit=$?"
git checkout -- .github/workflows/remix-release.yml
git status --short
```

Must report `exit=1` with `test_build_metadata_in_the_manifest_is_rejected`
failing. This is the mutation-test of the feature the plan exists for: with the
guard gone, a `+` version sails through.

### V5 — Mutation: a wrong comparator must go red

In `tests/test_version_scheme.py`, temporarily make `semver_precedence` compare
the full strings including build metadata (i.e. stop stripping at `+`), then:

```bash
git diff --quiet -- tests/test_version_scheme.py; echo "mutation_applied_expect_1=$?"
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_version_scheme; echo "exit=$?"
git checkout -- tests/test_version_scheme.py
git status --short
```

Must report `exit=1` on `test_comparator_matches_compare_versions_6_1_1`. If the
fidelity table still passes with build metadata included, the table is not
pinning Decky's actual behaviour and must be corrected.

### V6 — The new version survives real packaging

Requires `dist/index.js` to exist; run `pnpm build` first if it does not.

```bash
set -euo pipefail
version="$(node -p "require('./package.json').version")"
echo "version=$version"
test "$version" = '3.3.1-beallio.11'
out="/tmp/SDH-PlayTime/verify-$$"
mkdir -p "$out"
python3 tools/release_archive.py build --source "$PWD" --version "$version" \
  --output "$out/SDH-PlayTime-beallio-remix-v${version}.zip"
python3 tools/release_archive.py validate \
  --archive "$out/SDH-PlayTime-beallio-remix-v${version}.zip" --version "$version"
ls -1 "$out"
```

`set -e` makes any failing step abort loudly, so reaching the `ls -1` output is
itself the pass signal — do not add an `echo "...=$?"` after a guarded command,
which would print `0` unconditionally. Record the `ls -1` listing and confirm
both the archive and its `.sha256` embed the `-beallio.11` form, not `+beallio`.

Then the paired negative control, deliberately **without** `set -e` so the
failure can be inspected:

```bash
set +e
set -o pipefail
python3 tools/release_archive.py validate \
  --archive "$out/SDH-PlayTime-beallio-remix-v3.3.1-beallio.11.zip" \
  --version '3.3.1-beallio.12' > /tmp/SDH-PlayTime/verify-badver.txt 2>&1
echo "status=$?"
grep -F 'does not preserve PlayTime at version 3.3.1-beallio.12' \
  /tmp/SDH-PlayTime/verify-badver.txt; echo "grep_status=$?"
```

`status` must be non-zero **and** `grep_status` must be `0`. A non-zero status
alone would also be produced by a missing interpreter, so both are required.

### V7 — Precondition check on the published tag history

```bash
set -o pipefail
git tag --list 'v3.3.0+beallio.*' | sort -V
git tag --list 'v3.3.1-beallio.11'
```

The first command must list `v3.3.0+beallio.10` — the version the new release has
to supersede. If it does not, the assumption behind
`test_manifest_version_supersedes_every_published_remix_tag` is wrong: stop and
report rather than adjusting the test. The second command must print nothing;
this plan does not create the tag.

### V8 — Negative control: the update Decky would actually see

Run this last, after every mutation above has been restored. It passes only if
the whole change works end to end.

`compare-versions` is not a repo dependency and must not become one. Install it
into a scratch directory first and point `NODE_PATH` at it:

```bash
npm install --prefix /tmp/SDH-PlayTime/cv compare-versions@6.1.1
export NODE_PATH=/tmp/SDH-PlayTime/cv/node_modules
git status --short package.json pnpm-lock.yaml
```

The `git status` line must print nothing — if `package.json` or the lockfile
changed, the install leaked into the repo and must be reverted.

```bash
node -e '
const {compare, validate} = require("compare-versions");
const installed = "3.3.0+beallio.10";
const candidate = require("./package.json").version;
const plugin = require("./plugin.json").version;
if (plugin !== candidate) { console.error("FAIL: manifests disagree"); process.exit(1); }
const ok = candidate !== installed && validate(candidate) && validate(installed)
  && compare(candidate, installed, ">");
console.log("installed=" + installed + " candidate=" + candidate + " decky_offers_update=" + ok);
if (!ok) { console.error("FAIL: Decky would not offer this as an update"); process.exit(1); }
'
echo "exit=$?"
```

Required output: `decky_offers_update=true` and `exit=0`. Re-run the same snippet
with `candidate` forced to `3.3.0+beallio.11` and record that it prints
`decky_offers_update=false` and exits non-zero — that is the defect this plan
fixes, reproduced against the real library.

### V9 — Full quality gate

```bash
scripts/orchestration/run-quality-gates
```

Record the pass/fail line for each of the nine gate commands. Also run
`git diff --check` and record its output.

### Not verified

- **The tag trigger actually firing.** `tags: ['v*-beallio.*']` is checked only
  as workflow text (Task 5, V1). GitHub's glob matching is not exercised by any
  local test and cannot be, so the first real proof is pushing
  `v3.3.1-beallio.11` and observing `publish-stable-release` run. Treat that push
  as the outstanding verification and check it with
  `gh run list --workflow 'Remix quality and release'`.
- **CI end to end.** No workflow run is triggered by landing this plan on
  `remix`; the `Derive release metadata` step is exercised locally under a stubbed
  `git`, not on a GitHub runner.
- **On-device behaviour.** Decky Loader is never actually observed offering the
  update, because this repo publishes no store feed (see the out-of-scope note).
  V8 reproduces Decky's comparison logic against the same library version Decky
  uses; it does not prove a Steam Deck displays an update prompt.
- **Existing installs.** Whether a user already on `3.3.0+beallio.10` upgrades
  cleanly in place is untested here; the README snippet is a manual path.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished decky-updatable-version-scheme
```

This writes:

```text
/tmp/SDH-PlayTime/decky-updatable-version-scheme_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer decky-updatable-version-scheme`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/decky-updatable-version-scheme-review-*.md
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
   scripts/orchestration/clear-finished decky-updatable-version-scheme
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
   git add docs/review/decky-updatable-version-scheme-review-*.md
   git commit -m "docs(review): record decky-updatable-version-scheme review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished decky-updatable-version-scheme
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer decky-updatable-version-scheme` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed decky-updatable-version-scheme
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize decky-updatable-version-scheme
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/decky-updatable-version-scheme_finalized
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
scripts/orchestration/finalize decky-updatable-version-scheme
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/decky-updatable-version-scheme_finished
/tmp/SDH-PlayTime/decky-updatable-version-scheme_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
