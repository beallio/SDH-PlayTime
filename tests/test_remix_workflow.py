"""Regression checks for the isolated remix release workflow contract."""

from __future__ import annotations

from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "remix-release.yml"
).read_text(encoding="utf-8")


class RemixWorkflowTests(unittest.TestCase):
    def test_only_remix_events_trigger_the_workflow(self) -> None:
        self.assertIn("branches: [remix]", WORKFLOW)
        self.assertIn("tags: ['v*\\+beallio.*']", WORKFLOW)
        self.assertIn("pull_request:", WORKFLOW)
        self.assertIn("workflow_dispatch:", WORKFLOW)

    def test_all_archives_depend_on_the_complete_quality_gate(self) -> None:
        for command in (
            "uvx ruff@0.16.0 check .",
            "uvx ruff@0.16.0 format --check .",
            "uvx ty@0.0.64 check main.py py_modules --exclude 'py_modules/tests/**'",
            "uv run --no-project --with pytest pytest",
            "bun test",
            "pnpm exec tsc --noEmit",
            "pnpm exec biome format .",
            "pnpm exec biome lint .",
            "pnpm build",
        ):
            self.assertIn(command, WORKFLOW)
        self.assertIn("needs: quality", WORKFLOW)
        self.assertIn("remix-production-dist-${{ github.run_id }}", WORKFLOW)

    def test_pnpm_is_explicitly_pinned_for_the_v9_lockfile(self) -> None:
        self.assertEqual(WORKFLOW.count("uses: pnpm/action-setup@v6"), 2)
        self.assertEqual(WORKFLOW.count("version: 10"), 2)

    def test_decky_build_and_canonical_archive_are_both_required(self) -> None:
        self.assertIn("DECKY_CLI_VERSION: '0.0.8'", WORKFLOW)
        self.assertIn("gh release download", WORKFLOW)
        self.assertNotIn("curl", WORKFLOW)
        self.assertNotIn("wget", WORKFLOW)
        self.assertIn("plugin build", WORKFLOW)
        self.assertNotIn("test -f /tmp/decky-build/SDH-PlayTime.zip", WORKFLOW)
        self.assertIn("shopt -s nullglob", WORKFLOW)
        self.assertIn("decky_archives=(/tmp/decky-build/*.zip)", WORKFLOW)
        self.assertIn('"${#decky_archives[@]}" -ne 1', WORKFLOW)
        self.assertIn('unzip -tq "${decky_archives[0]}"', WORKFLOW)
        self.assertIn("tools/release_archive.py build", WORKFLOW)
        self.assertIn("tools/release_archive.py validate", WORKFLOW)

    def test_canonical_package_restores_a_clean_quality_frontend(self) -> None:
        self.assertIn('dist_dir="$GITHUB_WORKSPACE/dist"', WORKFLOW)
        self.assertIn('sudo rm -rf -- "$dist_dir"', WORKFLOW)
        self.assertIn('sudo chown "$(id -u):$(id -g)" "$dist_dir"', WORKFLOW)
        self.assertLess(
            WORKFLOW.index("Clear compatibility build output from trusted frontend"),
            WORKFLOW.index("Restore quality frontend for canonical package"),
        )
        self.assertLess(
            WORKFLOW.index("Restore quality frontend for canonical package"),
            WORKFLOW.index("tools/release_archive.py build"),
        )

    def test_only_publish_jobs_can_write_and_prs_never_publish(self) -> None:
        self.assertEqual(WORKFLOW.count("contents: write"), 2)
        self.assertIn("publish-remix-nightly:", WORKFLOW)
        self.assertIn(
            "github.event_name == 'push' && github.ref == 'refs/heads/remix'", WORKFLOW
        )
        self.assertIn("publish-stable-release:", WORKFLOW)
        self.assertIn(
            "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')",
            WORKFLOW,
        )

    def test_release_paths_validate_versions_and_prevent_nightly_regression(
        self,
    ) -> None:
        self.assertIn('version="${GITHUB_REF_NAME#v}"', WORKFLOW)
        self.assertIn('checked_package_version" != "$version"', WORKFLOW)
        self.assertIn('checked_plugin_version" != "$version"', WORKFLOW)
        self.assertIn('version="${base_version}+beallio.g${short_sha}"', WORKFLOW)
        self.assertIn("group: remix-nightly-publication", WORKFLOW)
        self.assertIn('test "$(git rev-parse origin/remix)" = "$GITHUB_SHA"', WORKFLOW)
        self.assertIn("git push --force origin refs/tags/remix-nightly", WORKFLOW)


if __name__ == "__main__":
    unittest.main()
