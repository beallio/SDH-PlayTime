"""Executable tests for the remix release workflow's version derivation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest

from py_modules import safe_yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "remix-release.yml"


def _workflow_run() -> str:
    workflow = safe_yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    for step in workflow["jobs"]["package"]["steps"]:
        if step.get("name") == "Derive release metadata":
            return step["run"]
    raise AssertionError(
        "The remix workflow is missing the Derive release metadata step."
    )


def _run(env: dict[str, str], cwd: Path = ROOT) -> tuple[int, str, dict[str, str]]:
    if shutil.which("bash") is None:
        raise RuntimeError("bash is required to execute the release metadata step")
    if shutil.which("node") is None:
        raise RuntimeError("node is required to execute the release metadata step")

    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_root = Path(temporary_directory)
        script = temporary_root / "derive-release-metadata.sh"
        script.write_text(_workflow_run(), encoding="utf-8")
        stub_bin = temporary_root / "bin"
        stub_bin.mkdir()
        git_stub = stub_bin / "git"
        git_stub.write_text("#!/bin/sh\nprintf '%s\\n' 1a2b3c4\n", encoding="utf-8")
        git_stub.chmod(git_stub.stat().st_mode | stat.S_IXUSR)
        output_file = temporary_root / "github-output"
        run_env = os.environ.copy()
        run_env.update(env)
        run_env["PATH"] = f"{stub_bin}{os.pathsep}{run_env['PATH']}"
        run_env["GITHUB_OUTPUT"] = str(output_file)
        result = subprocess.run(
            ["bash", str(script)],
            cwd=cwd,
            env=run_env,
            capture_output=True,
            text=True,
            check=False,
        )
        outputs: dict[str, str] = {}
        if output_file.exists():
            for line in output_file.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if separator:
                    outputs[key] = value
        return result.returncode, result.stdout + result.stderr, outputs


class RemixWorkflowMetadataTests(unittest.TestCase):
    def assert_successful_outputs(
        self,
        env: dict[str, str],
        expected_version: str,
        expected_asset_name: str,
    ) -> None:
        returncode, output, outputs = _run(env)
        self.assertEqual(returncode, 0, msg=output)
        self.assertEqual(outputs.get("version"), expected_version)
        self.assertEqual(outputs.get("asset_name"), expected_asset_name)

    def test_tag_derives_stable_release_metadata(self) -> None:
        self.assert_successful_outputs(
            {
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_REF_TYPE": "tag",
                "GITHUB_REF_NAME": "v3.3.1-beallio.12",
            },
            "3.3.1-beallio.12",
            "SDH-PlayTime-beallio-remix-v3.3.1-beallio.12.zip",
        )

    def test_push_derives_date_stamped_nightly_metadata(self) -> None:
        before = datetime.now(timezone.utc).strftime("%Y%m%d")
        returncode, output, outputs = _run(
            {
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_REF_TYPE": "branch",
                "GITHUB_REF_NAME": "remix",
            }
        )
        after = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.assertEqual(returncode, 0, msg=output)
        self.assertIn(
            outputs.get("version"),
            {
                f"3.3.1-beallio.12.dev.{before}.g1a2b3c4",
                f"3.3.1-beallio.12.dev.{after}.g1a2b3c4",
            },
        )
        self.assertEqual(
            outputs.get("asset_name"), "SDH-PlayTime-beallio-remix-nightly.zip"
        )

    def test_pull_request_derives_date_stamped_pr_metadata(self) -> None:
        before = datetime.now(timezone.utc).strftime("%Y%m%d")
        returncode, output, outputs = _run(
            {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_REF_TYPE": "branch"}
        )
        after = datetime.now(timezone.utc).strftime("%Y%m%d")
        self.assertEqual(returncode, 0, msg=output)
        self.assertIn(
            outputs.get("version"),
            {
                f"3.3.1-beallio.12.dev.{before}.g1a2b3c4",
                f"3.3.1-beallio.12.dev.{after}.g1a2b3c4",
            },
        )
        self.assertEqual(
            outputs.get("asset_name"),
            "SDH-PlayTime-beallio-remix-pr-1a2b3c4.zip",
        )

    def test_manual_dispatch_derives_stable_release_metadata(self) -> None:
        self.assert_successful_outputs(
            {"GITHUB_EVENT_NAME": "workflow_dispatch", "DISPATCH_VERSION": ""},
            "3.3.1-beallio.12",
            "SDH-PlayTime-beallio-remix-manual-3.3.1-beallio.12.zip",
        )

    def test_tag_version_must_match_the_manifests(self) -> None:
        returncode, output, _ = _run(
            {
                "GITHUB_EVENT_NAME": "push",
                "GITHUB_REF_TYPE": "tag",
                "GITHUB_REF_NAME": "v9.9.9",
            }
        )
        self.assertEqual(returncode, 1)
        self.assertIn(
            "Tag version must exactly match package.json and plugin.json.", output
        )

    def test_build_metadata_in_the_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cwd = Path(temporary_directory)
            for name in ("package.json", "plugin.json"):
                (cwd / name).write_text(
                    json.dumps({"version": "3.3.0+beallio.11"}), encoding="utf-8"
                )
            returncode, output, _ = _run(
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_TYPE": "branch"}, cwd
            )
        self.assertEqual(returncode, 1)
        self.assertIn(
            "Remix versions must not use SemVer build metadata: Decky ignores it when comparing versions.",
            output,
        )

    def test_mismatched_manifests_are_rejected_on_every_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            cwd = Path(temporary_directory)
            (cwd / "package.json").write_text(
                json.dumps({"version": "3.3.1-beallio.11"}), encoding="utf-8"
            )
            (cwd / "plugin.json").write_text(
                json.dumps({"version": "3.3.1-beallio.12"}), encoding="utf-8"
            )
            returncode, output, _ = _run(
                {"GITHUB_EVENT_NAME": "push", "GITHUB_REF_TYPE": "branch"}, cwd
            )
        self.assertEqual(returncode, 1)
        self.assertIn("package.json and plugin.json versions must be identical.", output)


if __name__ == "__main__":
    unittest.main()
