# Review — shortcut-evidence-classifier (round 04)

Branch: `feat/shortcut-evidence-classifier`
Reviewed against: `docs/plans/2026-08-05_shortcut-evidence-classifier.md`

## Verdict

CHANGES_REQUESTED. The resolver gate now blocks symlinks and unproven direct
paths, but build/channel suffixes and cross-launcher structural parsing still
leave shared binaries or malformed commands checksum-eligible; one valid
Bottles form is also rejected.

## Gate status

- Static/frontend gates and Bun tests (192): PASS at
  `fdd92f519cb5aea502c72a8382e6df2452c8e864`.
- Root Python discovery was interrupted by an environmental `/tmp` tmpfs
  exhaustion (`sqlite3.OperationalError: database or disk is full`), not an
  assertion failure. The tree remains clean and later gates must run with
  `TMPDIR` redirected to the repo-local ignored temp directory.
- Exact marker, `git diff --check`, and preservation of review notes 01-03:
  PASS.
- Three independent Terra reviews completed; one found no lifecycle issue and
  two reproduced the required parser changes below.

## Required changes

1. Reject build/channel-suffixed variants of known Windows launchers and
   emulators before regular-file resolver approval. Bounded stem/prefix matching
   must catch examples such as `UbisoftConnect-beta.exe` and
   `DuckStation-preview.exe`; a regular file proves reachability, not game
   identity. Add version/channel fixtures.
2. Reject unexpected leftover operators and absolute command paths in every
   launcher grammar, including extensionless secondary commands. Reproduced
   Heroic `&& /usr/bin/other` and EmuDeck `... /usr/bin/other` forms must be
   ambiguous rather than checksum-eligible.
3. Treat an option-like token or shell separator as a missing operand for known
   operand-taking options unless that option explicitly permits such a value.
   `Game.gba --config --verbose` must not return the earlier ROM.
4. Preserve valid Bottles separated executable syntax. Structural validation
   must consume known launcher option operands before looking for extra
   executable tokens so `--executable "C:\\Games\\Game.exe"` remains valid.
   Add separated and equals-form regression coverage.

STATUS: CHANGES_REQUESTED
