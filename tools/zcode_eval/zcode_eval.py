#!/usr/bin/env python3
"""Small harness for evaluating ZCode against Claude Code GLM workers.

The CLI deliberately starts with inspection and measurement. Direct ZCode GUI
automation should only be added after the local app exposes a stable control
surface such as a CLI, URL scheme, or documented IPC.
"""

from __future__ import annotations

import argparse
import json
import math
import plistlib
import statistics
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .duel_import import import_duel_results
except ImportError:
    from duel_import import import_duel_results

DEFAULT_APP_DIRS = (Path("/Applications"), Path.home() / "Applications")
DEFAULT_CLI_PATHS = (Path("/Applications/ZCode.app/Contents/Resources/glm/zcode.cjs"),)
DEFAULT_LEDGER = Path("artifacts/evals/zcode-vs-claude.jsonl")
SUPPORTED_TOOLS = ("zcode", "claude-code-glm52")
STAT_FIELDS = (
    "duration_seconds",
    "manual_interventions",
    "tokens_total",
    "tokens_before",
    "tokens_after",
    "tokens_used",
    "quota_units",
    "quota_percent_before",
    "quota_percent_after",
    "quota_percent_used",
    "files_changed",
    "lines_added",
    "lines_deleted",
    "tests_passed",
    "tests_failed",
)
PERCENT_FIELDS = {"quota_percent_before", "quota_percent_after", "quota_percent_used"}
PROVIDER_META_FIELDS = (
    "supervisor_state",
    "provider_code",
    "provider_message",
    "provider_request_id",
    "provider_error_line",
    "provider_id",
    "provider_kind",
    "attempt_count",
    "attempts",
    "retry_count",
    "retry_delays_ms",
    "no_usage_reason",
    "quota_percent_status",
    "quota_percent_unavailable_reason",
    "source_run_dir",
    "source_result_path",
    "preview",
    "task_kind",
)
PROVIDER_BOOL_FIELDS = (
    "provider_error",
    "retryable_provider_error",
    "partial_artifacts_possible",
    "safe_to_retry_later",
    "usage_available",
)


@dataclass(frozen=True)
class ZCodeAppInfo:
    path: str
    bundle_id: str | None
    version: str | None
    executable: str | None
    url_schemes: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_zcode_apps(search_dirs: tuple[Path, ...] = DEFAULT_APP_DIRS) -> list[Path]:
    apps: list[Path] = []
    for base in search_dirs:
        if not base.exists():
            continue
        for path in base.glob("*.app"):
            if "zcode" in path.name.lower():
                apps.append(path)
    return sorted(apps)


def read_app_info(app_path: Path) -> ZCodeAppInfo:
    info_plist = app_path / "Contents" / "Info.plist"
    data: dict[str, Any] = {}
    if info_plist.exists():
        with info_plist.open("rb") as handle:
            data = plistlib.load(handle)

    schemes: list[str] = []
    for entry in data.get("CFBundleURLTypes", []) or []:
        schemes.extend(entry.get("CFBundleURLSchemes", []) or [])

    return ZCodeAppInfo(
        path=str(app_path),
        bundle_id=data.get("CFBundleIdentifier"),
        version=data.get("CFBundleShortVersionString") or data.get("CFBundleVersion"),
        executable=data.get("CFBundleExecutable"),
        url_schemes=schemes,
    )


def infer_control_surface(apps: list[ZCodeAppInfo]) -> str:
    if not apps:
        return "install_required"
    if any(app.url_schemes for app in apps):
        return "url_scheme_candidate"
    return "gui_or_bundle_only"


def print_doctor(as_json: bool) -> int:
    apps = [read_app_info(path) for path in find_zcode_apps()]
    payload = {
        "status": "found" if apps else "not_found",
        "apps": [app.__dict__ for app in apps],
        "cli": find_cli_info(),
        "control_surface": infer_control_surface(apps),
    }
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ZCode app: {payload['status']}")
        for app in apps:
            print(f"- path: {app.path}")
            print(f"  bundle_id: {app.bundle_id or 'unknown'}")
            print(f"  version: {app.version or 'unknown'}")
            print(f"  executable: {app.executable or 'unknown'}")
            print(f"  url_schemes: {', '.join(app.url_schemes) or 'none'}")
        cli = payload["cli"]
        print(f"cli: {cli['status']}")
        if cli.get("path"):
            print(f"  path: {cli['path']}")
            print(f"  version: {cli.get('version') or 'unknown'}")
        print(f"control_surface: {payload['control_surface']}")
    return 0


def find_cli_info() -> dict[str, Any]:
    for path in DEFAULT_CLI_PATHS:
        if not path.exists():
            continue
        version = None
        try:
            result = subprocess.run(
                ["node", str(path), "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                version = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            version = None
        return {"status": "found", "path": str(path), "version": version}
    return {"status": "not_found"}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL: {exc}") from exc
    return records


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def bounded_percent(raw: str) -> float:
    value = non_negative_float(raw)
    if value > 100:
        raise argparse.ArgumentTypeError("percent must be between 0 and 100")
    return value


def non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def parse_retry_delays_ms(raw: str) -> list[int]:
    text = raw.strip()
    if not text:
        return []
    if text.startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise argparse.ArgumentTypeError("retry delays must be a JSON list or comma list")
        delays = value
    else:
        delays = [item.strip() for item in text.split(",") if item.strip()]
    parsed: list[int] = []
    for item in delays:
        delay = int(item)
        if delay < 0:
            raise argparse.ArgumentTypeError("retry delays must be non-negative")
        parsed.append(delay)
    return parsed


def stat_type(field: str):
    return bounded_percent if field in PERCENT_FIELDS else non_negative_float


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def normalize_codexbar_usage_snapshot(payload: Any) -> dict[str, Any]:
    rows = payload if isinstance(payload, list) else [payload]
    row = next((item for item in rows if isinstance(item, dict) and item.get("provider") == "zai"), None)
    row = row if row is not None else next((item for item in rows if isinstance(item, dict)), {})
    usage = row.get("usage", {}) if isinstance(row, dict) else {}
    windows: dict[str, dict[str, Any]] = {}
    quota_candidates: list[dict[str, Any]] = []
    if isinstance(usage, dict):
        for name in ("primary", "secondary", "tertiary"):
            window = usage.get(name)
            if not isinstance(window, dict):
                continue
            used_percent = window.get("usedPercent", window.get("used_percent"))
            normalized = {
                "name": name,
                "used_percent": used_percent if isinstance(used_percent, (int, float)) else None,
                "reset_description": window.get("resetDescription"),
                "resets_at": window.get("resetsAt"),
            }
            windows[name] = normalized
            if isinstance(normalized["used_percent"], (int, float)):
                quota_candidates.append(
                    {
                        "name": name,
                        "value": float(normalized["used_percent"]),
                        "line": f"{name}.usedPercent ({normalized['reset_description'] or 'quota window'})",
                    }
                )
    best = quota_candidates[0] if quota_candidates else None
    return {
        "source": "codexbar",
        "provider": row.get("provider") if isinstance(row, dict) else None,
        "windows": windows,
        "best": {
            "tokens_total": None,
            "quota_percent": best["value"] if best else None,
            "quota_percent_line": best["line"] if best else None,
        },
        "token_candidates": [],
        "quota_percent_candidates": quota_candidates,
    }


def normalize_zai_api_usage_snapshot(payload: Any) -> dict[str, Any]:
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    limits = data.get("limits", []) if isinstance(data, dict) else []
    windows: dict[str, dict[str, Any]] = {}
    quota_candidates: list[dict[str, Any]] = []
    raw_quota_candidates: list[dict[str, Any]] = []
    names_by_type = {"TOKENS_LIMIT": "primary", "TIME_LIMIT": "secondary"}
    iterable_limits = limits if isinstance(limits, list) else []
    for limit in iterable_limits:
        if not isinstance(limit, dict):
            continue
        limit_type = limit.get("type")
        name = names_by_type.get(limit_type)
        if name is None:
            continue
        raw_used_percent = finite_number(limit.get("percentage", limit.get("usedPercent", limit.get("used_percent"))))
        usage = finite_number(limit.get("usage"))
        remaining = finite_number(limit.get("remaining"))
        token_counts_available = usage is not None and remaining is not None
        authoritative = raw_used_percent is not None
        unavailable_reason = (
            "zai_limit_missing_percentage"
            if raw_used_percent is None
            else None
        )
        normalized = {
            "name": name,
            "type": limit_type,
            "used_percent": raw_used_percent,
            "raw_used_percent": raw_used_percent,
            "non_authoritative_used_percent": None,
            "authoritative": authoritative,
            "token_counts_available": token_counts_available,
            "quota_percent_unavailable_reason": unavailable_reason,
            "reset_description": "Tokens limit" if name == "primary" else "Time limit",
            "resets_at": limit.get("nextResetTime"),
            "usage": usage,
            "remaining": remaining,
        }
        windows[name] = normalized
        if name == "primary" and isinstance(normalized["used_percent"], (int, float)):
            quota_candidates.append(
                {
                    "name": name,
                    "value": float(normalized["used_percent"]),
                    "line": f"{limit_type}.percentage ({normalized['reset_description']})",
                }
            )
        if raw_used_percent is not None:
            raw_quota_candidates.append(
                {
                    "name": name,
                    "value": raw_used_percent,
                    "line": f"{limit_type}.percentage ({normalized['reset_description']})",
                    "authoritative": authoritative,
                    "unavailable_reason": unavailable_reason,
                }
            )
    best = quota_candidates[0] if quota_candidates else None
    raw_best = raw_quota_candidates[0] if raw_quota_candidates else None
    primary = windows.get("primary")
    return {
        "source": "zai-api",
        "provider": "zai",
        "plan": data.get("level") if isinstance(data, dict) else None,
        "windows": windows,
        "best": {
            "tokens_total": None,
            "quota_percent": best["value"] if best else None,
            "quota_percent_line": best["line"] if best else None,
            "raw_quota_percent": raw_best["value"] if raw_best else None,
            "quota_percent_authoritative": bool(best),
            "quota_percent_unavailable_reason": None
            if best
            else primary.get("quota_percent_unavailable_reason")
            if isinstance(primary, dict)
            else None,
        },
        "token_candidates": [],
        "quota_percent_candidates": quota_candidates,
        "quota_percent_raw_candidates": raw_quota_candidates,
    }


def unwrap_usage_snapshot(payload: Any) -> dict[str, Any]:
    if isinstance(payload, list):
        return normalize_codexbar_usage_snapshot(payload)
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("value"), dict):
        return payload["value"]
    if isinstance(payload.get("data"), dict) and isinstance(payload["data"].get("limits"), list):
        return normalize_zai_api_usage_snapshot(payload)
    if payload.get("source") == "codexbar" and isinstance(payload.get("windows"), dict):
        return payload
    if payload.get("source") == "zai-api" and isinstance(payload.get("windows"), dict):
        return payload
    if payload.get("provider") == "zai" and isinstance(payload.get("usage"), dict):
        return normalize_codexbar_usage_snapshot(payload)
    return payload


def load_usage_snapshot(path: Path) -> dict[str, Any]:
    return unwrap_usage_snapshot(read_json(path))


def best_usage_value(snapshot: dict[str, Any], key: str) -> float | None:
    best = snapshot.get("best")
    if isinstance(best, dict) and isinstance(best.get(key), (int, float)):
        return float(best[key])
    candidates_key = "token_candidates" if key == "tokens_total" else "quota_percent_candidates"
    candidates = snapshot.get(candidates_key, [])
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and isinstance(candidate.get("value"), (int, float)):
                return float(candidate["value"])
    return None


def snapshot_quota_unavailable_reason(snapshot: dict[str, Any]) -> str | None:
    best = snapshot.get("best")
    if isinstance(best, dict) and isinstance(best.get("quota_percent_unavailable_reason"), str):
        return best["quota_percent_unavailable_reason"]
    windows = snapshot.get("windows")
    if isinstance(windows, dict):
        primary = windows.get("primary")
        if isinstance(primary, dict) and isinstance(primary.get("quota_percent_unavailable_reason"), str):
            return primary["quota_percent_unavailable_reason"]
    if snapshot.get("ok") is False:
        reason = snapshot.get("error_type") or snapshot.get("reason") or snapshot.get("message")
        if isinstance(reason, str):
            return reason
    return None


def usage_snapshot_quota_unavailable_reason(args: argparse.Namespace) -> str:
    for path in (args.usage_after, args.usage_before):
        if path:
            reason = snapshot_quota_unavailable_reason(load_usage_snapshot(path))
            if reason:
                return reason
    return "quota_percent_unavailable"


def apply_usage_snapshot_defaults(args: argparse.Namespace, stats: dict[str, float | None]) -> None:
    if args.usage_before:
        before = load_usage_snapshot(args.usage_before)
        if stats["tokens_before"] is None:
            stats["tokens_before"] = best_usage_value(before, "tokens_total")
        stats["quota_percent_before"] = (
            stats["quota_percent_before"]
            if stats["quota_percent_before"] is not None
            else best_usage_value(before, "quota_percent")
        )
    if args.usage_after:
        after = load_usage_snapshot(args.usage_after)
        if stats["tokens_after"] is None:
            stats["tokens_after"] = best_usage_value(after, "tokens_total")
        stats["quota_percent_after"] = (
            stats["quota_percent_after"]
            if stats["quota_percent_after"] is not None
            else best_usage_value(after, "quota_percent")
        )


def derive_usage_stats(args: argparse.Namespace, stats: dict[str, float | None]) -> None:
    tokens_before = stats.get("tokens_before")
    tokens_after = stats.get("tokens_after")
    if stats.get("tokens_used") is None and tokens_before is not None and tokens_after is not None:
        if tokens_after >= tokens_before:
            stats["tokens_used"] = round(tokens_after - tokens_before, 4)

    quota_before = stats.get("quota_percent_before")
    quota_after = stats.get("quota_percent_after")
    if stats.get("quota_percent_used") is None and quota_before is not None and quota_after is not None:
        if args.quota_percent_direction == "remaining":
            delta = quota_before - quota_after
        else:
            delta = quota_after - quota_before
        if delta >= 0:
            stats["quota_percent_used"] = round(delta, 4)


def init_ledger(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(exist_ok=True)
    print(str(path))
    return 0


def append_result(args: argparse.Namespace) -> int:
    path = args.path
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": utc_now(),
        "run_id": args.run_id,
        "tool": args.tool,
        "task_id": args.task_id,
        "task_name": args.task_name,
        "status": args.status,
        "validation": args.validation,
        "notes": args.notes,
    }
    stats = {field: getattr(args, field) for field in STAT_FIELDS}
    apply_usage_snapshot_defaults(args, stats)
    derive_usage_stats(args, stats)
    if (
        args.usage_before
        or args.usage_after
        or stats.get("quota_percent_before") is not None
        or stats.get("quota_percent_after") is not None
    ):
        record["quota_percent_direction"] = args.quota_percent_direction
    quota_percent_status = args.quota_percent_status
    quota_percent_unavailable_reason = args.quota_percent_unavailable_reason
    if quota_percent_status is None:
        if stats.get("quota_percent_used") is not None:
            quota_percent_status = "measured"
        elif args.usage_before or args.usage_after:
            quota_percent_status = "unavailable"
    if quota_percent_status == "unavailable" and quota_percent_unavailable_reason is None:
        quota_percent_unavailable_reason = usage_snapshot_quota_unavailable_reason(args)
    if quota_percent_status is not None:
        record["quota_percent_status"] = quota_percent_status
    if quota_percent_unavailable_reason is not None:
        record["quota_percent_unavailable_reason"] = quota_percent_unavailable_reason
    if args.usage_available is False and args.no_usage_reason is None:
        record["no_usage_reason"] = "usage_marked_unavailable"
    for field in STAT_FIELDS:
        value = stats[field]
        if value is not None:
            record[field] = value
    for field in PROVIDER_META_FIELDS:
        value = getattr(args, field)
        if value is not None:
            record[field] = value
    for field in PROVIDER_BOOL_FIELDS:
        value = getattr(args, field)
        if value is not None:
            record[field] = value
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_tool: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_tool.setdefault(record.get("tool", "unknown"), []).append(record)

    return {
        "records": len(records),
        "tools": {
            tool: summarize_tool(tool_records)
            for tool, tool_records in sorted(by_tool.items())
        },
    }


def summarize_tool(records: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(1 for record in records if record.get("status") == "pass")
    result: dict[str, Any] = {
        "runs": len(records),
        "pass_rate": round(passed / len(records), 3),
        "provider_errors": sum(1 for record in records if record.get("provider_error") is True),
        "retryable_provider_errors": sum(1 for record in records if record.get("safe_to_retry_later") is True),
        "partial_successes": sum(1 for record in records if record.get("supervisor_state") == "partial_success"),
    }
    for field in STAT_FIELDS:
        values = [
            record[field]
            for record in records
            if isinstance(record.get(field), (int, float))
        ]
        if values:
            result[f"avg_{field}"] = round(statistics.fmean(values), 2)
            result[f"total_{field}"] = round(sum(values), 2)
    return result


def summarize(path: Path) -> int:
    records = load_records(path)
    if not records:
        print("No records.")
        return 0
    print(json.dumps(build_summary(records), indent=2, sort_keys=True))
    return 0


def show_log(path: Path, limit: int, as_json: bool) -> int:
    records = load_records(path)
    selected = records[-limit:] if limit else records
    if as_json:
        print(json.dumps(selected, indent=2, sort_keys=True))
        return 0
    for record in selected:
        tokens = record.get("tokens_used", record.get("tokens_total", "unknown"))
        quota = record.get("quota_percent_used", "unknown")
        print(
            f"{record.get('recorded_at', 'unknown')} "
            f"{record.get('tool', 'unknown')} "
            f"{record.get('task_id', 'unknown')} "
            f"status={record.get('status', 'unknown')} "
            f"tokens_used={tokens} quota_percent_used={quota}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate ZCode vs Claude Code GLM workers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Inspect whether ZCode.app is installed.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable app info.")
    doctor.set_defaults(func=lambda args: print_doctor(args.json))

    init = subparsers.add_parser("init-ledger", help="Create the JSONL evaluation ledger.")
    init.add_argument("--path", type=Path, default=DEFAULT_LEDGER)
    init.set_defaults(func=lambda args: init_ledger(args.path))

    append = subparsers.add_parser("append-result", help="Append one benchmark result.")
    append.add_argument("--path", type=Path, default=DEFAULT_LEDGER)
    append.add_argument("--run-id", required=True)
    append.add_argument("--tool", choices=SUPPORTED_TOOLS, required=True)
    append.add_argument("--task-id", required=True)
    append.add_argument("--task-name", required=True)
    append.add_argument("--status", choices=("pass", "fail", "partial", "blocked"), required=True)
    append.add_argument("--validation", default="")
    append.add_argument("--notes", default="")
    append.add_argument(
        "--supervisor-state",
        choices=("success", "partial_success", "retryable_provider_error", "unsafe_partial", "cli_error"),
    )
    append.add_argument("--provider-code")
    append.add_argument("--provider-message")
    append.add_argument("--provider-request-id")
    append.add_argument("--provider-error-line")
    append.add_argument("--provider-id")
    append.add_argument("--provider-kind")
    append.add_argument("--attempt-count", type=non_negative_int)
    append.add_argument("--attempts", type=non_negative_int)
    append.add_argument("--retry-count", type=non_negative_int)
    append.add_argument("--retry-delays-ms", type=parse_retry_delays_ms)
    append.add_argument("--no-usage-reason")
    append.add_argument("--quota-percent-status", choices=("measured", "estimated", "unavailable"))
    append.add_argument("--quota-percent-unavailable-reason")
    append.add_argument("--source-run-dir")
    append.add_argument("--source-result-path")
    append.add_argument("--preview")
    append.add_argument("--task-kind")
    for field in PROVIDER_BOOL_FIELDS:
        append.add_argument(f"--{field.replace('_', '-')}", action=argparse.BooleanOptionalAction, default=None)
    append.add_argument("--usage-before", type=Path)
    append.add_argument("--usage-after", type=Path)
    append.add_argument(
        "--quota-percent-direction",
        choices=("remaining", "used"),
        default="remaining",
        help="How to derive quota-percent-used from before/after snapshots.",
    )
    for field in STAT_FIELDS:
        append.add_argument(f"--{field.replace('_', '-')}", type=stat_type(field))
    append.set_defaults(func=append_result)

    import_duel = subparsers.add_parser("import-duel-results", help="Append rows from an external supervisor duel results.json.")
    import_duel.add_argument("--source", type=Path, required=True)
    import_duel.add_argument("--path", type=Path, default=DEFAULT_LEDGER)
    import_duel.add_argument("--tool", choices=("zcode", "claude-code-glm52", "all"), default="zcode")
    import_duel.add_argument("--allow-duplicates", action="store_true")
    import_duel.set_defaults(func=import_duel_results)

    report = subparsers.add_parser("summarize", help="Summarize recorded benchmark results.")
    report.add_argument("--path", type=Path, default=DEFAULT_LEDGER)
    report.set_defaults(func=lambda args: summarize(args.path))

    show = subparsers.add_parser("show-log", help="Show recent JSONL result records.")
    show.add_argument("--path", type=Path, default=DEFAULT_LEDGER)
    show.add_argument("--limit", type=int, default=10)
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=lambda args: show_log(args.path, args.limit, args.json))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
