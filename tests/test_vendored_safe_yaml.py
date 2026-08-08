"""Release-boundary tests for the vendored safe YAML runtime."""

from __future__ import annotations

import importlib.util
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
        self.assertEqual(
            release_archive.VENDORED_PYYAML_SOURCE_SHA256,
            "d76623373421df22fb4cf8817020cbb7ef15c725b9d5e45f17e189bfc384190f",
        )
        self.assertIn("yaml/composer.py", release_archive.VENDORED_PYYAML_FILE_HASHES)

    def test_clean_archive_imports_backend_without_host_pyyaml_or_native_code(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workdir = Path(temporary_directory)
            archive = release_archive.build_archive(
                ROOT, "3.3.1-beallio.vendor-test", workdir / "PlayTime.zip"
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
                for relative_path in release_archive.VENDORED_PYYAML_FILE_HASHES:
                    self.assertIn(f"SDH-PlayTime/py_modules/{relative_path}", names)
                zip_file.extractall(workdir)

            plugin_root = workdir / "SDH-PlayTime"
            poison_package = workdir / "poison" / "yaml"
            poison_package.mkdir(parents=True)
            (poison_package / "__init__.py").write_text("", encoding="utf-8")
            (poison_package / "_yaml.py").write_text(
                "raise AssertionError('host native YAML binding was imported')\n",
                encoding="utf-8",
            )
            runtime_check = """
import os
from pathlib import Path
import sys
import types

plugin_root = Path.cwd()
poison_root = plugin_root.parent / "poison"
# Reproduce the plugin's append-only path setup with a preinstalled top-level
# yaml package available first. The vendored package must never import it.
sys.path.extend((str(poison_root), str(plugin_root), str(plugin_root / "py_modules")))
from py_modules import safe_yaml, yaml

plugin_modules = plugin_root / "py_modules"
assert Path(yaml.__file__).resolve().is_relative_to(plugin_modules.resolve())
assert "yaml" not in sys.modules
assert not any(
    name == "_yaml" or name.startswith("yaml.") or name.startswith("py_modules.yaml._yaml")
    for name in sys.modules
)
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

runtime_dir = plugin_root / "runtime"
runtime_dir.mkdir()
os.environ.update(
    DECKY_USER_HOME=str(plugin_root / "user-home"),
    DECKY_PLUGIN_RUNTIME_DIR=str(runtime_dir),
    DECKY_PLUGIN_DIR=str(plugin_root),
)
decky = types.ModuleType("decky")
decky.logger = types.SimpleNamespace()
sys.modules["decky"] = decky
sys.path.insert(0, str(plugin_root))
import main
from py_modules.game_resolution import (
    DirectExecutableAdapter,
    GameChecksumCoordinator,
    GameResolutionCoordinator,
    HeroicAdapter,
)

assert main.GameChecksumCoordinator is GameChecksumCoordinator
assert GameResolutionCoordinator and DirectExecutableAdapter and HeroicAdapter
assert "yaml" not in sys.modules
            """
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-c", runtime_check],
                cwd=plugin_root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_safe_load_rejects_deep_and_aliased_structures_as_value_errors(
        self,
    ) -> None:
        from py_modules import safe_yaml

        lines = [f"{'  ' * depth}child:" for depth in range(33)]
        lines.append(f"{'  ' * 33}value: true")
        deeply_nested_mapping = "\n".join(lines)

        for value in (deeply_nested_mapping, "&cycle [*cycle]"):
            with self.subTest(value=value[:20]), self.assertRaises(ValueError):
                safe_yaml.safe_load(value)


if __name__ == "__main__":
    unittest.main()
