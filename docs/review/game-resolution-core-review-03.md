# Review — game-resolution-core (round 03)

Branch: `feat/game-resolution-core`
Reviewed against: `docs/plans/2026-08-05_game-resolution-core.md`

## Verdict

CHANGES_REQUESTED. Review round 2 fixes bounded worker admission and normal
mount uncertainty, but the shell exclusion remains incomplete and ancestor-link
removable evidence has an eight-hop boundary error.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `84a88d68257061ab60dc5f64965d23e64b0bd088` using isolated repo-local temp and
  the matching pnpm store.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests, frontend build, backend
  Python tests (218), root package tests (18), and review integrity pass.
- Exact marker, clean tree, `git diff --check`, and reviews 01-02 preservation:
  PASS.
- Three independent Terra reviews completed; one found no process issue and two
  reproduced the remaining changes below.

## Required changes

1. Complete the common shell exclusion at both submitted and resolved-target
   boundaries. Add at least `csh`, `pwsh`, `powershell`, `cmd`, `xonsh`, `nu`,
   and `busybox`, including executable extension/stem variants, and exercise
   each directly and through a game-looking symlink. These shared command
   interpreters must never become checksum-eligible.
2. Fix the bounded ancestor-symlink traversal off-by-one. After consuming the
   eighth permitted hop, evaluate the resulting target for removable-volume
   evidence; only a ninth required hop should become uncertainty. Add exact
   eight-hop and over-limit regressions.

STATUS: CHANGES_REQUESTED
