import contextlib
import io
import importlib.util
from importlib.machinery import SourceFileLoader
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/update-homebrew-formula"


def load_script():
    loader = SourceFileLoader("update_homebrew_formula", str(SCRIPT))
    spec = importlib.util.spec_from_loader("update_homebrew_formula", loader)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load update-homebrew-formula script")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HomebrewFormulaTests(unittest.TestCase):
    def test_formula_marks_generated_wrappers_executable(self):
        formula = Path(__file__).resolve().parents[1] / "packaging/homebrew/zcode-supervisor.rb"
        text = formula.read_text(encoding="utf-8")

        self.assertIn("wrapper.chmod 0755", text)

    def test_release_workflow_checks_out_tag_ref(self):
        workflow = Path(__file__).resolve().parents[1] / ".github/workflows/release-artifacts.yml"
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("ref: refs/tags/${{ inputs.tag }}", text)
        self.assertIn('^v[0-9]+\\.[0-9]+\\.[0-9]+$', text)
        self.assertIn('git show-ref --verify --quiet "refs/tags/${TAG}"', text)
        self.assertIn("actions/attest-build-provenance@v4", text)
        self.assertIn("attestations: write", text)
        self.assertIn("contents: write", text)
        self.assertIn("id-token: write", text)
        self.assertNotIn("artifact-metadata:", text)

    def test_update_formula_text_replaces_url_version_and_sha(self):
        module = load_script()
        text = """class ZcodeSupervisor < Formula
  url "https://example.invalid/old.tar.gz"
  version "0.0.1"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
end
"""

        updated = module.update_formula_text(
            text,
            version="0.0.2",
            url="https://github.com/AkiGarage/ZCode-supervisor/releases/download/v0.0.2/zcode-supervisor-v0.0.2.tar.gz",
            sha256="a" * 64,
        )

        self.assertIn('version "0.0.2"', updated)
        self.assertIn('sha256 "' + "a" * 64 + '"', updated)
        self.assertIn("releases/download/v0.0.2/zcode-supervisor-v0.0.2.tar.gz", updated)

    def test_formula_updater_defaults_to_public_product_repo_releases(self):
        module = load_script()

        self.assertEqual(module.DEFAULT_OWNER_REPO, "AkiGarage/ZCode-supervisor")
        self.assertEqual(
            module.release_url(
                module.DEFAULT_OWNER_REPO,
                "v0.0.3",
                "zcode-supervisor-v0.0.3.tar.gz",
            ),
            "https://github.com/AkiGarage/ZCode-supervisor/releases/download/v0.0.3/zcode-supervisor-v0.0.3.tar.gz",
        )

    def test_formula_uses_homebrew_python_libexec_unversioned_python(self):
        formula = Path(__file__).resolve().parents[1] / "packaging/homebrew/zcode-supervisor.rb"
        text = formula.read_text(encoding="utf-8")

        self.assertIn('homepage "https://github.com/AkiGarage/ZCode-supervisor"', text)
        self.assertIn('Formula["python@3.11"].opt_libexec/"bin/python3"', text)
        self.assertIn('Formula["python@3.11"].opt_libexec/"bin"', text)

    def test_update_formula_script_dry_run_uses_artifact_checksum(self):
        module = load_script()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            formula = root / "zcode-supervisor.rb"
            artifact = root / "zcode-supervisor-v0.0.2.tar.gz"
            formula.write_text(
                """class ZcodeSupervisor < Formula
  url "https://example.invalid/old.tar.gz"
  version "0.0.1"
  sha256 "0000000000000000000000000000000000000000000000000000000000000000"
end
""",
                encoding="utf-8",
            )
            artifact.write_bytes(b"release artifact\n")

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = module.main([
                    "--version",
                    "v0.0.2",
                    "--artifact",
                    str(artifact),
                    "--formula",
                    str(formula),
                    "--dry-run",
                ])

            self.assertEqual(exit_code, 0)
            self.assertIn('"ok": true', output.getvalue())
            self.assertIn("example.invalid/old.tar.gz", formula.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
