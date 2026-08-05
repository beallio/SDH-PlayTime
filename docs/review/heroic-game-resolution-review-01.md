# Review — heroic-game-resolution (round 01)

Branch: `feat/heroic-game-resolution`
Reviewed against: `docs/plans/2026-08-05_heroic-game-resolution.md`

## Verdict

CHANGES_REQUESTED. Heroic payload proof and external-volume behavior are
correct, but valid Flatpak syntax is rejected, source roots can contaminate one
another, record identity consistency and metadata resource bounds are missing,
and release validation does not require the new adapter.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `513c69c7339e55ea77297b23a31771099297209e` with isolated repo-local temp.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (225), frontend build,
  backend Python tests (231), root package tests (18), and review integrity pass.
- Exact marker, clean tree, and `git diff --check`: PASS.
- Three independent Terra reviews completed; all changes below were reproduced.

## Required changes

1. Accept the source-backed Heroic Flatpak grammar with one optional `--`
   between `com.heroicgameslauncher.hgl` and the URI. The existing recognized
   frontend fixture must resolve end-to-end rather than becoming backend
   `malformed`; add the fixture-shaped integration regression.
2. Preserve launcher packaging/source context when choosing metadata roots.
   Native/AppImage evidence must not be invalidated by an irrelevant unreadable
   Flatpak root, and Flatpak evidence must not indiscriminately merge native
   records. Deduplicate truly identical evidence; conflicting relevant records
   remain ambiguous.
3. Validate all present record identity aliases and runner/source fields. If
   `app_name`, `appName`, mapping keys, runner fields, or comparable identifiers
   disagree with each other or the requested source, fail closed as ambiguous
   rather than silently selecting one value.
4. Bound Heroic metadata before/during parsing: bytes per file, JSON depth/nodes,
   records per collection, record field lengths, and accumulated candidates.
   Oversize/malformed input must not leave worker slots consuming unbounded
   resources and must return the structured incomplete/unknown result. Add
   byte, nesting, record-count, and candidate-limit tests.
5. Add `py_modules/game_resolution/heroic.py` to canonical archive required
   runtime files and add a missing-adapter rejection test.

STATUS: CHANGES_REQUESTED
