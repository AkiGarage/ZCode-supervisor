import unittest

from tools.zcode_eval.pypi_readiness import PackageIndexStatus, evaluate_readiness


READY_RELEASE = {
    "tagName": "v0.0.1",
    "isDraft": False,
    "isPrerelease": False,
    "assets": [
        {"name": "zcode-supervisor-v0.0.1.tar.gz"},
        {"name": "SHA256SUMS"},
    ],
}

READY_ENVIRONMENTS = {
    "testpypi": {
        "protection_rules": ["branch_policy"],
        "branch_policies": [{"name": "v*", "type": "tag"}],
    },
    "pypi": {
        "protection_rules": ["required_reviewers", "branch_policy"],
        "branch_policies": [{"name": "v*", "type": "tag"}],
    },
}


def evaluate(**overrides):
    defaults = {
        "target": "testpypi",
        "tag": "v0.0.1",
        "version": "0.0.1",
        "trusted_publishers_configured": False,
        "release": READY_RELEASE,
        "environments": READY_ENVIRONMENTS,
        "package_statuses": {
            "testpypi": PackageIndexStatus("testpypi", 404, []),
            "pypi": PackageIndexStatus("pypi", 404, []),
        },
        "owner_repo": "AkiGarage/ZCode-supervisor",
        "package": "zcode-supervisor",
        "workflow": "pypi-publish.yml",
    }
    defaults.update(overrides)
    return evaluate_readiness(**defaults)


class PyPIReadinessTests(unittest.TestCase):
    def test_blocks_until_trusted_publishers_are_manually_confirmed(self):
        payload = evaluate()

        self.assertFalse(payload["ok"])
        self.assertIn("Create pending Trusted Publishers", payload["manual_actions"][0])
        self.assertIsNone(payload["next_workflow_command"])

    def test_allows_testpypi_dispatch_after_manual_confirmation(self):
        payload = evaluate(trusted_publishers_configured=True)

        self.assertTrue(payload["ok"])
        self.assertIn("publish_target=testpypi", payload["next_workflow_command"])

    def test_blocks_pypi_until_testpypi_has_version(self):
        payload = evaluate(target="pypi", trusted_publishers_configured=True)

        self.assertFalse(payload["ok"])
        self.assertIn("TestPyPI does not show", " ".join(payload["errors"]))

    def test_allows_pypi_after_testpypi_version_exists(self):
        payload = evaluate(
            target="pypi",
            trusted_publishers_configured=True,
            package_statuses={
                "testpypi": PackageIndexStatus("testpypi", 200, ["0.0.1"]),
                "pypi": PackageIndexStatus("pypi", 404, []),
            },
        )

        self.assertTrue(payload["ok"])
        self.assertIn("publish_target=pypi", payload["next_workflow_command"])

    def test_requires_pypi_reviewer_gate(self):
        environments = {
            **READY_ENVIRONMENTS,
            "pypi": {
                "protection_rules": ["branch_policy"],
                "branch_policies": [{"name": "v*", "type": "tag"}],
            },
        }
        payload = evaluate(trusted_publishers_configured=True, environments=environments)

        self.assertFalse(payload["ok"])
        self.assertIn("reviewer approval", " ".join(payload["errors"]))


if __name__ == "__main__":
    unittest.main()
