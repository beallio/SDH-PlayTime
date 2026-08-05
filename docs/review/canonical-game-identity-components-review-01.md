# Review — canonical-game-identity-components (round 01)

Branch: `feat/canonical-game-identity-components`
Reviewed against: `docs/plans/2026-08-05_canonical-game-identity-components.md`

## Verdict

The shared component model is a sound direction and the full repository gates pass, but
the first integration round introduces correctness regressions in report aggregation and
checksum output. The branch is not ready to merge until the duplicated-row behavior and
compatibility issues below are fixed with focused regression coverage.

## Gate status

- Round-complete marker is valid and stamped at `b69e9864e518f79e9c0e9a06995ed6b2db3eac6b`.
- Working tree was clean and `git diff --check remix...HEAD` passed.
- Ruff check/format and `ty` passed.
- TypeScript/Biome passed.
- Bun passed: 125 tests.
- Production build passed.
- Python unittest suite passed: 167 tests.
- Review-note deletion check passed.

## Required changes

1. **HIGH — prevent checksum fan-out from multiplying playtime and sessions.**
   `py_modules/db/dao.py` daily and overall/session queries join each play/session row to
   every checksum row owned by a game. A member with two checksums is emitted twice, and
   the new canonical merge then sums/retains both copies. Refactor the query/data flow so
   each underlying play interval/session contributes exactly once regardless of checksum
   count. Add a regression where a transitive bridge member has two checksum records and
   assert its duration, day total, and session identities occur once in both daily and
   overall projections.

2. **MEDIUM — restore checksum RPC child filtering or canonicalize it explicitly.**
   `py_modules/games.py::get_games_checksum()` now exposes explicitly associated child
   rows that the endpoint previously hid, while merely sorting through the component map.
   Preserve the legacy de-duplicated response or return one deliberately canonicalized
   row per component without leaking children. Add an explicit parent/child checksum
   endpoint regression test that fixes the chosen compatibility contract.

3. **MEDIUM — normalize empty canonical names consistently.** In the daily, overall, and
   game-dictionary projections, an empty canonical name can be emitted as `""` when the
   canonical member owns a row but becomes `"Unknown Game"` on fallback paths. Apply the
   same canonical-name helper everywhere and cover both canonical-with-playtime and
   fallback cases.

4. **MEDIUM — preserve deterministic reverse-chronological session order after merging.**
   Overall component sessions currently inherit DAO grouping by game ID/date and are no
   longer globally sorted after merge. Sort the merged session list using the prior
   public ordering contract and add a component with interleaved member session dates.

5. **MEDIUM — remove the new whole-library/N+1 query regressions.** A single-game daily
   request with aliases currently loads the whole period and rebuilds the component map;
   overall statistics performs `get_game()` per component; game dictionary projection
   performs checksum reads per member. Batch the identity/name/checksum inputs and keep a
   filtered request proportional to its requested component. Add query-count or spy-based
   tests that fence these access patterns without overfitting SQL text.

6. **LOW — eliminate the dormant second association algorithm.** The legacy public
   `combine_games_by_association`, `_apply_associations_to_playtime_info`, and
   `_apply_associations_to_daily_statistics` helpers remain available with independent
   aggregation and alias-order behavior. Remove them if truly unused, or delegate them to
   the shared component model with compatibility tests. Do not leave a future caller able
   to bypass canonical identity rules.

STATUS: CHANGES_REQUESTED
