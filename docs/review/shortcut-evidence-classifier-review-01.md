# Review — shortcut-evidence-classifier (round 01)

Branch: `feat/shortcut-evidence-classifier`
Reviewed against: `docs/plans/2026-08-05_shortcut-evidence-classifier.md`

## Verdict

CHANGES_REQUESTED. The structured classifier and test corpus are a strong
foundation, but several ambiguous command shapes still promote shared launchers,
emulators, or option operands to checksum-eligible game payloads.

## Gate status

- `scripts/orchestration/run-quality-gates`: PASS at
  `40587ed30b58ae2f78521c688769e2a30f8965ff`.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (155), frontend build,
  Python discovery tests (196), and review-note integrity all pass.
- Exact marker, clean tree, and `git diff --check remix...HEAD`: PASS.
- Three independent Terra reviews completed; all required changes below were
  reproduced against the stamped commit.

## Required changes

1. Fail closed for syntactically uncertain native, AppImage, emulator, launcher,
   and extensionless commands. The short denylist currently allows arbitrary
   extensionless binaries plus examples such as `rpcs3.AppImage`,
   `Ryujinx.AppImage`, `Bottles.AppImage`, and `gamescope` to become direct
   payloads and therefore shared checksums. Require positive direct-game
   evidence, or withhold `payloadPath` until a resolver proves it. Add
   source-backed fixtures for Heroic AppImage and Proton, generic Flatpak,
   additional emulator/launcher AppImages, wrapper chains, custom launchers,
   and symlink shapes.
2. Restrict EmuDeck ROM extraction to supported launcher grammar and ignore
   option operands. A path such as `--config /home/deck/config/mgba.cfg` must
   not become the ROM payload. Cover configuration, BIOS, core, log, and
   metadata paths with no ROM present; return ambiguous when position cannot be
   proven.
3. Require coherent, anchored launcher evidence. A Heroic/Lutris URI embedded
   in an unrelated executable or conflicting launcher chain must not establish
   that launcher, and competing launcher kinds must be ambiguous. Add mismatched
   executable/URI, mismatched Flatpak-app/URI, and multiple-launcher fixtures.
4. Stop Bottles identity parsing at `--`. Identity-like flags after the
   separator are payload arguments, not launcher evidence. Cover cases with and
   without valid pre-separator identity.
5. Preserve literal filesystem path bytes, decode URI components exactly once,
   and reject unresolved shell expressions in payload candidates. Global token
   URI-decoding currently mutates literal `%20`/`%25` filenames, while paths
   containing variables or command substitutions can be accepted. Add direct
   literal-path, URI single-decode, variable, and substitution fixtures.

STATUS: CHANGES_REQUESTED
