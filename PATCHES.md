# Remix patch ledger

This ledger records every change carried by **SDH-PlayTime Beallio Remix** that has an upstream relationship. It is maintained on `remix`, not on contribution branches. Statuses are explicitly date-qualified because upstream state can change.

## Required entry fields

Every patch entry must include:

- **Contribution branch** — the original branch name, including a note if it predates the current naming policy.
- **Immutable commit** — the contribution commit SHA that must never be rewritten.
- **Upstream PR** — the upstream pull request URL or `N/A` with a reason.
- **Remix inclusion commit** — the `remix` commit that includes the immutable work.
- **Upstream status** — `OPEN`, `MERGED`, `CLOSED`, or another precise state, qualified with the verification date.
- **Notes** — intent, compatibility constraints, and any important behavior.

Contribution branches are retained after their upstream pull request closes. Do not delete them just because the ledger is updated.

## Merged parent playtime

| Field | Record |
| --- | --- |
| Contribution branch | `feat/merge-child-playtime` — legacy pre-policy name; retained after PR closure. |
| Immutable commit | [`da1da48`](https://github.com/beallio/SDH-PlayTime-beallio-remix/commit/da1da48efb0babf8017d23ae7cf92f860edd32d5) |
| Upstream PR | [0u73r-h34v3n/SDH-PlayTime#55](https://github.com/0u73r-h34v3n/SDH-PlayTime/pull/55) |
| Remix inclusion commit | [`4580a11`](https://github.com/beallio/SDH-PlayTime-beallio-remix/commit/4580a115a3c80df16071a0fad785725012b0b012) |
| Upstream status | **OPEN**, verified 2026-08-04. |
| Notes | Adds configurable merged-parent playtime. Checksum-derived aliases are intentional and must remain supported. |

When PR #55 changes state, update this entry on `remix` with the new state and verification date; do not amend `da1da48` or rewrite its branch.
