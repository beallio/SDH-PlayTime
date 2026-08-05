# Review — atomic-game-parent-confirmation (round 02)

Branch: `feat/atomic-game-parent-confirmation`
Reviewed against: `docs/plans/2026-08-05_atomic-game-parent-confirmation.md`

## Verdict

CHANGES_REQUESTED. The first review round is substantially addressed, but the
confirmation result and request-boundary contract are not yet internally
consistent across stored components and related RPCs.

## Gate status

- `scripts/orchestration/run-quality-gates`: PASS at
  `5b70256a9c4d4f986c5dd76e469f9ecae0f225ee`
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (130), frontend build,
  Python discovery tests (188), and review-note integrity all pass.
- Worktree and `git diff --check remix...HEAD`: clean.
- Independent review: three Terra reviewers; two reported the required changes
  below and one reported no remaining code or gate issue.

## Required changes

1. Bound the recomputed persisted component before constructing member-ID SQL
   or mutating its star. A valid-size submission against an already oversized
   stored component must return `INVALID_REQUEST`, rather than
   `INCOMPLETE_MEMBER_SELECTION` or a SQLite parameter-limit failure. Add a
   regression test proving rejection occurs before member-name lookup or star
   mutation.
2. After atomically upserting explicitly selected additions, recompute the
   returned component members and fingerprint. The success DTO must describe
   the post-commit component consistently; its concurrency token must not be
   stale immediately upon return.
3. Apply the identifier/component-size bounds consistently to grouped reads and
   the read, detach, and dissolve RPC boundaries before building SQL parameter
   lists. Overlong identifiers and oversized components must return the
   structured `INVALID_REQUEST` contract. Add boundary and over-limit tests for
   these paths.

STATUS: CHANGES_REQUESTED
