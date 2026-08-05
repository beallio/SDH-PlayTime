# Review — shortcut-evidence-classifier (round 03)

Branch: `feat/shortcut-evidence-classifier`
Reviewed against: `docs/plans/2026-08-05_shortcut-evidence-classifier.md`

## Verdict

CHANGES_REQUESTED. Review round 2 closes its exact AppImage and unknown-option
cases, but equivalent Windows-executable, symlink, ROM-token, and cross-launcher
structural bypasses remain checksum-eligible.

## Gate status

- `scripts/orchestration/run-quality-gates`: PASS at
  `b17ba44dbd87535bd72a0e80b76d03329b61c99e`.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (192), frontend build,
  Python discovery tests (196), and review-note integrity all pass.
- Exact marker, clean tree, `git diff --check`, and preservation of review notes
  01-02: PASS.
- Three independent Terra reviews completed; each reproduced at least one
  generalized fail-closed bypass below.

## Required changes

1. Apply the positive-evidence boundary consistently to `.exe`/`.x86*` direct
   candidates and suffix-bearing symlink shapes. Finite exact-name denial still
   exposes shared executables such as `UbisoftConnect.exe`, `Playnite.exe`, and
   `DuckStation-qt-x64-ReleaseLTCG.exe`; lexical suffixes alone cannot prove a
   game payload or reject symlinks. Normalize known launcher/emulator stems and
   do not let the compatibility path reach checksumming until injected resolver
   filesystem evidence proves a regular, non-symlink target. Add unlisted and
   versioned executable plus suffix-bearing symlink fixtures.
2. Reuse the full literal-token validation for EmuDeck ROM candidates and every
   payload-bearing classifier. ROM tokens containing placeholders, globs,
   braces, process substitutions, or shell operators (`*.gba`, `%ROM%.gba`,
   `A|B.gba`) must fail closed. Also reject Bash extglob forms such as
   `@(Games)`, `+(Games)`, and `!(Games)` in direct and ROM paths.
3. Enforce structural completeness across every launcher classifier, not only
   direct classification: reject multiple executable-token command shapes and
   known operand-taking options with missing operands before returning
   recognized evidence. Add Heroic/EmuDeck dual-executable and trailing
   `--config`-without-value regressions.

STATUS: CHANGES_REQUESTED
