# Review — vendored-safe-yaml-runtime (round 01)

Branch: `feat/vendored-safe-yaml-runtime`
Reviewed against: `docs/plans/2026-08-05_vendored-safe-yaml-runtime.md`

## Verdict

CHANGES_REQUESTED. The archive is self-contained in isolated smoke tests, but
the checked-in runtime can still bind to host PyYAML/native code, archive
validation does not prove the exact dependency payload, adversarial structures
escape the wrapper's failure contract, and the local gate omits the new package
tests.

## Gate status

- Existing `scripts/orchestration/run-quality-gates`: PASS at
  `26f884799b16cb9d0ad7b23158d68236af8d9ee2` with isolated repo-local temp.
- Ruff, Ruff format, ty, TypeScript, Biome, Bun tests (224), frontend build,
  Python discovery tests (196), and review-note integrity all pass.
- The implementer's broader pytest/package checks passed, but root orchestration
  does not yet discover them; this is a required change below.
- Exact marker, clean tree, and `git diff --check`: PASS.
- Three independent Terra reviews completed; all required changes below were
  reproduced against the stamped commit.

## Required changes

1. Eliminate host PyYAML/native binding. `py_modules/yaml/cyaml.py` performs an
   absolute `yaml._yaml` import, and plugin path setup appends paths, so a host
   package can win. Package only the pure-Python runtime or otherwise remove the
   absolute import path; test with a poison/preinstalled top-level `yaml` and
   assert no host `yaml*` or native module is imported. Keep isolated `-I -S`
   archive coverage as a second fence.
2. Enforce reproducible upstream integrity and an exact packaged runtime
   manifest. Pin the upstream PyYAML 6.0.3 archive SHA-256 plus exact allowlisted
   file hashes (runtime modules, metadata, license), reject missing transitive
   modules and every extra/development/compiled file, and validate both source
   and extracted archive. Add missing `composer.py` plus extra `backdoor.py`,
   `_yaml.pyx`, and comparable negative tests; do not trust self-declared
   metadata alone.
3. Bound adversarial YAML structure and normalize failures. Deeply nested small
   input must not leak `RecursionError`, and aliases must not return cyclic
   object graphs. Enforce depth/node/alias-cycle policy suitable for launcher
   metadata and translate parser/recursion/structure violations to the wrapper's
   documented `ValueError` surface. Add deep nesting and alias-cycle tests.
4. Include the root vendoring/archive test modules in the normal local
   orchestration quality gate. A local round-complete marker must exercise
   `tests/test_vendored_safe_yaml.py` and `tests/test_release_archive.py`, not
   rely only on the broader GitHub pytest workflow.

STATUS: CHANGES_REQUESTED
