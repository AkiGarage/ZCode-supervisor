"""Repo-local auto-routing for Codex-to-ZCode delegation."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROUTING_FILE = Path(".codex/zcode-routing.json")
DEFAULT_USAGE_SNAPSHOT_SOURCE = "auto"
IMPLEMENTATION_WORDS = (
    "add",
    "build",
    "change",
    "edit",
    "fix",
    "implement",
    "refactor",
    "test",
    "update",
    "write",
    "作って",
    "修正",
    "変更",
    "実装",
    "追加",
    "直して",
)
READ_ONLY_WORDS = (
    "audit",
    "explain",
    "inspect",
    "plan",
    "review",
    "summarize",
    "調べ",
    "説明",
    "レビュー",
    "計画",
)
TRIVIAL_WORDS = ("typo", "comment", "one-line", "one line", "誤字", "一行")
HIGH_RISK_WORDS = (
    ".env",
    "api key",
    "billing",
    "credential",
    "delete",
    "deploy",
    "destructive",
    "migration",
    "password",
    "payment",
    "production",
    "secret",
    "token",
    "trading",
    "remove data",
    "本番",
    "秘密",
    "認証",
    "決済",
    "削除",
    "移行",
)


def utc_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def routing_path(workspace: Path) -> Path:
    return workspace / ROUTING_FILE


def load_routing(workspace: Path) -> dict[str, Any] | None:
    path = routing_path(workspace)
    if not path.exists():
        return None
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"routing config must be a JSON object: {path}")
    return payload


def lowered_words(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = lowered_words(text)
    return any(needle in lowered for needle in needles)


def classify_task(objective: str, task_kind: str) -> dict[str, Any]:
    if contains_any(objective, HIGH_RISK_WORDS):
        return {"route": "ask_user", "reason": "high_risk_task"}
    if "no-zcode" in lowered_words(objective):
        return {"route": "codex_direct", "reason": "no_zcode_requested"}
    if task_kind == "read-only":
        return {"route": "codex_direct", "reason": "read_only_task"}
    if task_kind == "trivial":
        return {"route": "codex_direct", "reason": "trivial_task"}
    if task_kind in {"plan", "audit"}:
        return {"route": "codex_direct", "reason": f"{task_kind}_owned_by_codex"}
    if task_kind == "implementation":
        return {"route": "delegate_zcode", "reason": "implementation_task"}
    if contains_any(objective, TRIVIAL_WORDS) and len(objective) < 140:
        return {"route": "codex_direct", "reason": "trivial_task"}
    if contains_any(objective, IMPLEMENTATION_WORDS):
        return {"route": "delegate_zcode", "reason": "implementation_task"}
    if contains_any(objective, READ_ONLY_WORDS):
        return {"route": "codex_direct", "reason": "read_only_task"}
    return {"route": "codex_direct", "reason": "unclear_or_planning_task"}


def slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return slug[:48] or "task"


def route_defaults(config: dict[str, Any]) -> dict[str, Any]:
    defaults = config.get("defaults") if isinstance(config.get("defaults"), dict) else {}
    return {
        "effort": defaults.get("effort", "max"),
        "task_class": defaults.get("task_class", "root-cause"),
        "risk_budget": defaults.get("risk_budget", "low"),
        "workspace_kind": defaults.get("workspace_kind", "regular"),
        "usage_snapshot_source": defaults.get("usage_snapshot_source", DEFAULT_USAGE_SNAPSHOT_SOURCE),
        "max_attempts": int(defaults.get("max_attempts", 2)),
        "retry_delay_ms": int(defaults.get("retry_delay_ms", 60000)),
    }


def trusted_supervisor_path() -> str:
    return str(Path(__file__).resolve().with_name("zcode_supervisor.py"))


def trusted_controller_path(args: argparse.Namespace) -> str:
    if args.trusted_zcodectl:
        return str(args.trusted_zcodectl.resolve())
    return str(Path(__file__).resolve().parents[1] / "zcode_control" / "zcodectl.mjs")


def workspace_output_path(workspace: Path, raw: str) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("routing output path must be a non-empty string")
    raw_path = Path(raw)
    if raw_path.is_absolute():
        raise ValueError(f"routing output path must be relative: {raw}")
    visible = workspace / raw_path
    cursor = visible
    workspace_resolved = workspace.resolve()
    while True:
        if cursor.exists() or cursor.is_symlink():
            if cursor.is_symlink():
                raise ValueError(f"routing output path uses symlink: {cursor.relative_to(workspace)}")
        if cursor == workspace:
            break
        cursor = cursor.parent
    candidate = (workspace / raw_path).resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError(f"routing output path escapes workspace: {raw}") from exc
    return candidate


def packet_command(args: argparse.Namespace, config: dict[str, Any], packet_path: Path, prompt_path: Path) -> list[str]:
    defaults = route_defaults(config)
    command = [
        sys.executable,
        trusted_supervisor_path(),
        "packet",
        "--workspace",
        str(args.workspace),
        "--objective",
        args.objective,
        "--validation",
        args.validation,
        "--effort",
        args.effort or defaults["effort"],
        "--task-class",
        args.task_class or defaults["task_class"],
        "--risk-budget",
        args.risk_budget or defaults["risk_budget"],
        "--workspace-kind",
        args.workspace_kind or defaults["workspace_kind"],
        "--out",
        str(packet_path),
        "--prompt-out",
        str(prompt_path),
    ]
    for item in args.allowed:
        command.extend(["--allowed", item])
    for item in args.forbidden:
        command.extend(["--forbidden", item])
    if args.max_changed_files is not None:
        command.extend(["--max-changed-files", str(args.max_changed_files)])
    if args.goal:
        command.append("--goal")
    return command


def run_packet_command(args: argparse.Namespace, config: dict[str, Any], packet_path: Path, run_path: Path) -> list[str]:
    defaults = route_defaults(config)
    max_attempts = args.max_attempts if args.max_attempts is not None else defaults["max_attempts"]
    retry_delay_ms = args.retry_delay_ms if args.retry_delay_ms is not None else defaults["retry_delay_ms"]
    return [
        "node",
        trusted_controller_path(args),
        "run-packet",
        "--packet",
        str(packet_path),
        "--mode",
        args.run_mode,
        "--max-attempts",
        str(max_attempts),
        "--retry-delay-ms",
        str(retry_delay_ms),
        "--usage-snapshot-source",
        args.usage_snapshot_source or defaults["usage_snapshot_source"],
        "--out",
        str(run_path),
    ]


def run_json_command(command: list[str], cwd: Path) -> tuple[int, dict[str, Any] | None, str, str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    parsed = None
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = None
    return result.returncode, parsed, result.stdout, result.stderr


def build_paths(workspace: Path, config: dict[str, Any], objective: str) -> tuple[Path, Path, Path]:
    paths = config.get("paths") if isinstance(config.get("paths"), dict) else {}
    task_id = f"{utc_slug()}-{slugify(objective)}"
    packet_dir = workspace_output_path(workspace, paths.get("packets", ".codex/zcode/packets"))
    run_dir = workspace_output_path(workspace, paths.get("runs", ".codex/zcode/runs"))
    packet_path = packet_dir / f"{task_id}.json"
    prompt_path = packet_dir / f"{task_id}.prompt.txt"
    run_path = run_dir / f"{task_id}.zcode.json"
    return packet_path, prompt_path, run_path


def explain_decision(
    *,
    workspace: Path,
    config: dict[str, Any] | None,
    classification: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    route = classification["route"]
    needs_planning = route == "delegate_zcode" and (not args.allowed or not args.validation)
    return {
        "ok": True,
        "workspace": str(workspace),
        "routing_config": str(routing_path(workspace)) if config else None,
        "routing_mode": config.get("routing_mode") if config else None,
        "route": "needs_codex_planning" if needs_planning else route,
        "reason": "missing_allowed_or_validation" if needs_planning else classification["reason"],
        "codex_owns": (config or {}).get("policy", {}).get("codex_owns", []),
        "zcode_owns": (config or {}).get("policy", {}).get("zcode_owns", []),
        "next_action": next_action(route, classification["reason"], needs_planning),
    }


def next_action(route: str, reason: str, needs_planning: bool) -> str:
    if needs_planning:
        return "Codex should choose a tight allowed-file set and validation command, then rerun auto-route --execute."
    if route == "delegate_zcode":
        return "Run with --execute to create a packet and delegate bounded implementation to ZCode."
    if route == "ask_user":
        return "Pause for a concise plan because this matches an ask-before risk category."
    if route == "codex_direct":
        return f"Codex may handle this directly because {reason}."
    return "Inspect the routing decision before proceeding."


def auto_route_command(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        raise ValueError(f"workspace does not exist: {workspace}")
    config = load_routing(workspace)
    if config is None:
        emit_json({
            "ok": True,
            "workspace": str(workspace),
            "route": "codex_direct",
            "reason": "routing_config_missing",
            "next_action": "Run zcode-install-repo for this repo if ZCode delegation should be enabled.",
        })
        return 0

    classification = classify_task(args.objective, args.task_kind)
    decision = explain_decision(workspace=workspace, config=config, classification=classification, args=args)
    if decision["route"] != "delegate_zcode" or not args.execute:
        emit_json(decision)
        return 0

    packet_path, prompt_path, run_path = build_paths(workspace, config, args.objective)
    packet_cmd = packet_command(args, config, packet_path, prompt_path)
    packet_rc, packet_json, packet_stdout, packet_stderr = run_json_command(packet_cmd, workspace)
    if packet_rc != 0:
        emit_json({
            **decision,
            "ok": False,
            "route": "packet_failed",
            "packet_command": packet_cmd,
            "packet_stdout": packet_stdout[-4000:],
            "packet_stderr": packet_stderr[-4000:],
        })
        return 1

    run_cmd = run_packet_command(args, config, packet_path, run_path)
    run_rc, run_json, run_stdout, run_stderr = run_json_command(run_cmd, workspace)
    payload = {
        **decision,
        "executed": True,
        "packet": str(packet_path),
        "prompt": str(prompt_path),
        "run": str(run_path),
        "packet_command": packet_cmd,
        "run_command": run_cmd,
        "packet_result": packet_json,
        "run_result": run_json,
        "run_stdout_tail": run_stdout[-4000:] if run_json is None else "",
        "run_stderr_tail": run_stderr[-4000:],
        "ok": run_rc == 0,
    }
    write_json(run_path.with_suffix(".route.json"), payload)
    emit_json(payload)
    return 0 if run_rc == 0 else 1


def add_auto_route_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    route = subparsers.add_parser("auto-route", help="Route a task through the repo-local ZCode delegation contract.")
    route.add_argument("--workspace", type=Path, default=Path("."))
    route.add_argument("--objective", required=True)
    route.add_argument("--task-kind", choices=("auto", "implementation", "read-only", "plan", "audit", "trivial"), default="auto")
    route.add_argument("--allowed", action="append", default=[])
    route.add_argument("--forbidden", action="append", default=[])
    route.add_argument("--validation", default="")
    route.add_argument("--execute", action="store_true")
    route.add_argument("--run-mode", choices=("plan", "edit", "build", "yolo"), default="edit")
    route.add_argument("--effort", choices=("high", "max"))
    route.add_argument("--task-class", choices=("small-fix", "long-horizon", "architecture", "root-cause", "production-gate", "mobile-debug", "research"))
    route.add_argument("--risk-budget", choices=("low", "medium", "high"))
    route.add_argument("--workspace-kind", choices=("regular", "worktree", "disposable", "fixture"))
    route.add_argument("--max-changed-files", type=int)
    route.add_argument("--max-attempts", type=int)
    route.add_argument("--retry-delay-ms", type=int)
    route.add_argument("--usage-snapshot-source", choices=("auto", "zai-api", "codexbar", "none"))
    route.add_argument("--trusted-zcodectl", type=Path, help=argparse.SUPPRESS)
    route.add_argument("--goal", action="store_true")
    route.set_defaults(func=auto_route_command)


def auto_route_entrypoint(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Route a task through a repo-local ZCode delegation contract.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_auto_route_parser(subparsers)
    args = parser.parse_args(["auto-route", *(argv if argv is not None else sys.argv[1:])])
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        emit_json({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    raise SystemExit(auto_route_entrypoint())
