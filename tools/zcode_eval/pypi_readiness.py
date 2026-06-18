"""Preflight checks for the guarded PyPI/TestPyPI release path."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


DEFAULT_OWNER_REPO = "AkiGarage/ZCode-supervisor"
DEFAULT_PACKAGE = "zcode-supervisor"
DEFAULT_TAG = "v0.0.1"
DEFAULT_SOURCE_DIGEST = "6525b8a41371a687a9b9ef3513da38eaab52cf9e"
DEFAULT_WORKFLOW = "pypi-publish.yml"
RELEASE_WORKFLOW = "release-artifacts.yml"
ENVIRONMENTS = ("testpypi", "pypi")


@dataclass(frozen=True)
class PackageIndexStatus:
    name: str
    status: int | None
    versions: list[str]
    error: str | None = None


def split_owner_repo(owner_repo: str) -> tuple[str, str]:
    parts = owner_repo.split("/", 1)
    if len(parts) != 2 or not all(parts):
        raise ValueError("owner repo must look like OWNER/REPO")
    return parts[0], parts[1]


def package_json_url(index: str, package: str) -> str:
    host = "test.pypi.org" if index == "testpypi" else "pypi.org"
    return f"https://{host}/pypi/{package}/json"


def fetch_package_status(index: str, package: str, timeout: float = 10.0) -> PackageIndexStatus:
    url = package_json_url(index, package)
    request = urllib.request.Request(url, headers={"User-Agent": "zcode-supervisor-release-preflight"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        versions = sorted(body.get("releases", {}).keys())
        return PackageIndexStatus(index, 200, versions)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return PackageIndexStatus(index, 404, [])
        return PackageIndexStatus(index, exc.code, [], str(exc))
    except (OSError, json.JSONDecodeError) as exc:
        return PackageIndexStatus(index, None, [], str(exc))


def run_json(command: list[str]) -> Any:
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    return json.loads(completed.stdout)


def fetch_release(owner_repo: str, tag: str) -> dict[str, Any]:
    return run_json(
        [
            "gh",
            "release",
            "view",
            tag,
            "-R",
            owner_repo,
            "--json",
            "tagName,isDraft,isPrerelease,assets,publishedAt,url",
        ]
    )


def fetch_environments(owner_repo: str) -> dict[str, dict[str, Any]]:
    owner, repo = split_owner_repo(owner_repo)
    environments = run_json(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/environments",
            "--jq",
            ".environments",
        ]
    )
    result: dict[str, dict[str, Any]] = {}
    for environment in environments:
        name = environment["name"]
        policies = run_json(
            [
                "gh",
                "api",
                f"repos/{owner}/{repo}/environments/{name}/deployment-branch-policies",
                "--jq",
                ".branch_policies",
            ]
        )
        result[name] = {
            "deployment_branch_policy": environment.get("deployment_branch_policy"),
            "protection_rules": [rule.get("type") for rule in environment.get("protection_rules", [])],
            "branch_policies": [{"name": policy.get("name"), "type": policy.get("type")} for policy in policies],
        }
    return result


def expected_publishers(owner_repo: str, package: str, workflow: str) -> list[dict[str, str]]:
    owner, repo = split_owner_repo(owner_repo)
    return [
        {
            "index": environment,
            "project_name": package,
            "owner": owner,
            "repository_name": repo,
            "workflow_filename": workflow,
            "environment_name": environment,
        }
        for environment in ENVIRONMENTS
    ]


def has_v_tag_policy(environment: dict[str, Any] | None) -> bool:
    if not environment:
        return False
    for policy in environment.get("branch_policies", []):
        if policy.get("name") == "v*" and policy.get("type") == "tag":
            return True
    return False


def release_is_ready(release: dict[str, Any], tag: str) -> list[str]:
    errors: list[str] = []
    assets = {asset.get("name") for asset in release.get("assets", [])}
    expected_archive = f"zcode-supervisor-{tag}.tar.gz"
    if release.get("tagName") != tag:
        errors.append(f"release tag mismatch: expected {tag}")
    if release.get("isDraft"):
        errors.append("GitHub Release is still draft")
    if release.get("isPrerelease"):
        errors.append("GitHub Release is marked prerelease")
    if expected_archive not in assets:
        errors.append(f"missing release asset: {expected_archive}")
    if "SHA256SUMS" not in assets:
        errors.append("missing release asset: SHA256SUMS")
    return errors


def evaluate_readiness(
    *,
    target: str,
    tag: str,
    version: str,
    trusted_publishers_configured: bool,
    release: dict[str, Any],
    environments: dict[str, dict[str, Any]],
    package_statuses: dict[str, PackageIndexStatus],
    owner_repo: str,
    package: str,
    workflow: str,
) -> dict[str, Any]:
    errors = release_is_ready(release, tag)
    warnings: list[str] = []
    manual_actions: list[str] = []

    for environment_name in ENVIRONMENTS:
        environment = environments.get(environment_name)
        if environment is None:
            errors.append(f"missing GitHub environment: {environment_name}")
        elif not has_v_tag_policy(environment):
            errors.append(f"GitHub environment {environment_name} is not restricted to v* tags")
    pypi_environment = environments.get("pypi", {})
    if "required_reviewers" not in pypi_environment.get("protection_rules", []):
        errors.append("GitHub environment pypi does not require reviewer approval")

    if not trusted_publishers_configured:
        manual_actions.append("Create pending Trusted Publishers on both TestPyPI and PyPI.")

    testpypi_status = package_statuses["testpypi"]
    pypi_status = package_statuses["pypi"]
    if testpypi_status.status is None:
        warnings.append(f"could not read TestPyPI status: {testpypi_status.error}")
    if pypi_status.status is None:
        warnings.append(f"could not read PyPI status: {pypi_status.error}")

    if target == "testpypi":
        if testpypi_status.status == 200 and version in testpypi_status.versions:
            errors.append(f"TestPyPI already has {package} {version}; do not re-upload same version")
        if pypi_status.status == 200 and version in pypi_status.versions:
            errors.append(f"PyPI already has {package} {version}; do not re-upload same version")
        next_command = (
            f"gh workflow run {workflow} -R {owner_repo} --ref {tag} "
            f"-f tag={tag} -f publish_target=testpypi"
        )
    elif target == "pypi":
        if testpypi_status.status != 200 or version not in testpypi_status.versions:
            errors.append(f"TestPyPI does not show {package} {version}; verify TestPyPI before PyPI")
        if pypi_status.status == 200 and version in pypi_status.versions:
            errors.append(f"PyPI already has {package} {version}; do not re-upload same version")
        next_command = (
            f"gh workflow run {workflow} -R {owner_repo} --ref {tag} "
            f"-f tag={tag} -f publish_target=pypi"
        )
    else:
        raise ValueError(f"unknown target: {target}")

    safe_to_dispatch = not errors and trusted_publishers_configured
    if not trusted_publishers_configured:
        warnings.append("publisher setup cannot be verified via public PyPI JSON APIs before upload")

    return {
        "ok": safe_to_dispatch,
        "target": target,
        "tag": tag,
        "version": version,
        "package": package,
        "owner_repo": owner_repo,
        "safe_to_dispatch": safe_to_dispatch,
        "errors": errors,
        "warnings": warnings,
        "manual_actions": manual_actions,
        "expected_publishers": expected_publishers(owner_repo, package, workflow),
        "package_indexes": {
            name: {
                "status": status.status,
                "versions": status.versions,
                "error": status.error,
            }
            for name, status in package_statuses.items()
        },
        "next_workflow_command": next_command if safe_to_dispatch else None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("testpypi", "pypi"), required=True)
    parser.add_argument("--owner-repo", default=DEFAULT_OWNER_REPO)
    parser.add_argument("--package", default=DEFAULT_PACKAGE)
    parser.add_argument("--tag", default=DEFAULT_TAG)
    parser.add_argument("--version", default=DEFAULT_TAG.removeprefix("v"))
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument(
        "--trusted-publishers-configured",
        action="store_true",
        help="Assert that pending publishers were created in the PyPI/TestPyPI account UIs.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        release = fetch_release(args.owner_repo, args.tag)
        environments = fetch_environments(args.owner_repo)
        package_statuses = {
            index: fetch_package_status(index, args.package)
            for index in ENVIRONMENTS
        }
        payload = evaluate_readiness(
            target=args.target,
            tag=args.tag,
            version=args.version,
            trusted_publishers_configured=args.trusted_publishers_configured,
            release=release,
            environments=environments,
            package_statuses=package_statuses,
            owner_repo=args.owner_repo,
            package=args.package,
            workflow=args.workflow,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 2
    except (OSError, ValueError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
