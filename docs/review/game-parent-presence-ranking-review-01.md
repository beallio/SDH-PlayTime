# Review — game-parent-presence-ranking (round 01)

Branch: `feat/game-parent-presence-ranking`
Reviewed against: `docs/plans/2026-08-05_game-parent-presence-ranking.md`

## Verdict

Changes requested. The pure ranking table follows the intended conservative tiers,
but the production snapshot path can still misclassify removed records and can make
every non-Steam candidate unknown in an ordinary library larger than one resolver batch.

## Gate status

The marker is valid at `df825fb32505b3ae69fe93b09af05db5ca8d4571`, the tree is
clean, and `git diff --check remix...HEAD` passes. The implementer gate completed.
Root review found blocking contract gaps before repeating the full gate:

- `Backend.getAssociationCandidates()` returns only `game` and `duration`, but
  `refreshCurrentGamePresenceSnapshot()` passes those candidates through unchanged.
  A removed tracked record is absent from both inventories and has no `source`, so
  `deriveInventory()` returns `unknown`; the production path can never classify that
  record as historical. The tests hide this by injecting `source` themselves.
- all non-Steam resolution requests are sent in one call, while the merged backend
  resolver accepts at most 32 entries. A normal library with 33 or more current
  shortcuts therefore receives a batch-level malformed error and marks every shortcut
  unknown instead of resolving bounded chunks.
- the runtime inventory helpers label any present `appStore.allApps` array or
  `deckDesktopApps` object as complete without a reliable loaded/success signal. A
  partially populated store can therefore omit a tracked ID and mark it historical.

## Required changes

1. Make the production raw-candidate path carry or derive an authoritative stable source
   for tracked rows, including rows no longer present in either live inventory. Do not
   rely on test-only `source` injection. Add a test that starts from the exact current
   backend DTO shape (`game` plus `duration`) and proves removed native and non-Steam
   records become historical only under their own complete inventory.
2. Do not infer source by fuzzy name or playtime. Use a documented stable app-identity
   rule or extend the read DTO with a source derived from authoritative stored/Steam ID
   evidence. This may add read metadata, but must not persist live presence or mutate an
   association during refresh.
3. Chunk non-Steam resolver requests into bounded batches no larger than the backend's
   `MAX_RESOLUTION_BATCH_SIZE` (32), preserving candidate/result correlation across
   batches. Add 32/33/multi-batch tests, a failed middle batch, and input-order tests.
4. Require each resolver batch to return exactly one result per request. Extra, missing,
   or batch-error results must fail closed for that batch. A candidate is reachable only
   when the result is internally consistent for an adapter-confirmed regular file;
   `payloadStatus: reachable` with a directory/unknown kind or missing payload proof must
   not become "Available on this Deck."
5. Make production inventory completeness capability-based. Do not mark an inventory
   complete merely because its current array/object exists. Either detect a reliable
   loaded/success state narrowly, accept completeness from an authoritative caller, or
   return incomplete until integration hardening supplies proof. Add loading, partial,
   failed, and complete runtime-adapter tests showing omissions become historical only
   in the final case.
6. Replace the tautological no-write assertion (`const databaseWrites = 0`) with spies or
   fakes that would record candidate/association/checksum writes. Exercise both the pure
   refresh and production refresh adapter and assert every write count remains zero.
7. Update the plan context to the user's reduced scope: direct executables and Heroic are
   implemented; Lutris, Bottles, and EmuDeck/Steam ROM Manager are skipped and must
   remain fail-closed. Do not claim all launcher adapters are merged.
8. Preserve the current pure ranking guarantees (confirmed-parent stability, exactly-one
   running/reachable tiers, semantic ties, incomplete/unknown review gates, and stable
   display-only ordering), run the complete quality gates, commit all fixes/tests, clean
   transient artifacts, and recreate the marker.

STATUS: CHANGES_REQUESTED
