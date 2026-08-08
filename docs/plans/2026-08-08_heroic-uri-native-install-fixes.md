# Plan: Fix Heroic URI classification and native install probe on Deck (heroic-uri-native-install-fixes)

## Context

Two independent frontend defects make the "Game Management > Manage Game Associations"
page report the wrong availability for real games on a Steam Deck. Both were measured on
device on 2026-08-08 against plugin version `3.3.1-beallio.11`, by evaluating the plugin's
own code inside Steam's `SharedJSContext` through the CEF debugger. Neither is a backend
defect: the Python resolver returns correct verdicts for every case below.

### Bug 1 — Heroic shortcuts are classified `ambiguous` on device

`classifyHeroic` in `src/steam/utils/GamePaths.ts:703-707` selects Heroic launch URIs with:

```ts
(url): url is URL => url?.protocol === "heroic:" && url.host === "launch"
```

`URL` parses non-special schemes differently across engines. Measured, same input string
`heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload`:

| Engine | `protocol` | `host` | `pathname` |
| --- | --- | --- | --- |
| Node 24 / Bun 1.3 (where `bun test` runs) | `heroic:` | `launch` | `""` |
| Steam Deck CEF (`SharedJSContext`) | `heroic:` | `""` | `//launch` |

On device the filter therefore drops every URL, `appNames` stays empty, and
`GamePaths.ts:743-751` returns `ambiguous("heroic")`. `src/app/gamePresence.ts:655-663`
accepts only `recognized`, so it sets `availability.status = "unknown"` with
`reason("resolver_unknown", "resolver")` and **never calls `resolve_game_payloads`**. The
association UI renders "Status unavailable" (`src/pages/association/associationViewModel.ts:83-108`).

Measured live snapshot for `Transformers Devastation` (Steam shortcut appid `3015223078`):

```json
{"source":"non_steam","tracked":true,"inventory":{"status":"current"},
 "availability":{"status":"unknown","reasons":[{"code":"resolver_unknown","source":"resolver"}]}}
```

Every Heroic shortcut on the device fails identically — `Deadpool` (`3497159354`),
`Windrose`, `Wobbly Life`, `Warhammer 40,000: Space Marine`. The backend is correct: calling
`resolve_game_payloads` on device through the live Decky RPC with the exact frontend-built
request returns `payloadStatus: "reachable"`, `metadataStatus: "resolved"`,
`provenance: "heroic_metadata"`. This bug is why the Heroic flatpak fix shipped in
`493722b` produced no visible change.

`classifyLutris` at `GamePaths.ts:783` already tolerates both shapes with
`const action = url.host || segments.shift();`. Bug 1 is the Heroic path failing to use that
same idiom. Bug 1's fix must extend it to the two Heroic sites and change nothing else.

`bun test` runs on Bun, the engine where the bug does **not** reproduce, which is why the
existing suite is green against broken behavior. A regression test that merely calls
`classifyShortcutEvidence` with a Heroic URI passes today and proves nothing. This plan
therefore requires both a pure helper testable with either engine's parse shape, and a test
that emulates the Deck's `URL` semantics.

### Bug 2 — native Steam games report "Installed" when they are not

`SteamClient.Apps.BIsAppInstalled` does not exist on this Steam build (measured:
`typeof` is `"undefined"`), so `runtimeNativeInstallProbe`
(`src/app/gamePresence.ts:888-932`) always takes its fallback. For
`STAR WARS™: The Force Unleashed™ Ultimate Sith Edition` (appid `32430`) Steam supplies
neither `installed` nor `is_installed`, so the fallback reaches its last branch and maps
`per_client_data[0].is_available_on_current_platform` to `"installed"`. That field means
"runs on this platform", not "is on disk", so every owned platform-compatible game reads as
installed. Measured live snapshot:

```json
{"id":"32430","source":"native_steam","availability":{"status":"reachable","label":"Installed"}}
```

`32430` is not installed. A correct source exists and was verified on device:
`collectionStore.localGamesCollection` held 27 apps, with `32430` and `Prototype` (`10150`)
absent and `Hades` (`1145360`) and `Vampire Survivors` (`1942280`) present. It agrees with
`SteamClient.InstallFolder.GetInstallFolders()`.

Two decisions are settled and must be implemented as specified:

1. Use `collectionStore.localGamesCollection` as the fallback install source. Do not add an
   `InstallFolder` call.
2. When that collection is present and the app is absent from it, report `"not_installed"`
   — treat the collection as complete. When the collection itself is unavailable, the probe
   is unavailable, which is a different thing: see the task for the exact split.

### Intended outcome

On device, `Transformers Devastation` and the other Heroic shortcuts read
"Available on this Deck", and `32430` reads "Installation missing" instead of "Installed".

### Out of scope

Do not modify any Python under `py_modules/` or `main.py` — the backend is correct. Do not
touch `classifyLutris`, `classifyBottles`, `classifyFlatpak`, or `classifyEmudeck` beyond the
shared helper extraction this plan specifies. Do not address the separate bare-`.exe` +
`STEAM_COMPAT_DATA_PATH %command%` gap that leaves `Transformers Fall of Cybertron`
(`3276984150`) and `X-Men Origins Wolverine` (`2156493633`) unresolvable; that is known
outstanding work for a different plan. Do not bump the plugin version or cut a release. Do
not merge, delete, or otherwise reconcile the duplicate `game_dict` rows for
`Transformers Devastation` (`3015223078` and `3843090730`) in the on-device database.

### Working-tree precondition

At authoring time the only uncommitted path was an untracked `uv.lock`. Per `AGENTS.md` §3
it is user-owned and out of scope: do not commit, stage, stash, or delete it. Stop and
report if any other tracked modification is present when Setup begins.

**Slug used throughout this plan:** `heroic-uri-native-install-fixes`

---

## Orchestration Contract

**Slug:** `heroic-uri-native-install-fixes`

**Plan file:**

```text
docs/plans/2026-08-08_heroic-uri-native-install-fixes.md
```

**Implementation branch:**

```text
feat/heroic-uri-native-install-fixes
```

**Round-complete marker:**

```text
/tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finished
```

**Finalized marker:**

```text
/tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finalized
```

**Review notes:**

```text
docs/review/heroic-uri-native-install-fixes-review-*.md
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
git checkout -b feat/heroic-uri-native-install-fixes
```

Commit this plan first:

```bash
git add docs/plans/2026-08-08_heroic-uri-native-install-fixes.md
git commit -m "docs(plan): add heroic-uri-native-install-fixes implementation plan"
```

---

## Implementation Tasks

Files you may modify. Any other path is out of scope:

```text
src/steam/utils/GamePaths.ts
src/app/gamePresence.ts
src/types/steam/CollectionStored.d.ts
src/test/utils/steam/shortcutEvidenceClassifier.spec.ts
src/test/gamePresence.spec.ts
docs/plans/2026-08-08_heroic-uri-native-install-fixes.md
```

Work in the order below. Tasks 1-4 are Bug 1; tasks 5-8 are Bug 2.

### Task 1 — Add the Deck `URL` emulator to the classifier spec (RED)

In `src/test/utils/steam/shortcutEvidenceClassifier.spec.ts`, add a helper that emulates how
Steam Deck CEF parses non-special schemes, plus a scoped installer that restores the real
global afterwards:

```ts
const SPECIAL_SCHEMES = new Set([
	"http:",
	"https:",
	"ws:",
	"wss:",
	"ftp:",
	"file:",
]);

class DeckUrl extends URL {
	get host(): string {
		return SPECIAL_SCHEMES.has(this.protocol) ? super.host : "";
	}

	get hostname(): string {
		return SPECIAL_SCHEMES.has(this.protocol) ? super.hostname : "";
	}

	get pathname(): string {
		if (SPECIAL_SCHEMES.has(this.protocol) || !super.host) {
			return super.pathname;
		}
		return `//${super.host}${super.pathname}`;
	}
}

function withDeckUrlParsing<T>(run: () => T): T {
	const realUrl = globalThis.URL;
	globalThis.URL = DeckUrl as unknown as typeof URL;
	try {
		return run();
	} finally {
		globalThis.URL = realUrl;
	}
}
```

Assert the emulator matches the measured device behavior before relying on it:

```ts
test("DeckUrl reproduces Steam Deck CEF parsing of heroic URIs", () => {
	const parsed = new DeckUrl(
		"heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload",
	);
	expect(parsed.protocol).toBe("heroic:");
	expect(parsed.host).toBe("");
	expect(parsed.pathname).toBe("//launch");
	expect(parsed.searchParams.get("appName")).toBe("4YuV2WARPPBTcq2Aatubw1");
});
```

Then add the failing integration test, using the exact shortcut measured on device:

```ts
test("recognizes a Heroic flatpak shortcut under Deck URL parsing", () => {
	const evidence = withDeckUrlParsing(() =>
		classifyShortcutEvidence({
			strShortcutExe: '"flatpak"',
			strShortcutLaunchOptions:
				'run com.heroicgameslauncher.hgl --no-gui --no-sandbox "heroic://launch?appName=4YuV2WARPPBTcq2Aatubw1&runner=sideload"',
			strShortcutStartDir: '"/usr/bin"',
			strFlatpakAppID: "",
		} as ShortcutEvidenceInput),
	);

	expect(evidence.status).toBe("recognized");
	expect(evidence.launcherKind).toBe("heroic");
	expect(evidence.externalIdentityHints).toEqual({
		heroicAppName: "4YuV2WARPPBTcq2Aatubw1",
		heroicRunner: "sideload",
	});
});
```

Run `bun test src/test/utils/steam/shortcutEvidenceClassifier.spec.ts` and record the
output. The new integration test **must fail**, reporting `"ambiguous"` where `"recognized"`
is expected. If it passes, the emulator is wrong — fix the emulator before continuing, and
do not proceed to Task 2 until you have observed a genuine failure for that reason.

### Task 2 — Extract an engine-tolerant Heroic launch-URI helper

In `src/steam/utils/GamePaths.ts`, add a module-level helper next to `parseUrl`
(`GamePaths.ts:635`). Export it so it can be unit-tested directly:

```ts
export type LaunchUriParts = {
	protocol: string;
	host: string;
	pathname: string;
};

/**
 * Returns the path segments after a `heroic://launch` action, or `undefined` when the URI
 * is not a Heroic launch URI. Engines disagree on how non-special schemes are parsed:
 * Node and Bun report `heroic://launch` as host `launch` with an empty pathname, while
 * Steam Deck CEF reports an empty host with pathname `//launch`. Both shapes must resolve
 * to the same segments, matching the existing `url.host || segments.shift()` idiom in
 * `classifyLutris`.
 */
export function heroicLaunchSegments(
	url: LaunchUriParts,
): string[] | undefined {
	if (url.protocol !== "heroic:") {
		return;
	}
	const segments = url.pathname.split("/").filter(Boolean);
	const action = url.host || segments.shift();
	return action === "launch" ? segments : undefined;
}
```

Do not change `parseUrl` itself.

### Task 3 — Use the helper at both Heroic call sites

In `classifyHeroic` (`GamePaths.ts:699-758`), the loop body still needs the `URL` object for
`getUrlValues`, so carry the URL and its segments together instead of filtering to bare
URLs:

```ts
	const heroicUrls = normalized.launchOptionTokens
		.map(parseUrl)
		.map((url) => {
			const segments = url ? heroicLaunchSegments(url) : undefined;
			return url && segments ? { url, segments } : undefined;
		})
		.filter(
			(entry): entry is { url: URL; segments: string[] } => entry !== undefined,
		);
```

Then iterate `for (const { url, segments } of heroicUrls)`, using `url` for the
`getUrlValues` calls and the helper's `segments` in place of the recomputed
`url.pathname.split("/").filter(Boolean)` at `GamePaths.ts:729`, so the `launch` token is
not re-counted on the Deck shape.

Preserve every other behavior in that function exactly: the `isHeroicLauncher` guard, the
`isStructurallyCompleteCommand` guard, `getUrlValues(url, ["appName", "appId", "appID"])`,
`runner`, `altExe`, the `segments.length === 1` / `=== 2` / `> 2` interpretation, the
`invalidPath` handling, and the `uniqueValue` ambiguity checks.

In `launcherProtocols` (`GamePaths.ts:1051-1065`), replace
`url?.protocol === "heroic:" && url.host === "launch"` with a check that
`heroicLaunchSegments(url) !== undefined`. Leave the `lutris:` branch untouched.

Re-run `bun test src/test/utils/steam/shortcutEvidenceClassifier.spec.ts`. The Task 1
integration test must now pass, and every pre-existing case in the fixture corpus must still
pass. Record the pass/fail tallies.

### Task 4 — Unit-test the helper against both engine shapes

Add direct tests for `heroicLaunchSegments` in
`src/test/utils/steam/shortcutEvidenceClassifier.spec.ts`. These take plain objects and do
not depend on any runtime `URL` implementation:

| Input | Expected |
| --- | --- |
| `{protocol:"heroic:", host:"launch", pathname:""}` | `[]` |
| `{protocol:"heroic:", host:"", pathname:"//launch"}` | `[]` |
| `{protocol:"heroic:", host:"launch", pathname:"/legendary/GameId"}` | `["legendary","GameId"]` |
| `{protocol:"heroic:", host:"", pathname:"//launch/legendary/GameId"}` | `["legendary","GameId"]` |
| `{protocol:"heroic:", host:"install", pathname:""}` | `undefined` |
| `{protocol:"heroic:", host:"", pathname:"//install"}` | `undefined` |
| `{protocol:"lutris:", host:"rungameid", pathname:"/1"}` | `undefined` |

### Task 5 — Declare `localGamesCollection`

In `src/types/steam/CollectionStored.d.ts`, add to the `CollectionStore` interface:

```ts
	/**
	 * Steam's set of locally installed apps. Absent on some clients.
	 */
	localGamesCollection?: SteamCollection;
```

Do not add or change any other member.

### Task 6 — Add the failing native-install-probe test (RED)

In `src/test/gamePresence.spec.ts`, extend the `RuntimeTestFixtures` type
(`gamePresence.spec.ts:141-156`) with:

```ts
	collectionStore?: {
		deckDesktopApps?: {
			apps: Map<number, TestDeckDesktopApp>;
		};
		localGamesCollection?: {
			allApps: Array<{ appid: number }>;
		};
	};
```

Add a test reproducing the measured `32430` case. Copy the harness shape used by the
existing test at `gamePresence.spec.ts:1593`: drive it through
`refreshCurrentGamePresenceSnapshot({ getAppDetails: async () => ({ status: "failure", reason: "missing-details" }) })`
with `setRuntimeFixtures(...)`, and leave `SteamClient` unset so
`SteamClient.Apps.BIsAppInstalled` is absent and `runtimeNativeInstallProbe()` takes its
fallback. Do not use the `buildGamePresenceSnapshot` input path for these two tests — the
runtime probe is only constructed on the `refreshCurrentGamePresenceSnapshot` path.

The candidate's `appStore` row must have **no** `installed` and **no** `is_installed`, have
`per_client_data: [{ is_available_on_current_platform: true }]`, and be **absent** from
`localGamesCollection`. Assert:

```ts
expect(snapshot.candidates[0]?.availability).toEqual({
	status: "unreachable",
	reasons: [{ code: "native_not_installed", source: "native_steam" }],
});
```

That literal is the shape `src/app/gamePresence.ts:576-580` produces for `not_installed`;
re-read that branch and keep the assertion matching it exactly.

Add a sibling test where the same app **is** present in `localGamesCollection` and assert
`availability` equals `{ status: "reachable", reasons: [], label: "Installed" }`, matching
the existing reachable assertions in this file.

Run `bun test src/test/gamePresence.spec.ts` and record the output. The absent-app test
**must fail** today, reporting a reachable/installed availability. Do not proceed until you
have observed that failure.

### Task 7 — Replace the `is_available_on_current_platform` branch

In `runtimeNativeInstallProbe` (`src/app/gamePresence.ts:888-932`):

1. Extend the local `runtime` type with
   `collectionStore?: { localGamesCollection?: { allApps?: Array<{ appid: number }> } }`.
2. Delete the `per_client_data` branch at `gamePresence.ts:917-929` entirely.
3. Resolve the installed-app ids once per probe construction, not per call: read
   `runtime.collectionStore?.localGamesCollection?.allApps`, and if it is an array build a
   `Set<number>` of its `appid` values.
4. Change the availability guard. The probe is *unavailable* — keep returning `undefined`
   from `runtimeNativeInstallProbe` — only when **both** `appStore.allApps` is not an array
   **and** the local-games set could not be built. If either source exists, return a probe.
5. Inside the returned probe, resolve in this order:
   - if the matching `appStore` row has a boolean `installed`, use it;
   - else if that row has a boolean `is_installed`, use it;
   - else if the local-games set was built, return `"installed"` when it contains `appId` or
     `toSteamCallbackAppId(appId)`, and `"not_installed"` otherwise;
   - else return `{ status: "unknown" }`.

   Note this makes a missing `appStore` row non-fatal when the local-games set exists; the
   current `if (!app) return { status: "unknown" }` early return must move accordingly.
6. Remove `per_client_data` from the `RuntimeAppStoreGame` type (`gamePresence.ts:151-159`)
   only after `rg -n "per_client_data" src/` shows no remaining non-test reference.

### Task 8 — Retire the test that asserts the old behavior

`src/test/gamePresence.spec.ts:1593` is
`"falls back to appStore per_client_data install metadata when direct probe is unavailable"`.
It encodes the defect: it asserts that `is_available_on_current_platform: true` yields
installed. Replace it with the Task 6 coverage rather than leaving both.

`AGENTS.md` §7 forbids weakening tests to make a change pass. This deletion is required by
this plan, so it is permitted — record the rationale in the session log, naming the test and
stating that the behavior it asserted is the defect being fixed. Do not delete or weaken any
other test.

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

Verification steps here follow `references/verification-standards.md` in the
`orchestration-plan-author` skill. Report captured command output and tallies, not
conclusions. Run every step from the repository root with `set -o pipefail` in effect for
any pipeline.

### 1. Record the RED evidence

Paste the failing output captured in Task 1 and Task 6, before their fixes. Each must show a
test failing for the stated reason:

- Task 1: the Deck-URL classifier test reporting `"ambiguous"` where `"recognized"` was
  expected.
- Task 6: the absent-from-`localGamesCollection` test reporting a reachable/installed
  availability where `unreachable` / `native_not_installed` was expected.

If either was already green before its fix, the test does not exercise the defect. Say so
explicitly and fix the test before continuing. A missing RED record fails this step.

### 2. Focused suites

```bash
bun test src/test/utils/steam/shortcutEvidenceClassifier.spec.ts
bun test src/test/gamePresence.spec.ts
```

Record the pass/fail tallies for each. Any failure fails this step.

### 3. Mutation control — Bug 1

Temporarily change `heroicLaunchSegments` so it ignores the Deck shape, reverting it to the
original semantics:

```ts
	const action = url.host;
```

Run:

```bash
bun test src/test/utils/steam/shortcutEvidenceClassifier.spec.ts
```

The Deck-URL integration test and the two `pathname: "//launch"` helper cases **must fail**.
Record the failing test names, then revert the mutation and re-run to confirm green again.
If the suite stays green under the mutation, the tests do not cover the fix.

### 4. Mutation control — Bug 2

Temporarily change the local-games branch in `runtimeNativeInstallProbe` to always report
installed:

```ts
			return { status: "installed" };
```

Run:

```bash
bun test src/test/gamePresence.spec.ts
```

The absent-from-`localGamesCollection` test **must fail**. Record the failing test name,
then revert the mutation and re-run to confirm green again.

### 5. Scope check

```bash
git diff --name-only remix...HEAD
```

Paste the full list. It must contain exactly:

```text
docs/plans/2026-08-08_heroic-uri-native-install-fixes.md
src/app/gamePresence.ts
src/steam/utils/GamePaths.ts
src/test/gamePresence.spec.ts
src/test/utils/steam/shortcutEvidenceClassifier.spec.ts
src/types/steam/CollectionStored.d.ts
```

plus any `docs/review/heroic-uri-native-install-fixes-review-*.md` note committed during a
review round. A missing entry means the work was not done; an extra entry means scope was
exceeded. Either fails this step. `uv.lock` must not appear.

### 6. Full quality gates

```bash
scripts/orchestration/run-quality-gates
```

Record its exit status and the tail of its output. A non-zero exit fails this step.

### 7. Negative control (run last)

This step passes only against a working implementation. It runs after every failure case
above — including both mutation reverts — so it cannot pass merely by not having been
exercised. Steps 3 and 4 already proved each of these two tests can go red, so a green run
here is meaningful rather than decorative.

Re-run only the two decisive tests, by name, and capture the exit status directly rather
than through a pipeline:

```bash
bun test src/test/utils/steam/shortcutEvidenceClassifier.spec.ts \
  -t "recognizes a Heroic flatpak shortcut under Deck URL parsing"
heroic_status=$?

bun test src/test/gamePresence.spec.ts -t "<name of the Task 6 absent-app test>"
native_status=$?

if [[ "$heroic_status" -eq 0 && "$native_status" -eq 0 ]]; then
	printf 'NEGATIVE CONTROL: PASS\n'
else
	printf 'NEGATIVE CONTROL: FAIL heroic=%s native=%s\n' \
		"$heroic_status" "$native_status"
	exit 1
fi
```

Substitute the real Task 6 test name. Paste the full output of both runs, not just the final
line: a run that matched zero tests reports `0 pass` and still exits 0, so the tallies are
the evidence. If either run reports `0 pass`, the name filter is wrong and this step fails.

### Deferred and explicitly not verified

- **On-device behavior.** No step here proves the association UI renders
  "Available on this Deck" for `Transformers Devastation` or "Installation missing" for
  `32430`. That needs a build, an install on Steam Deck hardware, a Decky reload, and a look
  at the live UI. That confirmation is the user's, after this plan lands.
- **Other Steam clients.** The `URL` parse difference was measured on one Steam Deck CEF
  build and on Node 24 / Bun 1.3. The fix accepts both shapes, but no other client was
  tested.
- **`localGamesCollection` completeness.** It was observed once, holding 27 apps and
  agreeing with `SteamClient.InstallFolder.GetInstallFolders()`. Whether it is ever
  transiently empty or partially populated during Steam startup was not tested; if it is,
  the settled decision in Context makes those apps read "Installation missing" for that
  window.
- **Non-`sideload` Heroic runners.** `legendary`, `gog`, and `nile` shortcuts are covered
  only through the existing fixture corpus and the helper's path-segment cases, not against
  real device data.
- **The bare-`.exe` + `STEAM_COMPAT_DATA_PATH` gap** is out of scope and remains broken
  after this plan.

---

## Mark Round Complete

When the implementation round is complete and the working tree is clean, run:

```bash
scripts/orchestration/mark-finished heroic-uri-native-install-fixes
```

This writes:

```text
/tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finished
```

Then exit cleanly. If this process exits, the orchestrator will resume you through
`scripts/orchestration/continue-implementer heroic-uri-native-install-fixes`.

---

## Review Polling Loop

After marking the round complete, check existing review notes first, then poll for new review notes if you remain active:

```text
docs/review/heroic-uri-native-install-fixes-review-*.md
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
   scripts/orchestration/clear-finished heroic-uri-native-install-fixes
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
   git add docs/review/heroic-uri-native-install-fixes-review-*.md
   git commit -m "docs(review): record heroic-uri-native-install-fixes review notes"
   ```

8. Recreate the round-complete marker:

   ```bash
   scripts/orchestration/mark-finished heroic-uri-native-install-fixes
   ```

9. Either continue polling or exit cleanly. If you exit, the orchestrator will resume you with `scripts/orchestration/continue-implementer heroic-uri-native-install-fixes` after the next review note is created.

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
   scripts/orchestration/check-review-notes-committed heroic-uri-native-install-fixes
   ```

3. Confirm the working tree is clean:

   ```bash
   git status --short
   ```

4. Finalize:

   ```bash
   scripts/orchestration/finalize heroic-uri-native-install-fixes
   ```

5. Confirm the finalized marker exists:

   ```text
   /tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finalized
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
scripts/orchestration/finalize heroic-uri-native-install-fixes
```

Do not manually merge into `remix` unless the finalize script fails and the user/orchestrator explicitly instructs you to recover manually.

Leave both markers in place after finalization:

```text
/tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finished
/tmp/SDH-PlayTime/heroic-uri-native-install-fixes_finalized
```

Any project-specific release step runs from the project's
`scripts/orchestration-hooks/finalize-release` hook, invoked by finalize.
