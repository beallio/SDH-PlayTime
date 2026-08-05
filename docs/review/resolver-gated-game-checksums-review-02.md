# Review — resolver-gated-game-checksums (round 02)

Branch: `feat/resolver-gated-game-checksums`
Reviewed against: `docs/plans/2026-08-05_resolver-gated-game-checksums.md`

## Verdict

Changes requested. The branch now contains substantive implementation and tests,
but the checksum trust boundary can still be bypassed and the settings UI regresses
all successful rows to the old missing-path state.

## Gate status

The round-complete marker is valid at `7073159f1618a8f7a367a3706df3c41561108062`,
the tree is clean, and `git diff --check remix...HEAD` passes. The implementer gate
completed, but root review reproduced a blocking adversarial case: a caller-created
MZ file plus a forged, structurally valid `direct` normalized request and unrelated
`appId` returned `status: ready` and the file's digest. The coordinator ignores the
extra `appId`, so the current test only proves an extra `filePath` key is ignored;
it does not bind the normalized path to the requested Steam shortcut.

The independent reproduction returned:

```text
{'checksum': 'ed70a9aeb89aba99df217d3e5c87fa6bbc8f1274da5f45e843e59a3ad698fed1',
 'status': 'ready', 'reason_code': None}
```

The full gate was not repeated after this deterministic blocking finding.

## Required changes

1. Make the checksum RPC carry a bounded Steam app ID and bind the evidence to that
   exact shortcut in the backend before resolution. A caller-supplied
   `classificationStatus: recognized` and internally consistent normalized token set
   are not authoritative proof. Revalidate from an authoritative shortcut identity
   source or another backend-owned binding. If a direct shortcut cannot be bound
   safely, fail closed instead of hashing the supplied path.
2. Reject, rather than silently ignore, unexpected path/identity fields at the checksum
   RPC boundary. In particular, an unrelated app ID plus an arbitrary normalized direct
   path must return no checksum and must never call `Files.get_file_sha256`.
3. Replace the current arbitrary-path regression. It currently supplies the legitimate
   payload in every normalized field and merely adds an ignored `filePath`. Add tests
   for a forged `recognized` classification, an arbitrary executable-shaped normalized
   path, an unrelated app ID, inconsistent shortcut identity/evidence, and unexpected
   second path fields. Assert the hasher records zero calls in every rejected case.
4. Preserve a positive direct-executable path only when the app ID/evidence binding is
   confirmed. Preserve Heroic by resolving backend-owned Heroic metadata, not the
   launcher path. Add an actual reachable Heroic fixture integration test and an actual
   ambiguous-metadata test; a `StaticResolver` result is insufficient for the plan's
   Heroic verification.
5. Update `LocalNonSteamGame` and the checksum settings UI to use the new structured
   checksum status. `FileChecksumStatus` still checks `pathToGame`, but this branch no
   longer returns that field, so every row currently renders "File not found or
   unsupported path" even when `status` is `ready`. Render distinct supported UI states
   for unsupported shortcut, missing metadata, unavailable payload, hash failure,
   ready-unsaved, and ready-saved, with Bun coverage.
6. Do not report unsupported/unavailable map entries as successfully generated hashes.
   The completion toast currently uses `gameChecksums.nonSteam.size`, which now includes
   every structured failure; count only `ready` results with a checksum.
7. Remove the stale caller-path request alias (`GetFileSHA256DTO`) from the TypeScript and
   Python request schemas if it has no remaining compatibility consumer. Add a source/API
   regression proving the legacy public RPC is absent rather than checking only a static
   TypeScript class property.
8. Run the complete quality gates, commit the fixes and tests, leave a clean tree, and
   recreate the round-complete marker.

STATUS: CHANGES_REQUESTED
