# Review — game-resolution-core (round 01)

Branch: `feat/game-resolution-core`
Reviewed against: `docs/plans/2026-08-05_game-resolution-core.md`

## Verdict

CHANGES_REQUESTED. The bounded DTO/RPC skeleton is sound, but production callers
can still bypass backend reachability, backend direct validation is weaker than
the untrusted frontend grammar, failure isolation/timing are incomplete, and
several filesystem/package lifecycle invariants are missing.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `843740b29f4839564d1b1569849f306682b74f53` using isolated repo-local temp.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests, frontend build, backend
  Python tests (208), root package tests (18), and review-note integrity pass.
- Exact marker, clean tree, and `git diff --check`: PASS.
- Three independent Terra reviews completed; one found no process/test issue and
  two reproduced the required changes below.

## Required changes

1. Make the coordinator the only production reachability/checksum boundary for
   every payload-bearing shortcut. Remove the classifier `payloadPath` fallback
   that lets unsupported EmuDeck ROMs bypass backend probes. Add a safe direct
   candidate path so plan-required AppImage and extensionless native forms can
   reach backend proof, while unsupported launcher kinds remain structured
   `unknown` and legacy callers receive no path.
2. Mirror the complete literal-token and structural policy backend-side for
   untrusted DTOs. Reject `%VAR%`, `@(...)`, `+(...)`, `!(...)`, other shell
   syntax, multiple commands, and arbitrary non-payload files before probing.
   Define backend-owned direct types: Windows executables, AppImages, and native
   executables with executable-mode/format evidence; reject shells, launchers,
   emulators, wrappers, and data files such as `notes.txt`.
3. Revalidate resolved symlink targets against the wrapper/launcher/shell policy.
   A game-looking link to Wine, Proton, a launcher, emulator, or shell must not
   become reachable. Retain bounded link traversal and regular-file checks.
4. Preserve removable-volume reasoning for broken symlink targets. Use bounded
   `lstat`/link-target evidence so a home link into an absent
   `/run/media/...` target reports `drive_disconnected`, not generic
   `payload_missing`.
5. Add explicit per-entry and batch time budgets plus per-entry exception
   isolation. A stalled provider/probe must not block indefinitely, and an
   unexpected failure for one entry must preserve ordered one-result-per-input
   cardinality. Reserve batch-level errors for top-level request validation.
6. Add `unreachable` to the payload-status contract for conclusive missing,
   disconnected, and kind-mismatch evidence. Keep `unknown` for unsupported,
   malformed, permission, timeout, and incomplete/probe uncertainty.
7. Require the complete startup-critical `py_modules/game_resolution/` runtime
   package in canonical archive validation and test rejection when any imported
   module, including `coordinator.py`, is absent.

STATUS: CHANGES_REQUESTED
