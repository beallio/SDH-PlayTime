"""Release-boundary tests for the vendored safe YAML runtime."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PY_MODULES = ROOT / "py_modules"
VENDORED_REQUIREMENTS = ROOT / "requirements-vendored.txt"
PY_YAML_VERSION = "6.0.3"
PY_YAML_DIST_INFO = f"pyyaml-{PY_YAML_VERSION}.dist-info"
SPEC = importlib.util.spec_from_file_location(
    "release_archive", ROOT / "tools" / "release_archive.py"
)
assert SPEC and SPEC.loader
release_archive = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_archive)


class VendoredSafeYamlTests(unittest.TestCase):
    def test_declared_pin_matches_vendored_metadata_and_license(self) -> None:
        self.assertEqual(
            VENDORED_REQUIREMENTS.read_text(encoding="utf-8").splitlines(),
            [f"PyYAML=={PY_YAML_VERSION}"],
        )

        dist_infos = sorted(PY_MODULES.glob("pyyaml-*.dist-info"))
        self.assertEqual(dist_infos, [PY_MODULES / PY_YAML_DIST_INFO])
        metadata = (dist_infos[0] / "METADATA").read_text(encoding="utf-8")
        self.assertIn("Name: PyYAML\n", metadata)
        self.assertIn(f"Version: {PY_YAML_VERSION}\n", metadata)
        self.assertTrue((dist_infos[0] / "licenses" / "LICENSE").is_file())

    def test_clean_archive_imports_only_vendored_safe_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            archive = release_archive.build_archive(
                ROOT, "3.3.0+beallio.vendor-test", workdir / "PlayTime.zip"
            )
            with zipfile.ZipFile(archive) as zip_file:
                names = set(zip_file.namelist())
                self.assertIn("SDH-PlayTime/requirements-vendored.txt", names)
                self.assertIn("SDH-PlayTime/py_modules/safe_yaml.py", names)
                self.assertIn("SDH-PlayTime/py_modules/yaml/__init__.py", names)
                self.assertIn(
                    f"SDH-PlayTime/py_modules/{PY_YAML_DIST_INFO}/METADATA", names
                )
                self.assertIn(
                    f"SDH-PlayTime/py_modules/{PY_YAML_DIST_INFO}/licenses/LICENSE",
                    names,
                )
                zip_file.extractall(workdir)

            plugin_root = workdir / "SDH-PlayTime"
            environment = os.environ.copy()
            environment["PYTHONNOUSERSITE"] = "1"
            environment["PYTHONPATH"] = os.pathsep.join(
                (str(plugin_root), str(plugin_root / "py_modules"))
            )
            runtime_check = """
from pathlib import Path

from py_modules import safe_yaml, yaml

plugin_modules = Path.cwd() / "py_modules"
assert Path(yaml.__file__).resolve().is_relative_to(plugin_modules.resolve())
assert safe_yaml.__all__ == ("safe_load",)
assert safe_yaml.safe_load(b"game: Hades\\nrunner: wine\\n") == {
    "game": "Hades",
    "runner": "wine",
}
assert safe_yaml.safe_load("- bottles\\n- lutris\\n") == ["bottles", "lutris"]
assert safe_yaml.safe_load("plain metadata") == "plain metadata"

for value, options in (
    ("- not-a-mapping", {"require_mapping": True}),
    ("plain metadata", {"require_mapping": True}),
    ("game: [unterminated", {}),
    ("!!python/object/apply:builtins.eval ['40 + 2']", {}),
    ("x" * 1_048_577, {}),
    (1, {}),
):
    try:
        safe_yaml.safe_load(value, **options)
    except (TypeError, ValueError):
        pass
    else:
        raise AssertionError(f"unsafe YAML input was accepted: {value!r}")
"""
            result = subprocess.run(
                [sys.executable, "-S", "-c", runtime_check],
                cwd=plugin_root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
