# Review — game-parent-integration-hardening (round 02)

Branch: `feat/game-parent-integration-hardening`
Reviewed commit: `4367e7115b4f137ce6471bde8b15a07b58255ffd`
Reviewed against: `docs/plans/2026-08-05_game-parent-integration-hardening.md`

## Verdict

Changes requested. The round-01 integration, archive, and documentation findings are
resolved, but the shared projection regression fence is timezone-dependent and fails
in the repository's local timezone.

## Verified corrections

- The backend RPC, frontend cache, and Steam overview tests now consume one bounded
  shared projection fixture with a numeric Steam alias.
- Direct and Heroic adapter integration tests cover disconnect, reconnect, confirmed
  parent stability, read-only resolution, and resolver-gated checksumming.
- The support matrix separates source fixture provenance from local fence commits and
  no longer advertises Heroic GOG or Nile as verified.
- `DEVELOPER.md` is required in the release archive, and validation rejects archives
  that omit it or include excluded test/cache payloads.

## Required change

1. Make the shared projection tests preserve the backend's local-time contract without
   assuming UTC. `canonicalRecord.lastPlayedDate` is the RPC value
   `2025-01-01T12:00:00`, produced from PlayTime's timezone-naive local timestamps, but
   both new Bun assertions hard-code epoch `1735732800` (12:00 UTC). The default Bun
   test runner happens to make those assertions pass; the same tests fail under
   `TZ=America/Los_Angeles` with the correct local epoch `1735761600`:

   ```text
   TZ=America/Los_Angeles bun test \
     src/test/cachables.spec.ts src/test/steamPlayTimePatches.spec.ts
   # 17 pass, 2 fail
   # expected 1735732800, received 1735761600
   ```

   Derive the expected epoch from the shared fixture's `lastPlayedDate` using the same
   local-time interpretation as production, or use another timezone-independent
   assertion that still proves the exact RPC fixture reaches the cache and overview.
   Do not append `Z` to the fixture: that would change the asserted backend DTO shape
   instead of testing its established local-time semantics. Add the explicit
   `TZ=America/Los_Angeles` command to focused verification or otherwise fence this
   regression, then rerun the complete quality gates from a clean tree.

STATUS: CHANGES_REQUESTED
