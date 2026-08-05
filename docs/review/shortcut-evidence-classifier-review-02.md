# Review — shortcut-evidence-classifier (round 02)

Branch: `feat/shortcut-evidence-classifier`
Reviewed against: `docs/plans/2026-08-05_shortcut-evidence-classifier.md`

## Verdict

CHANGES_REQUESTED. Review round 1 fixed its named fixtures, but generalized
AppImage, emulator-option, and ambiguous-executable variants still bypass the
fail-closed checksum boundary.

## Gate status

- `scripts/orchestration/run-quality-gates`: PASS at
  `c37e62331ea35511b81c23ae08b71c487dfa6f44`.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (177), frontend build,
  Python discovery tests (196), and review-note integrity all pass.
- Exact marker, clean tree, `git diff --check`, and review-note preservation:
  PASS.
- Three independent Terra reviews completed; two reproduced the generalized
  bypasses below and one found no process/test-discovery issue.

## Required changes

1. Stop treating unproven `.AppImage` commands as direct game payloads.
   Finite exact-name denial still allows versioned launchers and other shared
   tools (`Heroic-2.16.1.AppImage`, `Lutris.AppImage`, `Cemu.AppImage`,
   `DuckStation.AppImage`, `Cartridges.AppImage`) to reach checksumming. Apply
   the plan's positive-evidence rule: withhold `payloadPath` for an AppImage
   unless direct-game identity is actually proven. Normalize launcher stems
   where classification still needs them, and add versioned/variant fixtures.
   Do not treat suffix-bearing or unresolved symlinks as sufficient payload
   evidence.
2. Fail closed on unknown EmuDeck/emulator option grammar. An unrecognized
   option's following token must never be reconsidered as a positional ROM;
   reproduced examples include `--appendconfig ...not-a-rom.iso` and
   `--firmware ...firmware.bin`. Either use complete launcher-specific grammar
   or make unknown option arity ambiguous. Add ROM-suffixed option-operand
   regressions.
3. Require exactly one literal, structurally valid executable token for direct
   classification. Reject Steam placeholders, globs, braces, process
   substitution, shell operators, and multiple executable-token command shapes.
   Add `%command%`, wildcard, shell syntax, and dual-executable fixtures.

STATUS: CHANGES_REQUESTED
