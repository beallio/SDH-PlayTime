# Review — resolver-gated-game-checksums (round 01)

Branch: `feat/resolver-gated-game-checksums`
Reviewed against: `docs/plans/2026-08-05_resolver-gated-game-checksums.md`

## Verdict

Changes requested. The round-complete branch contains only the plan commit;
none of the checksum-gating implementation or regression coverage exists.

## Gate status

`git diff --check remix...HEAD` is clean, but this is not a valid implementation
round. `remix...HEAD` adds only
`docs/plans/2026-08-05_resolver-gated-game-checksums.md` (330 lines) and changes
no runtime or test files. Passing the unchanged repository gates therefore does
not satisfy this plan's acceptance criteria.

## Required changes

1. Implement the resolver-gated checksum flow described by the plan. Begin with
   failing Python and Bun regression tests, then change the frontend/backend RPC
   boundary so an untrusted caller cannot supply the filesystem path to hash.
2. Resolve and revalidate shortcut evidence in the backend. Pass only a reachable,
   adapter-confirmed game payload into the existing checksum implementation. Never
   hash the shortcut target, launcher, runner, emulator, Wine/Proton binary, or a
   fallback caller-provided path.
3. Apply the user's revised launcher scope: support direct executable resolution
   and the already-merged Heroic adapter in this task. Lutris, Bottles, and
   EmuDeck/Steam ROM Manager are deliberately skipped; classify those unsupported
   sources fail-closed and return no checksum. Do not add their adapters here.
4. Amend the plan's Context, dependencies, Implementation Task 6, and Verification
   language to record that scope change. Replace fixtures that require skipped
   adapters with explicit fail-closed unsupported-source tests.
5. Preserve checksum algorithm/version semantics and structured failures. Cover at
   least reachable direct and Heroic payloads, an arbitrary-path injection attempt,
   missing metadata, ambiguity, payload changes, external-drive disconnect/reconnect,
   directories, symlinks, malformed RPC input, permission/probe failure, and hash
   failure at the appropriate test layer.
6. Run the complete quality gates, ensure the tree is clean, commit all implementation
   and tests, and then recreate the round-complete marker. A plan-only commit is not
   sufficient.

STATUS: CHANGES_REQUESTED
