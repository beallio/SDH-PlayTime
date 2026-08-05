# Review — atomic-game-parent-confirmation (round 01)

Branch: `feat/atomic-game-parent-confirmation`
Reviewed against: `docs/plans/2026-08-05_atomic-game-parent-confirmation.md`

## Verdict

The grouped API and transaction boundary are well structured and all repository gates
pass, but confirmation can currently report success without materializing the required
complete star and cannot add explicitly selected new identities. Those are core plan
invariants, so this round requires changes before integration.

## Gate status

- Valid round-complete marker stamped at `071a12cc29ef20e4319dc444a5a8546087846dad`.
- Clean tree and `git diff --check remix...HEAD` passed.
- Ruff/format/ty, TypeScript/Biome, 127 Bun tests, production build, 183 Python tests,
  and review-note integrity passed at the stamped HEAD.

## Required changes

1. **HIGH — always canonicalize a confirmed component into a complete star.** The DAO
   skips delete/recreate when the proposed parent already equals the current confirmed
   parent. A checksum-connected member with a missing explicit edge therefore remains
   outside the migration-10 star even though confirmation returns success. After stale
   evidence and membership validation, rewrite the complete star idempotently even for
   same-parent confirmation. Add a regression with one checksum-only member missing its
   explicit edge.

2. **HIGH — support explicitly selected additions safely.** The DAO rejects every
   selected ID outside the current component as `UNEXPECTED_MEMBER`, so the planned
   explicit additions and `game_dict` upserts are impossible. Accept selected new
   identities with submitted names, reject identities already owned by another component,
   and include the additions in the same atomic star rewrite. Test a valid addition,
   cross-component rejection, duplicate/invalid additions, and rollback of both identity
   upserts and edges after injected failure.

3. **MEDIUM — bound confirmation requests before hashing or SQL.** Add explicit maximum
   member count and identifier/name length validation in the request/RPC layer and enforce
   it again before DAO parameter construction. Oversized input must return
   `INVALID_REQUEST`, not exceed SQLite limits or persist arbitrarily large names. Cover
   boundary and over-limit cases.

4. **LOW — complete detach/dissolve RPC and client coverage.** Add success, malformed
   input, structured backend error, and network-fallback tests for both newly exposed
   removal methods in `py_modules/tests/main_test.py` and `src/test/association.spec.ts`.

STATUS: CHANGES_REQUESTED
