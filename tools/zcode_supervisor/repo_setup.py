"""Install repo-local Codex-to-ZCode routing hints."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROUTING_FILE = Path(".codex/zcode-routing.json")
DELEGATION_FILE = Path(".codex/ZCODE_DELEGATION.md")
AGENTS_FILE = Path("AGENTS.md")
VISION_MCP_FILE = Path(".agents/mcp.json")
AGENTS_BEGIN = "<!-- BEGIN ZCODE SUPERVISOR ROUTING -->"
AGENTS_END = "<!-- END ZCODE SUPERVISOR ROUTING -->"
DEFAULT_VISION_MCP_SERVER = "zai-mcp-server"
DEFAULT_VISION_MCP_PACKAGE = "@z_ai/mcp-server"


@dataclass(frozen=True)
class InstallResult:
    repo: Path
    routing_file: Path
    delegation_file: Path
    agents_file: Path
    vision_mcp_file: Path
    agents_status: str
    vision_mcp_status: str
    written: list[str]
    skipped: list[str]


def zcode_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def routing_payload(
    repo: Path,
    *,
    vision_mcp_server: str = DEFAULT_VISION_MCP_SERVER,
    vision_mcp_package: str = DEFAULT_VISION_MCP_PACKAGE,
) -> dict[str, Any]:
    root = zcode_repo_root()
    supervisor = root / "tools/zcode_supervisor/zcode_supervisor.py"
    controller = root / "tools/zcode_control/zcodectl.mjs"
    return {
        "version": 1,
        "repo": str(repo.resolve()),
        "orchestrator": "codex",
        "implementation_worker": "zcode",
        "routing_mode": "auto",
        "control_repo": str(root),
        "policy": {
            "codex_owns": ["planning", "orchestration", "audit", "validation", "final_acceptance"],
            "zcode_owns": ["bounded_implementation"],
            "never_delegate": ["secret_handling", "destructive_git_ops", "final_acceptance"],
            "codex_direct_edit_allowed": ["read_only", "trivial", "zcode_unavailable_recovery"],
            "ask_user_before": ["destructive", "migration", "credentials", "production_risk"],
            "skip_triggers": ["no-zcode"],
        },
        "defaults": {
            "mode": "Auto Edit",
            "effort": "max",
            "task_class": "root-cause",
            "risk_budget": "low",
            "workspace_kind": "regular",
            "usage_snapshot_source": "auto",
            "max_attempts": 2,
            "retry_delay_ms": 60000,
            "max_auto_retries": 2,
        },
        "paths": {
            "zcode_supervisor": str(supervisor),
            "zcodectl": str(controller),
            "packets": ".codex/zcode/packets",
            "snapshots": ".codex/zcode/snapshots",
            "runs": ".codex/zcode/runs",
        },
        "vision": {
            "service": vision_mcp_server,
            "mcp_file": str(VISION_MCP_FILE),
            "mcp_package": vision_mcp_package,
        },
        "trigger": (
            "For implementation work in this repo, Codex should plan the task, "
            "run auto-route, create a bounded packet, run ZCode, then audit and validate the result. "
            "Skip ZCode for read-only answers, trivial one-line edits, or when the user says no-zcode."
        ),
    }


def delegation_doc(
    repo: Path,
    *,
    vision_mcp_server: str = DEFAULT_VISION_MCP_SERVER,
    vision_mcp_package: str = DEFAULT_VISION_MCP_PACKAGE,
) -> str:
    payload = routing_payload(
        repo,
        vision_mcp_server=vision_mcp_server,
        vision_mcp_package=vision_mcp_package,
    )
    supervisor = payload["paths"]["zcode_supervisor"]
    controller = payload["paths"]["zcodectl"]
    return f"""# ZCode Delegation

Use this repo-local contract when the user wants Codex to keep planning,
orchestration, audit, and final acceptance while ZCode handles implementation.

## Default Routing

- Codex owns planning, packet creation, audit, validation, and final acceptance.
- ZCode owns only bounded implementation inside this repo or an isolated worktree.
- Before implementation edits, run `auto-route` so this repo's
  `.codex/zcode-routing.json` decides whether to delegate to ZCode.
- Use ZCode for implementation tasks unless the task is read-only, trivial,
  high-risk plan-only, or the user says `no-zcode`.
- Do not delegate secrets, destructive Git operations, dependency installs, or final
  acceptance to ZCode.

## Normal Flow

1. Codex classifies the task through the routing contract:

```bash
python3 {supervisor} auto-route \\
  --workspace . \\
  --objective "<specific outcome>"
```

2. For implementation tasks, Codex writes a small plan, allowed-file set, and
   validation command, then delegates:

```bash
python3 {supervisor} auto-route \\
  --workspace . \\
  --objective "<specific outcome>" \\
  --allowed "<file>" \\
  --validation "<command>" \\
  --execute
```

The command creates the packet, calls `zcodectl run-packet`, and returns a
machine-readable result. If it returns `needs_codex_planning`, Codex should add
a tighter allowed-file set and validation command, not ask the user.

## Manual Packet Flow

If manual control is needed, Codex can create a packet directly:

```bash
python3 {supervisor} packet \\
  --workspace . \\
  --objective "<specific outcome>" \\
  --allowed "<file>" \\
  --validation "<command>" \\
  --mode "Auto Edit" \\
  --effort max \\
  --task-class root-cause \\
  --risk-budget low \\
  --out .codex/zcode/packets/<task>.json \\
  --prompt-out .codex/zcode/packets/<task>.prompt.txt
```

3. Codex runs ZCode:

Use `zcodectl run-packet` through this repository's controller:

```bash
node {controller} run-packet \\
  --packet .codex/zcode/packets/<task>.json \\
  --mode edit \\
  --max-attempts 2 \\
  --retry-delay-ms 60000 \\
  --usage-snapshot-source auto \\
  --out .codex/zcode/runs/<task>.zcode.json
```

4. Codex reviews the `supervisor_state`, changed files, validation result, and
   risk notes before accepting the work.

## Vision MCP

Vision-capable packets use `{vision_mcp_server}` through `.agents/mcp.json`.
The configured stdio command is `npx -y {vision_mcp_package}`. Do not write API
keys into repo files; `zcodectl run-packet` passes available local credentials
to the ZCode child process without printing secret values.

Check setup with:

```bash
node {controller} vision-preflight --workspace .
```

## Local Routing Config

See `.codex/zcode-routing.json` for machine-readable defaults.
"""


def agents_block() -> str:
    return f"""{AGENTS_BEGIN}
## ZCode Supervisor Routing

For implementation tasks in this repository, read `.codex/ZCODE_DELEGATION.md`.
Default split: Codex plans, runs `auto-route`, orchestrates, audits, validates,
and final-accepts; ZCode performs only bounded implementation through
`zcodectl run-packet`.
Before direct implementation edits, Codex should run:
`python3 <zcode-supervisor>/tools/zcode_supervisor/zcode_supervisor.py auto-route --workspace . --objective "<task>"`.
Do not delegate secrets, destructive operations, or final acceptance to ZCode.
{AGENTS_END}
"""


def ensure_repo_local_output(repo: Path, path: Path) -> None:
    repo = repo.resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise ValueError(f"output path escapes repo: {path}") from exc

    cursor = path
    while True:
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink():
                raise ValueError(f"output path uses symlink: {cursor.relative_to(repo)}")
            if not cursor.resolve().is_relative_to(repo):
                raise ValueError(f"output path resolves outside repo: {cursor.relative_to(repo)}")
        if cursor == repo:
            break
        cursor = cursor.parent


def read_repo_text(repo: Path, path: Path) -> str:
    ensure_repo_local_output(repo, path)
    return path.read_text(encoding="utf-8")


def write_repo_text(repo: Path, path: Path, text: str) -> None:
    ensure_repo_local_output(repo, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ensure_repo_local_output(repo, path)
    path.write_text(text, encoding="utf-8")


def write_text_if_allowed(repo: Path, path: Path, text: str, *, force: bool) -> str:
    ensure_repo_local_output(repo, path)
    if path.exists() and not force:
        return "exists"
    write_repo_text(repo, path, text)
    return "written"


def install_agents_block(repo: Path, *, force: bool) -> str:
    path = repo / AGENTS_FILE
    block = agents_block()
    ensure_repo_local_output(repo, path)
    if not path.exists():
        write_repo_text(repo, path, f"# AGENTS.md\n\n{block}")
        return "created"
    text = read_repo_text(repo, path)
    if AGENTS_BEGIN in text and AGENTS_END in text:
        if not force:
            return "already_present"
        start = text.index(AGENTS_BEGIN)
        end = text.index(AGENTS_END, start) + len(AGENTS_END)
        write_repo_text(repo, path, text[:start].rstrip() + "\n\n" + block + text[end:].lstrip())
        return "replaced"
    write_repo_text(repo, path, text.rstrip() + "\n\n" + block)
    return "appended"


def vision_mcp_server_payload(package: str) -> dict[str, Any]:
    return {
        "type": "stdio",
        "command": "npx",
        "args": ["-y", package],
        "enable": True,
    }


def as_record(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def mcp_servers_for_update(config: dict[str, Any]) -> dict[str, Any]:
    mcp = config.get("mcp")
    if isinstance(mcp, dict) and isinstance(mcp.get("servers"), dict):
        return mcp["servers"]
    if isinstance(config.get("mcpServers"), dict):
        return config["mcpServers"]
    config["mcpServers"] = {}
    return config["mcpServers"]


def install_vision_mcp(repo: Path, *, force: bool, server_name: str, package: str) -> str:
    path = repo / VISION_MCP_FILE
    server = vision_mcp_server_payload(package)
    ensure_repo_local_output(repo, path)
    if not path.exists():
        write_repo_text(
            repo,
            path,
            json.dumps({"mcpServers": {server_name: server}}, indent=2, sort_keys=True) + "\n",
        )
        return "written"

    config = as_record(json.loads(read_repo_text(repo, path)), label=str(VISION_MCP_FILE))
    servers = mcp_servers_for_update(config)
    if server_name in servers and not force:
        return "already_present"
    status = "replaced" if server_name in servers else "added"
    servers[server_name] = server
    write_repo_text(repo, path, json.dumps(config, indent=2, sort_keys=True) + "\n")
    return status


def install_repo(
    repo: Path,
    *,
    write_agents: bool,
    force: bool,
    vision_mcp: bool = True,
    vision_mcp_server: str = DEFAULT_VISION_MCP_SERVER,
    vision_mcp_package: str = DEFAULT_VISION_MCP_PACKAGE,
) -> InstallResult:
    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError(f"repo does not exist: {repo}")
    written: list[str] = []
    skipped: list[str] = []

    routing_status = write_text_if_allowed(
        repo,
        repo / ROUTING_FILE,
        json.dumps(
            routing_payload(
                repo,
                vision_mcp_server=vision_mcp_server,
                vision_mcp_package=vision_mcp_package,
            ),
            indent=2,
            sort_keys=True,
        ) + "\n",
        force=force,
    )
    (written if routing_status == "written" else skipped).append(str(ROUTING_FILE))

    doc_status = write_text_if_allowed(
        repo,
        repo / DELEGATION_FILE,
        delegation_doc(
            repo,
            vision_mcp_server=vision_mcp_server,
            vision_mcp_package=vision_mcp_package,
        ),
        force=force,
    )
    (written if doc_status == "written" else skipped).append(str(DELEGATION_FILE))

    vision_mcp_status = "not_requested"
    if vision_mcp:
        vision_mcp_status = install_vision_mcp(
            repo,
            force=force,
            server_name=vision_mcp_server,
            package=vision_mcp_package,
        )
        if vision_mcp_status in {"written", "added", "replaced"}:
            written.append(str(VISION_MCP_FILE))
        else:
            skipped.append(str(VISION_MCP_FILE))

    agents_status = "not_requested"
    if write_agents:
        agents_status = install_agents_block(repo, force=force)
        if agents_status in {"created", "appended", "replaced"}:
            written.append(str(AGENTS_FILE))
        else:
            skipped.append(str(AGENTS_FILE))

    return InstallResult(
        repo=repo,
        routing_file=repo / ROUTING_FILE,
        delegation_file=repo / DELEGATION_FILE,
        agents_file=repo / AGENTS_FILE,
        vision_mcp_file=repo / VISION_MCP_FILE,
        agents_status=agents_status,
        vision_mcp_status=vision_mcp_status,
        written=written,
        skipped=skipped,
    )


def install_repo_command(args: Any) -> int:
    result = install_repo(
        args.repo,
        write_agents=args.write_agents,
        force=args.force,
        vision_mcp=not args.skip_vision_mcp,
        vision_mcp_server=args.vision_mcp_server,
        vision_mcp_package=args.vision_mcp_package,
    )
    payload = {
        "ok": True,
        "repo": str(result.repo),
        "routing_file": str(result.routing_file),
        "delegation_file": str(result.delegation_file),
        "agents_file": str(result.agents_file),
        "vision_mcp_file": str(result.vision_mcp_file),
        "agents_status": result.agents_status,
        "vision_mcp_status": result.vision_mcp_status,
        "written": result.written,
        "skipped": result.skipped,
        "next_action": "Read .codex/ZCODE_DELEGATION.md and run auto-route before implementation edits; run vision-preflight before required image tasks.",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def install_repo_entrypoint(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install ZCode delegation defaults into a target repo.")
    parser.add_argument("repo", type=Path, help="Target repository path.")
    parser.add_argument("--no-write-agents", dest="write_agents", action="store_false", default=True)
    parser.add_argument("--skip-vision-mcp", action="store_true")
    parser.add_argument("--vision-mcp-server", default=DEFAULT_VISION_MCP_SERVER)
    parser.add_argument("--vision-mcp-package", default=DEFAULT_VISION_MCP_PACKAGE)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    return install_repo_command(args)


if __name__ == "__main__":
    raise SystemExit(install_repo_entrypoint(sys.argv[1:]))
