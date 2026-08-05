# Review — zero-time-association-candidates (round 01)

Branch: `feat/zero-time-association-candidates`
Reviewed against: `docs/plans/2026-08-05_zero-time-association-candidates.md`

## Verdict

CHANGES_REQUESTED. Candidate exposure is correctly neutral about lifecycle
state, but the widened read has one unreviewed legacy-eligibility consequence
and nullable names are not updated safely during confirmation.

## Gate status

- `scripts/orchestration/run-quality-gates`: PASS at
  `0a2125eff343f2c8012f973b5164103d38fed3eb`.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (131), frontend build,
  Python discovery tests (193), and review-note integrity all pass.
- Exact marker, clean tree, and `git diff --check remix...HEAD`: PASS.
- Three independent Terra reviews completed; one found no lifecycle/data-boundary
  issue and two reported the required changes below.

## Required changes

1. Preserve or explicitly define legacy eligibility semantics for
   `AssociationManager.create_association()` and
   `Games.link_game_to_game_with_checksum()`. They use `get_game()` as an
   existence guard, so the new left join makes dictionary-only zero-time
   identities eligible where they were previously rejected. Prefer a
   candidate-specific read or explicit `has_overall_time` signal if strictness
   should remain; otherwise add compatibility tests and document the intended
   expansion. The raw candidate API must remain neutral about installed/current
   state either way.
2. Make `_save_game_dict()` update nullable stored names safely. SQLite's
   `NULL != :game_name` is not true, leaving a selected `NULL`-named identity
   unchanged while the confirmation response reports the submitted name. Add a
   regression test that confirms a nullable zero-time candidate, verifies the
   stored and response names agree, retains exactly one dictionary row, and
   creates no synthetic `overall_time` row.

STATUS: CHANGES_REQUESTED
