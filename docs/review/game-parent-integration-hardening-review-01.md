# Review — game-parent-integration-hardening (round 01)

Branch: `feat/game-parent-integration-hardening`
Reviewed against: `docs/plans/2026-08-05_game-parent-integration-hardening.md`

## Verdict

Changes requested. The individual regression fences are useful, but the branch
does not yet establish the shared cross-layer contract or the complete
disconnect invariant required by the plan, and the support matrix currently
overstates its source evidence.

## Gate status

Reviewed commit `83bd9069fb7d391f268c0eedead1eff95a54a8cb` directly. Its
round-complete marker is valid and the tree is clean. The root full gate was not
rerun because the integration/documentation findings below require another
round first.

## Required changes

1. Tie the backend RPC projection and frontend cache/Steam-overview tests to one
   durable contract fixture. `test_grouped_confirmation_projects_one_canonical_parent_everywhere`
   produces `explicit-parent` plus four aliases, while the Bun cache test
   independently reconstructs a similar object and the overview test uses the
   unrelated alias `123`. Those tests can now drift while all remain green.
   Add a bounded JSON fixture containing the canonical projected record and a
   numeric Steam alias. Have the Python RPC test assert its all-time/daily/
   per-game/dictionary projection against that fixture, and have the Bun cache
   and overview tests consume the same fixture. The RPC must remain the source
   of the asserted DTO shape; do not turn the fixture into production input.
   This should prove that an explicit zero-time parent which is not the lexical
   checksum leader reaches the exact cache keys and Steam overview alias used by
   the frontend.

2. Complete the direct/Heroic disconnect contract at the integration boundary.
   Current coverage separately proves a direct presence transition, a generic
   confirmed-parent ranking rule, a Heroic adapter transition, and checksum
   behavior fed by a synthetic `SequencedResolver`. Add fixture-backed coverage
   for each supported path showing the same sequence: a confirmed parent remains
   effective while its current shortcut becomes `drive_disconnected`, the
   refresh performs no association/checksum/database write, checksum generation
   does not read/hash a payload while unavailable, and reconnecting permits a
   checksum only after the real direct/Heroic adapter proves a regular file.
   Reuse the existing dependency-injected adapters and fixtures; do not add live
   mounts or launcher execution.

3. Correct the support matrix and user wording to reflect source-backed
   evidence. The `Verified repository commits` column currently lists this
   repository's implementation commits, not the upstream fixture provenance
   requested by the plan. Cite the repository and commit recorded by each
   source-addressable fixture (for example
   `Heroic-Games-Launcher/HeroicGamesLauncher@d6366b34084be43369f24ff04a50dab39ce5a454`),
   and keep local implementation/fence commits in a separately labelled column
   if they remain useful. Do not advertise Nile as verified: there is no
   positive Nile fixture/test in the current corpus. Either add a genuine
   source-addressable Nile fixture and positive/negative coverage or mark Nile
   unverified/unknown. Apply the same evidence rule to the README support claim.

4. Keep the release archive's documentation links self-contained. The packaged
   `README.md` links to `DEVELOPER.md`, but the archive builder includes only the
   README, so that relative link is broken in an extracted release. Either make
   `DEVELOPER.md` a required packaged file and cover its absence in the archive
   validator tests, or use an explicit repository URL whose target is valid for
   the documented release branch.

STATUS: CHANGES_REQUESTED
