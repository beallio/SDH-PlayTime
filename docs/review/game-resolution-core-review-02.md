# Review — game-resolution-core (round 02)

Branch: `feat/game-resolution-core`
Reviewed against: `docs/plans/2026-08-05_game-resolution-core.md`

## Verdict

CHANGES_REQUESTED. Review round 1 closes the production-routing and most
filesystem gaps, but its timeout strategy leaks unbounded threads and three
filesystem uncertainty/exclusion edge cases remain.

## Gate status

- Full `scripts/orchestration/run-quality-gates`: PASS at
  `ddefdae2c2327a3b5c8c2f9af74dc71dd4989b3f` using isolated repo-local temp and
  the matching pnpm store.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (224), frontend build,
  backend Python tests (214), root package tests (18), and review integrity pass.
- Exact marker, clean tree, `git diff --check`, and review-01 preservation:
  PASS.
- Three independent Terra reviews completed; all remaining required changes
  below were reproduced.

## Required changes

1. Replace per-entry abandoned daemon threads with a bounded worker/admission
   model and explicit saturation behavior. Repeated never-returning probes must
   not grow live threads or memory without limit after timeouts. Add a
   regression that issues multiple permanently stalled batches, verifies timely
   ordered responses, and asserts a fixed worker ceiling/lifecycle.
2. Reject known shell basenames/stems and extension variants both before probing
   and after symlink resolution (`sh`, `bash`, `dash`, `zsh`, `fish`, etc.). A
   relocated executable ELF shell such as `/home/deck/Games/bash` or
   `bash.x86_64` must never be checksum-eligible.
3. Preserve uncertainty when mount-table evidence is unavailable. If the mount
   provider returns `None` or raises, a missing `/run/media/...` payload must be
   `unknown/probe_failure` (or equivalent uncertainty), not conclusive
   `unreachable/payload_missing`. Only a successfully read mount table may prove
   missing/disconnected state.
4. Resolve removable-volume evidence through symlinked ancestor components, not
   only a leaf symlink. A candidate under `~/Library` where that directory links
   to an absent `/run/media/...` target must report `drive_disconnected` rather
   than generic `payload_missing`, within bounded link traversal.

STATUS: CHANGES_REQUESTED
