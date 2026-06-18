import contextlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

import tomllib

from tools import zcode_control
from scripts import verify_python_wheel_for_tests


ROOT = Path(__file__).resolve().parents[1]


class DistributionPackagingTests(unittest.TestCase):
    def test_pyproject_declares_uvx_safe_console_scripts_and_node_assets(self):
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        scripts = pyproject["project"]["scripts"]
        self.assertEqual(
            scripts["zcode-install-repo"],
            "tools.zcode_supervisor.repo_setup:install_repo_entrypoint",
        )
        self.assertEqual(scripts["zcode-auto-route"], "tools.zcode_supervisor.auto_route:auto_route_entrypoint")
        self.assertEqual(scripts["zcodectl"], "tools.zcode_control:main")
        self.assertEqual(pyproject["tool"]["setuptools"]["package-data"]["tools.zcode_control"], ["*.mjs"])

    def test_pypi_workflow_uses_trusted_publishing_and_build_only_default(self):
        workflow = (ROOT / ".github/workflows/pypi-publish.yml").read_text(encoding="utf-8")

        self.assertIn("default: build-only", workflow)
        self.assertIn("environment:\n      name: testpypi", workflow)
        self.assertIn("environment:\n      name: pypi", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("pypa/gh-action-pypi-publish@release/v1", workflow)
        self.assertIn("repository-url: https://test.pypi.org/legacy/", workflow)
        self.assertNotIn("PYPI" "_TOKEN", workflow)
        self.assertNotIn("pass" "word:", workflow)

    def test_verify_python_wheel_rejects_missing_node_controller_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            wheel = Path(tmp) / "zcode_supervisor-0.0.1-py3-none-any.whl"
            with zipfile.ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "zcode_supervisor-0.0.1.dist-info/entry_points.txt",
                    "\n".join(sorted(verify_python_wheel_for_tests.REQUIRED_ENTRY_POINTS)),
                )

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify_python_wheel_for_tests.main([str(wheel)]), 1)

    def test_zcodectl_wrapper_reports_missing_node_without_traceback(self):
        stderr = io.StringIO()

        with mock.patch("tools.zcode_control.subprocess.call", side_effect=FileNotFoundError):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(zcode_control.main(["--help"]), 127)

        self.assertIn("Node.js on PATH", stderr.getvalue())

    def test_zcodectl_wrapper_invokes_bundled_node_controller(self):
        with mock.patch("tools.zcode_control.subprocess.call", return_value=0) as call:
            self.assertEqual(zcode_control.main(["cli-preflight"]), 0)

        command = call.call_args.args[0]
        self.assertEqual(command[0], "node")
        self.assertTrue(command[1].endswith("zcodectl.mjs"))
        self.assertEqual(command[2:], ["cli-preflight"])


if __name__ == "__main__":
    unittest.main()
