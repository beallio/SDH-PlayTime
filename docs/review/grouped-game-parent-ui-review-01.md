# Review — grouped-game-parent-ui (round 01)

Branch: `feat/grouped-game-parent-ui`
Reviewed against: `docs/plans/2026-08-05_grouped-game-parent-ui.md`

## Verdict

Changes requested. The grouped presentation is directionally correct, but the
selector cannot create a new association, some resolver evidence is presented
incorrectly, and overlapping refreshes can leave the confirmation payload based
on stale state.

## Gate status

Reviewed commit `7fc5187389a2e6ce2188129e1e04e669cfab2dde` directly against the
plan and the merged atomic confirmation/presence contracts. The full quality
gate was not rerun because the functional blockers below require another
implementation round first.

## Required changes

1. Restore a working association-creation path. `useGamesForAssociation` derives
   `componentCards` only from `snapshot.existingMembers`, then requires every
   existing member to be selected. For an isolated anchor, the only selectable
   member is the anchor itself, so confirmation writes no edge and the user
   cannot associate it with another game. Present the existing component as the
   required member set and offer eligible candidates outside that component as
   explicit additions. Do not silently select the entire inventory. Keep all
   existing members mandatory, allow the user to add one or more eligible
   isolated candidates, require the proposed parent to be selected, and send the
   complete explicit selection in `selected_members`. Reject or clearly explain
   candidates already owned by another component rather than depending on a
   late opaque `UNEXPECTED_MEMBER` response. Cover the isolated-anchor creation
   case and multi-member reparent case.

2. Preserve the resolver's reason instead of mapping every non-native
   `unreachable` result to `Drive disconnected`. The resolver already
   distinguishes `drive_disconnected` from `payload_missing` (and can report
   other unreachable reasons such as `kind_mismatch`). Show `Drive disconnected`
   only for the explicit disconnected-volume reason. Show `Installation missing`
   for supported missing-install/payload evidence, and use a conservative label
   such as `Status unavailable` for evidence that does not justify either claim.
   Add tests for all three mappings. Keep the manual-parent warning in every
   unreachable/unknown case.

3. Expose launcher evidence on duplicate-name cards as required by the plan.
   `sourceLabel` currently collapses every supported launcher shortcut to
   `Non-Steam shortcut`, so a direct shortcut and a Heroic shortcut with the same
   title/ID-adjacent presentation cannot be distinguished by launcher. Carry the
   already-classified direct/Heroic launcher kind through the presence/view-model
   boundary and render it without adding Lutris, Bottles, or EmuDeck support.
   Unknown/unsupported shortcuts must remain explicitly unknown, not inferred.

4. Make component/presence loading race-safe. Rapid anchor changes can allow an
   older `getAssociationComponent` response to overwrite the newer anchor.
   `refresh()` also awaits a new presence snapshot and then calls a
   closure-bound `loadComponent` that ranks with the previous `presence`, which
   can retain an obsolete recommendation. Use a request generation (or
   equivalent cancellation guard), ignore post-unmount/out-of-date responses,
   and pass the just-refreshed presence snapshot directly into the component
   ranking. Do not clear a presence-refresh failure immediately inside the
   subsequent component load. Test out-of-order anchor responses and changed
   recommendation evidence across refresh.

5. Do not render an association RPC failure as a successful empty state.
   `AssociationService.getAllAssociations()` catches every transport failure and
   returns `[]`, so `useAssociations`' error branch is unreachable and the UI says
   `No game associations configured` during a backend outage. Return a
   result/error (or rethrow after logging) so the hook can show the failure and
   avoid replacing previously loaded groups with a false empty list. Cover the
   service/hook decision with Bun tests.

6. Add the interaction-level regression coverage promised by tasks 9 and 10.
   The new suite exercises only pure display helpers; it does not cover backend
   service interactions, creation with added members, stale/conflict refresh,
   out-of-order refresh, detach/dissolve refresh behavior, or context-menu anchor
   parity. Keep the repository free of a new React rendering framework by
   extracting testable controller/event-decision helpers where needed.

STATUS: CHANGES_REQUESTED
