# Upstream contribution flow

This repository has two deliberately separate histories:

- `master` is a fast-forward mirror of `upstream/master`.
- `remix` is the independent Beallio Remix integration branch.

Use a short-lived-for-work but retained-for-history `contrib/<slug>` branch for changes proposed to [upstream SDH-PlayTime](https://github.com/0u73r-h34v3n/SDH-PlayTime). A contribution branch contains only upstream-suitable code and tests; it must never carry remix branding, versioning, documentation, workflows, release automation, or patch-ledger edits.

## Start from upstream, not remix

Never branch a contribution from `remix`, never merge `remix` into `master`, and do not use `master` for remix-only work. Refresh the local upstream mirror before every contribution:

```bash
set -euo pipefail

git fetch upstream
git switch master
git branch --set-upstream-to=upstream/master master
git merge --ff-only upstream/master
git switch -c 'contrib/<slug>' upstream/master
```

Replace `<slug>` with a descriptive lowercase slug. Make only the change that upstream can accept, and keep remix-specific work on `remix`.

## Validate, commit, and open the upstream PR

Run the complete relevant suite before committing. For a normal frontend/backend change, use:

```bash
uv run --with pytest pytest
bun test
pnpm exec tsc --noEmit
pnpm exec biome format .
pnpm exec biome lint .
pnpm build
```

Then create a conventional commit, push the contribution branch, and open the upstream pull request:

```bash
git add path/to/upstream-suitable-file
git commit -m 'feat(scope): describe the upstream change'
git push -u origin 'contrib/<slug>'
gh pr create \
  --repo 0u73r-h34v3n/SDH-PlayTime \
  --base master \
  --head 'beallio:contrib/<slug>'
```

Retain `contrib/<slug>` after the PR closes. Its contribution commit is immutable evidence, not a disposable delivery branch.

## Record and integrate a contribution into the remix

Do not add remix documentation, release metadata, workflows, or `PATCHES.md` changes on the contribution branch. After creating or updating the upstream PR, switch to `remix` and update the patch ledger there.

If the remix should carry the exact contribution before upstream merges it, merge the immutable contribution history without rebasing or amending it:

```bash
git switch remix
git merge --no-ff 'contrib/<slug>'
```

Record the contribution branch, immutable commit, upstream PR, inclusion merge, date-qualified upstream status, and notes in [PATCHES.md](PATCHES.md). If a later remix-only adjustment is needed, make it as a separate commit on `remix`; never rewrite the upstream contribution commit to include it.

## Sync after upstream changes

When upstream merges the contribution or otherwise advances, first fast-forward the mirror, then merge upstream into the remix branch:

```bash
git fetch upstream
git switch master
git merge --ff-only upstream/master
git switch remix
git merge upstream/master
```

Update the relevant `PATCHES.md` entry on `remix` with the new upstream status and verification date. `master` remains an upstream mirror; `remix` is never merged back into it.
