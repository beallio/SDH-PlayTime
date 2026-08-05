# Review — grouped-game-parent-ui (round 02)

Branch: `feat/grouped-game-parent-ui`
Reviewed against: `docs/plans/2026-08-05_grouped-game-parent-ui.md`

## Verdict

Changes requested. Round 01 restored explicit additions and corrected the
evidence labels, but the effective group ranking and asynchronous selection
state are still unsafe after an addition.

## Gate status

Reviewed commit `18c2c53ee21271413cfe7e1d8ac311d9a4e1ab3a` directly. Its
round-complete marker is valid and the tree is clean. The full root gate was not
rerun because the behavioral findings below require another implementation
round.

## Required changes

1. Rank the complete explicit proposed group, not only
   `snapshot.existingMembers`. `ranking` and the recommendation badges currently
   use `componentCandidates`, while selected additions are excluded. For an
   isolated reachable anchor, the anchor can be preselected before the user adds
   a running candidate; adding the running candidate neither recomputes the
   recommendation nor updates the proposed parent. Derive ranking from the
   mandatory component plus the currently selected additions. Do not treat every
   offered addition as a group member. Preserve a confirmed backend parent, and
   do not overwrite an explicit manual parent choice, but update an untouched
   advisory preselection when the selected member set changes. The confirmation
   reasons and recommendation badge must describe the same selected group that
   will be sent to the backend. Add regression coverage for a reachable isolated
   anchor followed by a running addition, semantic ties among selected additions,
   removing a recommended addition, and preserving a manual choice.

2. Make addition/parent selection last-user-action-wins and expose pending
   eligibility checks. `ensureAddition()` reads the component coordinator's
   current generation without starting its own selection request. Two rapid
   `selectParent()` calls can both pass the same guard, and the slower first RPC
   can overwrite the newer parent choice. A rapid include-then-remove action can
   similarly re-add the member when the first check completes. Give selection
   operations their own generation/cancellation state, ignore superseded
   results, show which candidate is being checked, and disable confirmation
   while any selected-member or parent eligibility decision is unresolved.
   Restore `mounted.current = true` in the effect setup so React's development
   effect replay cannot leave the mounted guard permanently false. Test
   out-of-order parent checks, include/remove supersession, pending-confirm
   gating, and unmount invalidation through the controller used by the hook—not
   only the request counter in isolation.

3. Do not label every presence candidate as an eligible addition and then reject
   valid current-library entries with a generic verification error. Presence
   deliberately includes current inventory entries that have no `game_dict`
   component yet. For those entries, `getAssociationComponent()` returns
   `ANCHOR_NOT_FOUND`, even though the atomic confirmation API permits a selected
   addition that does not belong to another component and will save its game
   dictionary row. Either treat the structured `ANCHOR_NOT_FOUND` result as an
   eligible unowned singleton when the candidate is still present in the current
   snapshot, or filter such cards out and label the section accurately. Do not
   convert transport/unknown failures into eligibility. Add a service/controller
   test proving the chosen behavior for current untracked inventory, an owned
   component, and a network failure.

4. Strengthen the interaction regression layer so it exercises the decisions
   above as the hook consumes them. The new controller suite currently proves
   only that a standalone counter rejects an older integer; it does not exercise
   the actual async component/addition flow, selection state, or confirmation
   gate and therefore did not catch findings 1-3. Keep the no-new-React-harness
   constraint by moving the relevant transition logic into the testable
   controller and having the hook delegate to it.

STATUS: CHANGES_REQUESTED
