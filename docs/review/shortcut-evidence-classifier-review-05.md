# Review — shortcut-evidence-classifier (round 05)

Branch: `feat/shortcut-evidence-classifier`
Reviewed against: `docs/plans/2026-08-05_shortcut-evidence-classifier.md`

## Verdict

CHANGES_REQUESTED. Review round 4 fixes every structural case except the
generalized known-launcher/emulator suffix rule: unenumerated build labels still
cross the checksum boundary after regular-file approval.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `854435556d7fc592c6b873dcf9b4c85b58064e25` using an isolated repo-local
  `TMPDIR` and the existing repo-local pnpm store.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (222), frontend build,
  Python discovery tests (196), and review-note integrity all pass.
- Exact marker, clean tree, `git diff --check`, and review-note preservation:
  PASS.
- Three independent Terra reviews completed; two found no remaining issue in
  their bounded areas and one reproduced the required change below.

## Required changes

1. Replace the finite build/channel suffix vocabulary with separator-bounded
   prefix matching for every known launcher and emulator stem. Reproduced
   `UbisoftConnect-latest.exe` and `DuckStation-master.exe` still classify as
   direct and are returned by `getPathToGame()` when the regular non-symlink
   resolver succeeds. Any separator-suffixed variant of a known shared-tool
   stem must be rejected before resolver approval. Add non-enumerated suffix
   regressions through `getPathToGame()` with positive resolver evidence.

STATUS: CHANGES_REQUESTED
