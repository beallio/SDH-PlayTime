# Plan: Settings UI polish and association name sorting (settings-ui-and-association-sort)

## Context

Five user-requested presentation changes to the PlayTime settings UI. They are grouped into
one plan because four of them land in the same file, `src/pages/settings/index.tsx`. There is
no behavioral or data-model change here: no backend RPC, no database, no game-resolution
logic. The only change with testable logic is the association sort and the link derivation.

### 1. Tracking Status description belongs in the button's box

`src/pages/settings/index.tsx:536-551`. The `<div>` holding
"Control which games are tracked and shown in statistics." sits **outside** the
`PanelSectionRow` that wraps the "Manage Tracking Status" `ButtonItem`, so it renders as a
separate block below the button's field. Note the div sets only `padding`, `color`, and
`fontSize` — it does not set `textAlign`, so it is already left-aligned; the defect is the
separate box, not the alignment.

### 2. Game Associations description belongs in the button's box

`src/pages/settings/index.tsx:553-570`, identical structure and identical cause for
"Associate games to combine their playtime statistics. Useful for games that have multiple
versions or platforms."

For both, `ButtonItem` extends `ItemProps`, which declares `description?: ReactNode` and
`layout?: 'below' | 'inline'`
(`node_modules/.pnpm/@decky+ui@4.12.0/node_modules/@decky/ui/dist/components/Item.d.ts:3-6`).
Passing the text as `description` puts it inside the same `Field` container.

**Runtime-API caution.** `ButtonItem` is not implemented by Decky; it is located by a regex
against Steam's minified bundle
(`@decky/ui/dist/components/ButtonItem.js`). Per `AGENTS.md` §8, Steam/Decky runtime
interfaces are unstable and must be verified against live behavior rather than assumed. The
`description` prop is therefore a reasonable first choice, not a guarantee — see Task 1 for
the required fallback.

### 3. About section: remove the heart, show version and credit upstream

`src/pages/settings/index.tsx:472-491` renders
`With <FaHeart /> by ynhhoJ`, centered. That line is currently the **only** attribution to
the upstream author, so the upstream acknowledgement replaces it rather than merely adding
to it.

No new plumbing is needed for the version: `PLUGIN_VERSION` is already exported from
`src/app/settings.ts:70`, injected at build time by `@rollup/plugin-replace` from
`package.json` (`rollup.config.js:13-15`), and already stubbed in tests at
`src/test/settings.spec.ts:5-6`.

`FaHeart` is imported on `src/pages/settings/index.tsx:36` together with `FaGithub` and
`FaCalendarAlt`; removing its only use makes the import unused and biome lint will fail
unless the import list is updated in the same change.

### 4. Links point at the upstream repository

The URL constants are **duplicated across two files**, which is the part that is easy to miss:

| File | Line | Constant |
| --- | --- | --- |
| `src/pages/settings/index.tsx` | 44 | `GITHUB_URL` |
| `src/pages/settings/index.tsx` | 461 | `CHANGELOG_URL` |
| `src/pages/DeckyPanelPage.tsx` | 17 | `GITHUB_URL` |
| `src/pages/DeckyPanelPage.tsx` | 40 | `CHANGELOG_URL` |

All four are `https://github.com/0u73r-h34v3n/SDH-PlayTime` and
`${GITHUB_URL}/blob/master/CHANGELOG.md`. Fixing only the About section would leave the
Quick Access panel's changelog button — the one `useVersionCheck` reveals after an update
(`src/pages/DeckyPanelPage.tsx:44-52`) — still sending users to the upstream changelog, where
this build's entries do not exist. Both files are therefore in scope.

The remix repository is `https://github.com/beallio/SDH-PlayTime-beallio-remix`.

### 5. Association lists are not sorted by name

Two separate lists, both unsorted, and the user asked for both:

- **Existing groups** (`src/pages/AssociationListPage.tsx:136`). `buildAssociationListGroups`
  (`src/pages/association/associationViewModel.ts:375-417`) returns
  `[...grouped.entries()].map(...)`, i.e. `Map` insertion order, i.e. whatever order the
  backend emitted the associations in. Children within a group are likewise emitted in
  backend order.
- **Add-association anchor list** (`src/pages/association/hooks/useGamesForAssociation.ts:169-198`).
  `anchorCards` is built from `presence.candidates.filter(tracked)`, and the backend orders
  candidates by `game_id` as a **string** (`py_modules/db/dao.py:1216-1250`), which is
  arbitrary to a reader.

Sorting must happen in the view model, not in SQL: candidate names are a merge of database
rows and live Steam inventory (`src/app/gamePresence.ts:240-285`), so ordering the query
would only sort the database half.

Duplicate names are real in this data — two `Transformers Devastation` rows and four
`Hades II` rows exist on the author's device — so the comparison needs a deterministic
tiebreak or the list will visibly reshuffle between renders.
`src/pages/association/associationViewModel.ts:341` already uses
`localeCompare` on `gameId` for DTO members, so that idiom is established in this file.

### Settled decisions

Implement these as specified; do not substitute your own judgement:

1. **Changelog link target** is `${GITHUB_URL}/releases/tag/v${PLUGIN_VERSION}`, not a
   `CHANGELOG.md` anchor. The release tag exists for each shipped version and renders the
   release notes. A heading anchor would be `#331-beallio12---2026-08-08`, which embeds the
   release date and silently breaks.
2. **The URL constants are hoisted into one shared module** and imported by both pages.
   Do not leave two copies.
3. **Sort key** is the displayed name, compared with `localeCompare`, with `gameId` as the
   tiebreak. Apply it to group parents, to the children within each group, and to the anchor
   list.

### Testability, stated up front

The repository's frontend tests (`bun test`) are logic-only; there is no React renderer and
no test imports `SettingsPage` or `DeckyPanelPage`. Items 1, 2, and 3 are therefore markup
changes with no meaningful automated behavior test available, and this plan does not pretend
otherwise — they are covered by `tsc`, biome, `pnpm build`, and deferred on-device
inspection. Items 4 and 5 do carry real logic and **must** be unit-tested, which is why
Task 3 requires extracting the link derivation into a pure module rather than inlining a
template string in JSX.

### Out of scope

No Python changes. No backend RPC, database, migration, or game-resolution changes. Do not
alter what the association lists *contain* — only their order. Do not restyle unrelated
sections of the settings page. Do not bump the plugin version or cut a release.

### Working-tree precondition

At authoring time the only uncommitted path was an untracked `uv.lock`. Per `AGENTS.md` §3 it
is user-owned and out of scope: do not commit, stage, stash, or delete it. Stop and report if
any other tracked modification is present when Setup begins.

**Slug used throughout this plan:** `settings-ui-and-association-sort`

---

## Orchestration Contract

**Slug:** `settings-ui-and-association-sort`

**Plan file:**

```text
docs/plans/2026-08-08_settings-ui-and-association-sort.md
```

**Implementation branch:**

```text
feat/settings-ui-and-association-sort
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/settings-ui-and-association-sort_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/settings-ui-and-association-sort_finalized
```

**Review notes:**

```text
docs/review/settings-ui-and-association-sort-review-*.md
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
git checkout -b feat/settings-ui-and-association-sort
```

Commit this plan first:

```bash
git add docs/plans/2026-08-08_settings-ui-and-association-sort.md
git commit -m "docs(plan): add settings-ui-and-association-sort implementation plan"
```

---

## Implementation Tasks

Files you may modify. Any other path is out of scope:

```text
src/app/links.ts                                   (new)
src/pages/settings/index.tsx
src/pages/DeckyPanelPage.tsx
src/pages/association/associationViewModel.ts
src/pages/association/hooks/useGamesForAssociation.ts
src/test/links.spec.ts                             (new)
src/test/associationViewModel.spec.ts
docs/plans/2026-08-08_settings-ui-and-association-sort.md
```

Read the surrounding code in each file before editing and match its existing style: tabs for
indentation, the inline `style={{ … }}` convention already used in `settings/index.tsx`, and
the `bun:test` `describe`/`test` layout used by the specs.

Work in the order below. Tasks 1-2 are items 1-3; Task 3 is item 4; Tasks 4-6 are item 5.

### Task 1 — Move both descriptions into their button rows

In `src/pages/settings/index.tsx`:

- For the Tracking Status section (`:536-551`), delete the standalone description `<div>` and
  pass its text to the `ButtonItem` as `description`, keeping `Manage Tracking Status` as the
  button's children and the `onClick` unchanged.
- Do the same for the Game Associations section (`:553-570`) with its two-sentence text.

Keep both `PanelSection` titles as they are.

**Verify the rendering claim before trusting it.** `ButtonItem` resolves to a Steam-owned
component, so confirm `description` actually renders inside the field. Run `pnpm build` and
inspect the emitted `dist/index.js` to confirm the prop is passed through, then record in the
session log that on-device visual confirmation is deferred to the user. If you find concrete
evidence in this repository or in `@decky/ui`'s types that `description` is not rendered by
this component, stop and report rather than guessing — the documented fallback is to keep the
`<div>` but move it inside the `PanelSectionRow` with an explicit
`textAlign: "left"`, and that choice needs to be recorded.

### Task 2 — Rework the About header block

In `src/pages/settings/index.tsx:472-491`, replace the `With <FaHeart /> by ynhhoJ`
paragraph with a left-aligned block containing:

- the plugin version, rendered from `PLUGIN_VERSION` imported from `@src/app/settings`, in the
  form `Version 3.3.1-beallio.12` (do not hardcode the number);
- an acknowledgement naming the upstream project and author, worded so it reads as credit
  rather than affiliation, for example: `A community remix of PlayTime by ynhhoJ.` followed
  by `Upstream: 0u73r-h34v3n/SDH-PlayTime`.

Remove `textAlign: "center"`; this block is left-aligned. Then remove `FaHeart` from the
`react-icons/fa` import on line 36, leaving `FaGithub` and `FaCalendarAlt` intact. Do not
remove `FaGithub` — it is still used by the Links section at `:498`.

### Task 3 — Hoist the links into a tested module (RED first)

Create `src/app/links.ts` exporting exactly:

```ts
export const GITHUB_URL = "https://github.com/beallio/SDH-PlayTime-beallio-remix";

/** Release notes for a specific build; the tag exists for every shipped version. */
export function changelogUrlForVersion(version: string): string {
	return `${GITHUB_URL}/releases/tag/v${version}`;
}
```

Create `src/test/links.spec.ts` first and watch it fail before the module exists. Cover:

| Case | Expectation |
| --- | --- |
| `GITHUB_URL` | is the remix repository, and does **not** contain `0u73r-h34v3n` |
| `changelogUrlForVersion("3.3.1-beallio.12")` | `https://github.com/beallio/SDH-PlayTime-beallio-remix/releases/tag/v3.3.1-beallio.12` |
| `changelogUrlForVersion("3.3.2")` | ends with `/releases/tag/v3.3.2` |
| result of `changelogUrlForVersion` | never contains `blob/master` |

Then delete the four duplicated constants
(`settings/index.tsx:44`, `settings/index.tsx:461`, `DeckyPanelPage.tsx:17`,
`DeckyPanelPage.tsx:40`) and import from the new module in both files. In each file, derive
the changelog URL with `changelogUrlForVersion(PLUGIN_VERSION)`. Leave the surrounding
behavior alone — in particular `DeckyPanelPage.tsx:44-52` must still call
`markVersionAsSeen()` before navigating.

### Task 4 — Add the shared name comparator (RED first)

Add a comparator to `src/pages/association/associationViewModel.ts`, exported for testing:

```ts
export function compareByGameName(
	left: { title: string; id: string },
	right: { title: string; id: string },
): number {
	const byName = left.title.localeCompare(right.title);
	return byName !== 0 ? byName : left.id.localeCompare(right.id);
}
```

Write its tests in `src/test/associationViewModel.spec.ts` before wiring it up, and make them
fail first. Cover ascending order, case-insensitive-ish ordering via `localeCompare`, and —
importantly — that two entries sharing a title are ordered deterministically by id, using two
`Transformers Devastation` entries with ids `3015223078` and `3843090730`.

### Task 5 — Sort the existing-groups list

In `buildAssociationListGroups` (`associationViewModel.ts:375-417`):

- sort each group's `children` by `compareByGameName` before returning the group;
- sort the returned array of groups by their `parent` card with `compareByGameName`.

`AssociationCandidateCard` already carries both `title` and `id`
(`associationViewModel.ts:15-26`), so no new data plumbing is needed.

Extend the existing coverage at `src/test/associationViewModel.spec.ts:329`: construct
associations deliberately supplied out of alphabetical order and assert the returned group
order and child order are alphabetical. Read that existing test first — if it asserts on the
previous ordering, update it and record in the session log that the plan required the change
(`AGENTS.md` §7).

### Task 6 — Sort the add-association anchor list

In `src/pages/association/hooks/useGamesForAssociation.ts:169-198`, sort `anchorCards` with
`compareByGameName` inside the existing `useMemo` — sort the built cards, not the raw
candidates, so the comparator sees the same `title` the user reads. Do not change the
`candidate.tracked` filter, and do not change `componentCards` or `additionCards`; only the
anchor list is in scope for this task.

Do not sort in `py_modules/db/dao.py`. If you believe the SQL ordering must change, stop and
report instead.

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

Be honest about the split: items 1, 2, and 3 are markup with no automated behavior test
available in this repository, and no step below claims to prove them. Items 4 and 5 carry
logic and are proven by tests plus mutation controls.

### 1. Record the RED evidence

Paste the failing output captured before each fix:

- Task 3: `src/test/links.spec.ts` failing because `src/app/links.ts` does not exist yet.
- Task 4: the `compareByGameName` tests failing because the comparator does not exist yet.
- Task 5: the group-ordering assertions failing against the unsorted implementation.

A missing RED record fails this step, as does a record showing any of them green beforehand.

### 2. Focused suites

```bash
bun test src/test/links.spec.ts src/test/associationViewModel.spec.ts
```

Record the pass/fail tallies. Any failure fails this step.

### 3. Mutation control — the comparator's tiebreak is load-bearing

Temporarily drop the tiebreak so `compareByGameName` returns only the name comparison:

```ts
	return left.title.localeCompare(right.title);
```

Run the focused suites. The duplicate-title test using the two `Transformers Devastation`
ids **must fail**. Record the failing test name, then revert and confirm green.

If it stays green, the duplicate-name case is not actually being exercised, and the list will
reshuffle on the user's device where those duplicates exist.

### 4. Mutation control — the sorts are load-bearing

Temporarily remove the group sort added in Task 5 (return the mapped array unsorted). Run the
focused suites; the group-ordering assertions **must fail**. Record the names, revert,
confirm green.

### 5. Grep controls for the link change

These can fail, and say what failure looks like:

```bash
rg -n "0u73r-h34v3n" src/ ; echo "rg_exit=$?"
```

Expected: `rg_exit=1` with no matches — no source file may still reference the upstream
repository in a link. `rg_exit=0` with any hit fails this step.

```bash
rg -n "blob/master/CHANGELOG" src/ ; echo "rg_exit=$?"
```

Expected: `rg_exit=1`. Any remaining hit means a changelog link was missed.

```bash
rg -c "GITHUB_URL *=" src/ ; echo "rg_exit=$?"
```

Expected: exactly one file (`src/app/links.ts`) defines it. Two or more definitions means the
duplication was not removed and fails this step.

### 6. `FaHeart` is gone, `FaGithub` remains

```bash
rg -n "FaHeart" src/ ; echo "rg_exit=$?"
rg -n "FaGithub" src/pages/settings/index.tsx ; echo "github_exit=$?"
```

Expected: `rg_exit=1` for `FaHeart` (no matches anywhere, import included) and
`github_exit=0` for `FaGithub` (still imported and used). The inverse of either fails this
step — an unused import would also fail biome in step 8, and a removed `FaGithub` would break
the Links button.

### 7. Version is rendered from the constant, not hardcoded

```bash
rg -n "3\.3\.1-beallio" src/pages/settings/index.tsx ; echo "rg_exit=$?"
```

Expected: `rg_exit=1`. A literal version string in the page means `PLUGIN_VERSION` was not
used and the About section will go stale at the next release.

### 8. Full quality gates

```bash
scripts/orchestration/run-quality-gates
```

Record the exit status and the tail of the output. This is the only gate covering items 1-3:
it runs `tsc --noEmit`, biome lint and format, and `pnpm build`. A non-zero exit fails this
step.

### 9. Scope check

```bash
git diff --name-only remix...HEAD
```

Paste the full list. It must contain exactly:

```text
docs/plans/2026-08-08_settings-ui-and-association-sort.md
src/app/links.ts
src/pages/DeckyPanelPage.tsx
src/pages/association/associationViewModel.ts
src/pages/association/hooks/useGamesForAssociation.ts
src/pages/settings/index.tsx
src/test/associationViewModel.spec.ts
src/test/links.spec.ts
```

plus any `docs/review/settings-ui-and-association-sort-review-*.md` note committed during a
review round. No file under `py_modules/`, no `main.py`, and no `uv.lock`. A missing entry
means the work was not done; an extra entry means scope was exceeded.

### 10. Negative control (run last)

Runs after every failure case above, including both mutation reverts, so it cannot pass by
not having been exercised. Steps 3 and 4 already proved these tests can go red.

```bash
bun test src/test/links.spec.ts
links_status=$?

bun test src/test/associationViewModel.spec.ts
assoc_status=$?

if [[ "$links_status" -eq 0 && "$assoc_status" -eq 0 ]]; then
	printf 'NEGATIVE CONTROL: PASS\n'
else
	printf 'NEGATIVE CONTROL: FAIL links=%s assoc=%s\n' "$links_status" "$assoc_status"
	exit 1
fi
```

Paste the full output of both runs, not just the final line: a run that collected zero tests
still exits 0, so the reported counts are the evidence.

### Deferred and explicitly not verified

- **Items 1, 2, and 3 are not verified by any automated behavior test.** No React renderer
  exists in this repository and no test imports `SettingsPage`. Whether the descriptions
  actually render inside the button's box, whether they are left-aligned, and whether the
  About block reads correctly are confirmed only by the user looking at the device.
- **`ButtonItem.description` is an assumption about a Steam-owned component** located by
  regex against a minified bundle. It is not guaranteed by any type or test in this
  repository beyond the prop's presence in `ItemProps`.
- **On-device confirmation of the sort order** for the real association lists is the user's,
  after this plan lands.
- **Locale sensitivity.** `localeCompare` depends on the runtime's collation; ordering was
  reasoned about for the author's data, not tested across locales.
- **The Quick Access panel's changelog button** is changed but not exercised: showing it
  requires `useVersionCheck` to observe a version change on a real device.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished settings-ui-and-association-sort
```

This writes:

```text
/tmp/SDH-PlayTime/settings-ui-and-association-sort_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer settings-ui-and-association-sort`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/settings-ui-and-association-sort-review-*.md
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
   scripts/orchestration/clear-finished settings-ui-and-association-sort
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
   git add docs/review/settings-ui-and-association-sort-review-*.md
   git commit -m "docs(review): record settings-ui-and-association-sort review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished settings-ui-and-association-sort
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer settings-ui-and-association-sort` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed settings-ui-and-association-sort
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize settings-ui-and-association-sort
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/settings-ui-and-association-sort_finalized
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
scripts/orchestration/finalize settings-ui-and-association-sort
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/settings-ui-and-association-sort_finished
/tmp/SDH-PlayTime/settings-ui-and-association-sort_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
