# Review — heroic-game-resolution (round 02)

Branch: `feat/heroic-game-resolution`
Reviewed against: `docs/plans/2026-08-05_heroic-game-resolution.md`

## Verdict

CHANGES_REQUESTED. Review round 1 closes its named source, bound, identity, and
archive gaps, but duplicate JSON keys are collapsed before those conflict checks
can run.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `708771369ca5d0c2622b64fe205d0a5e767c3114` with isolated repo-local temp.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests, frontend build, backend
  Python tests (236), root package tests (18), and review integrity pass.
- Exact marker, clean tree, `git diff --check`, removal of temporary artifacts,
  and review-01 preservation: PASS.
- Three independent Terra reviews completed; two found no remaining issue and
  one reproduced the change below.

## Required changes

1. Detect JSON duplicate object keys before `json.loads` collapses them with
   last-key-wins semantics. Use an `object_pairs_hook` or equivalent bounded
   parser path: identical duplicate values may be deduplicated deterministically,
   while conflicting top-level app keys and record fields (`app_name`, runner,
   install/payload fields, etc.) must fail closed as ambiguous/malformed. Add
   Legendary/top-level and nested record-field regressions, including the
   reproduced two-`"game"` install-path conflict.

STATUS: CHANGES_REQUESTED
