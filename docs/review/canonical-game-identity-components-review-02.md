# Review — canonical-game-identity-components (round 02)

Branch: `feat/canonical-game-identity-components`
Reviewed against: `docs/plans/2026-08-05_canonical-game-identity-components.md`

## Verdict

Round 2 fixes the duplicated checksum contributions, checksum-child response,
session ordering, main name projections, legacy aggregation helpers, and the originally
identified batch-query paths. Independent semantic review found three remaining
canonical-read inconsistencies, so the branch is not yet ready to merge.

## Gate status

- Round-complete marker is valid and stamped at `72067603adda9b7fd84a2b73ee923462a310e748`.
- Working tree is clean; `git diff --check remix...HEAD` passes.
- Orchestrator reran the complete quality gates at the stamped HEAD: Ruff/format/ty,
  TypeScript/Biome, 125 Bun tests, production build, 171 Python tests, and review-note
  deletion check all pass.
- Review note 01 remains committed and every item is covered by code/tests except for
  the related projection/query paths below.

## Required changes

1. **MEDIUM — normalize `Games.get_by_id()` through the canonical-name helper.**
   `py_modules/games.py` still builds the canonical `Game` directly from `get_game()`.
   An empty confirmed-parent name therefore returns `""` while dictionary/daily/overall
   projections return `"Unknown Game"`. Use the shared name contract and extend the
   empty-name regression to this API.

2. **MEDIUM — remove the remaining canonical-read N+1 paths.**
   `Games.get_by_id()` calls `get_game()` once per component member and may query the
   canonical member twice. Alias-filtered daily pagination also invokes separate
   `has_prev`/`has_next` database transactions for each component member. Add/consume
   batched DAO operations so both paths remain proportional to the requested component,
   and add spy/query-count tests that cover a multi-member component.

3. **LOW — remove or centralize the unused alternate last-session helper.**
   `Statistics.get_last_sessions_from_grouped_sessions()` is unreferenced after the
   canonical overall path landed and retains an independent timestamp-selection
   algorithm. Remove it, or delegate to the active shared behavior with a caller/test;
   do not leave another dormant projection algorithm.

STATUS: CHANGES_REQUESTED
