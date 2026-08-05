# Review — resolver-gated-game-checksums (round 03)

Branch: `feat/resolver-gated-game-checksums`
Reviewed against: `docs/plans/2026-08-05_resolver-gated-game-checksums.md`

## Verdict

Changes requested. The backend-owned shortcut catalog closes the arbitrary-path
injection found in round 2, and the structured settings UI is corrected. However,
the new identity source still uses first-match selection when multiple VDF records
map to the same shortcut app ID, which can hash the wrong listing.

## Gate status

The round-complete marker is valid at `311a93dea08452738c0f16df04d1b0f9a18b8568`,
the tree is clean, and `git diff --check remix...HEAD` passes. Root review also
confirmed the checksum request now accepts only `{appId}` and the backend reconstructs
evidence from `shortcuts.vdf`.

An independent duplicate-record reproduction wrote two VDF records with the same
`exe` and `appname` (therefore the same shortcut app ID) but different launch data.
`SteamShortcutCatalog.get_request()` returned the first direct record instead of
failing closed as ambiguous. This is the first-match behavior the feature must avoid.
The full gate was not repeated after this deterministic blocking finding.

## Required changes

1. Collect all VDF records matching the requested unsigned app ID before returning a
   resolution request. If more than one distinct record/request matches, return an
   explicit ambiguous catalog outcome and ensure the checksum coordinator returns no
   digest with `reasonCode: ambiguous`. Do not let file order choose the payload.
2. Account for the candidate Steam roots being aliases of the same installation.
   Deduplicate the same physical/catalog source and identical record evidence so normal
   `.local/share/Steam`, `.steam/steam`, and `.steam/root` symlinks do not create false
   ambiguity; still reject genuinely distinct colliding records.
3. Parse and validate the VDF record's real integer `appid` field (normalizing its signed
   binary representation to unsigned 32-bit) against both the requested ID and the
   derived `crc32(exe + appname) | 0x80000000` value. A missing, non-integer, or
   inconsistent stored identity must fail closed. Update test VDF writers to emit the
   realistic type-2 `appid` field rather than relying only on string fields.
4. Expand `steam_shortcuts_test.py` beyond its single happy path. Cover duplicate/colliding
   records, identical-source deduplication, signed stored app IDs, mismatched/missing
   app IDs, malformed/truncated strings and integers, unsupported field types, excessive
   nesting/record count/file size, invalid UTF-8, duplicate case-insensitive keys, and
   trailing bytes. The parser is now an authorization boundary, so malformed structures
   must not be partially accepted.
5. Make parser structural limits effective during parsing, not only after a dictionary
   has already been built; duplicate record keys must not be able to hide a record-count
   overflow. Preserve the existing size, depth, field-length, and bounded-read behavior.
6. Add a coordinator regression proving duplicate/colliding shortcut records call neither
   the resolver nor the hasher and surface the structured ambiguous result. Preserve the
   round-2 forged-path, direct positive, Heroic positive/ambiguous, external-drive, and
   UI status tests.
7. Run the complete quality gates, commit the fixes/tests, leave a clean tree, and recreate
   the round-complete marker.

STATUS: CHANGES_REQUESTED
