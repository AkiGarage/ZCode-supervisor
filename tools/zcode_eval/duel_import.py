#!/usr/bin/env python3
"""Import external supervisor duel rows into the local ZCode eval ledger."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SUPPORTED_TOOLS = ("zcode", "claude-code-glm52")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def first_match(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match and match.group(1):
            return match.group(1)
    return None


def classify_provider_error_text(*, stdout: str = "", stderr: str = "", exit_code: Any = None) -> dict[str, Any]:
    text = f"{stderr}\n{stdout}"
    try:
        exit_code_number = int(exit_code)
    except (TypeError, ValueError):
        exit_code_number = None
    exit_143 = exit_code_number == 143
    provider_code = first_match(
        text,
        [
            r"providerCode:\s*['\"]?(\d+)['\"]?",
            r'"providerCode"\s*:\s*"(\d+)"',
            r"\[(\d{3,})\]\[",
            r"\bcode:\s*['\"]?(\d{3,})['\"]?",
            r'"code"\s*:\s*"(\d{3,})"',
        ],
    )
    temporary = bool(re.search(r"temporarily overloaded|try again later|overloaded_error", text, re.I)) or provider_code == "1305"
    provider_business = bool(
        re.search(r"ProviderBusinessError|PROVIDER_BUSINESS_ERROR|isProviderBusinessError:\s*true", text, re.I)
    )
    provider_error = provider_business or temporary or provider_code == "1305" or exit_143
    provider_line = next(
        (line for line in text.splitlines() if re.search(r"ProviderBusinessError|PROVIDER_BUSINESS_ERROR", line, re.I)),
        None,
    )
    provider_message = first_match(
        text,
        [
            r"providerMessage:\s*'([^']+)'",
            r'providerMessage:\s*"([^"]+)"',
            r'"providerMessage"\s*:\s*"([^"]+)"',
            r"ProviderBusinessError:\s*([^\n]+)",
        ],
    )
    return {
        "provider_error": provider_error,
        "provider_code": provider_code,
        "provider_message": provider_message or ("ZCode CLI exited with code 143" if exit_143 else None),
        "provider_request_id": first_match(
            text,
            [
                r"providerRequestId:\s*'([^']+)'",
                r'providerRequestId:\s*"([^"]+)"',
                r'"providerRequestId"\s*:\s*"([^"]+)"',
                r"request_id:\s*'([^']+)'",
                r'"request_id"\s*:\s*"([^"]+)"',
            ],
        ),
        "provider_error_line": provider_line,
        "provider_id": first_match(
            text,
            [r"providerId:\s*'([^']+)'", r'providerId:\s*"([^"]+)"', r'"providerId"\s*:\s*"([^"]+)"'],
        ),
        "provider_kind": first_match(
            text,
            [r"providerKind:\s*'([^']+)'", r'providerKind:\s*"([^"]+)"', r'"providerKind"\s*:\s*"([^"]+)"'],
        ),
        "retryable_provider_error": provider_error and (temporary or exit_143),
    }


def read_json_optional(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else {}


def bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def row_changed_count(row: dict[str, Any]) -> int | None:
    audit = row.get("audit")
    if isinstance(audit, dict) and isinstance(audit.get("changed_count"), int):
        return audit["changed_count"]
    changed_files = row.get("changed_files")
    if isinstance(changed_files, list):
        return len(changed_files)
    return None


def classify_duel_supervisor_state(row: dict[str, Any], provider: dict[str, Any]) -> dict[str, Any]:
    if row.get("run_ok") is True:
        return {"supervisor_state": "success", "partial_artifacts_possible": False, "safe_to_retry_later": False}
    if not provider.get("provider_error"):
        return {"supervisor_state": "cli_error", "partial_artifacts_possible": False, "safe_to_retry_later": False}
    changed_count = row_changed_count(row)
    audit = row.get("audit")
    audit_ok = bool_or_none(audit.get("ok")) if isinstance(audit, dict) else None
    if changed_count == 0 and provider.get("retryable_provider_error"):
        return {"supervisor_state": "retryable_provider_error", "partial_artifacts_possible": False, "safe_to_retry_later": True}
    if changed_count is not None and changed_count > 0 and audit_ok is True:
        return {"supervisor_state": "partial_success", "partial_artifacts_possible": True, "safe_to_retry_later": False}
    return {
        "supervisor_state": "unsafe_partial",
        "partial_artifacts_possible": changed_count is None or changed_count > 0,
        "safe_to_retry_later": False,
    }


def validation_summary(row: dict[str, Any]) -> str:
    validation = row.get("validation")
    if not isinstance(validation, dict):
        return ""
    status = "pass" if validation.get("ok") is True or row.get("validation_ok") is True else "fail"
    returncode = validation.get("returncode")
    return f"{status}; returncode={returncode}" if returncode is not None else status


def add_numeric(record: dict[str, Any], key: str, value: Any) -> None:
    number = finite_number(value)
    if number is not None:
        record[key] = number


def duel_tool_name(raw_tool: Any) -> str | None:
    if raw_tool == "zcode":
        return "zcode"
    if raw_tool == "glm":
        return "claude-code-glm52"
    if raw_tool in SUPPORTED_TOOLS:
        return raw_tool
    return None


def build_duel_record(row: dict[str, Any], *, source: Path, run_dir: Path) -> dict[str, Any] | None:
    tool = duel_tool_name(row.get("tool"))
    task_id = row.get("task_id")
    if tool is None or not isinstance(task_id, str):
        return None
    raw_tool = row.get("tool")
    result_path = run_dir / "_control" / str(raw_tool) / task_id / f"{raw_tool}-result.json"
    if raw_tool == "zcode":
        result_path = run_dir / "_control" / "zcode" / task_id / "zcode-result.json"
    result_json = read_json_optional(result_path)
    exit_code = result_json.get("exit_code")
    error_exit = row.get("run_ok") is False or result_json.get("ok") is False or (
        isinstance(exit_code, int) and exit_code != 0
    )
    provider = classify_provider_error_text(
        stdout=str(result_json.get("stdout") or ""),
        stderr=str(result_json.get("stderr") or ""),
        exit_code=exit_code,
    )
    if not error_exit:
        provider = {**provider, "provider_error": False, "retryable_provider_error": False}
    state = classify_duel_supervisor_state(row, provider)
    status = "partial" if state["supervisor_state"] == "partial_success" else "pass" if row.get("run_ok") is True else "fail"
    usage_available = any(
        finite_number(row.get(field)) is not None
        for field in ("tokens_total", "input_tokens", "output_tokens", "cache_read_tokens")
    )
    record: dict[str, Any] = {
        "recorded_at": utc_now(),
        "run_id": f"duel-{run_dir.name}-{tool}-{task_id}",
        "tool": tool,
        "task_id": task_id,
        "task_name": task_id.replace("_", " "),
        "task_kind": row.get("kind"),
        "status": status,
        "validation": validation_summary(row),
        "validation_ok": bool_or_none(row.get("validation_ok")),
        "scope_ok": bool_or_none(row.get("scope_ok")),
        "run_ok": bool_or_none(row.get("run_ok")),
        "output_files_ok": bool_or_none(row.get("output_files_ok")),
        "quality_score": finite_number(row.get("quality_score")),
        "preview": row.get("preview"),
        "source_run_dir": str(run_dir),
        "source_result_path": str(result_path) if result_path.exists() else None,
        "notes": f"Imported from external duel result {source}",
        "supervisor_state": state["supervisor_state"],
        "partial_artifacts_possible": state["partial_artifacts_possible"],
        "safe_to_retry_later": state["safe_to_retry_later"],
        "provider_error": bool(provider.get("provider_error")),
        "retryable_provider_error": bool(provider.get("retryable_provider_error")),
        "usage_available": usage_available,
        "attempt_count": 1,
        "attempts": 1,
        "retry_count": 0,
        "retry_delays_ms": [],
        "quota_percent_status": "unavailable",
        "quota_percent_unavailable_reason": "historical_duel_missing_authoritative_quota_snapshot",
    }
    if not usage_available:
        record["no_usage_reason"] = (
            "provider_error_without_zcode_cli_usage"
            if provider.get("provider_error")
            else "historical_duel_missing_usage_json"
        )
    for key in ("provider_code", "provider_message", "provider_request_id", "provider_error_line", "provider_id", "provider_kind"):
        if provider.get(key) is not None:
            record[key] = provider[key]
    wall_ms = finite_number(row.get("wall_ms"))
    add_numeric(record, "duration_seconds", wall_ms / 1000 if wall_ms is not None else None)
    for source_key, dest_key in (
        ("tokens_total", "tokens_total"),
        ("input_tokens", "input_tokens"),
        ("output_tokens", "output_tokens"),
        ("cache_read_tokens", "cache_read_tokens"),
        ("lines_added", "lines_added"),
        ("lines_deleted", "lines_deleted"),
    ):
        add_numeric(record, dest_key, row.get(source_key))
    changed_count = row_changed_count(row)
    if changed_count is not None:
        record["files_changed"] = float(changed_count)
    return {key: value for key, value in record.items() if value is not None}


def resolve_run_dir(raw_run_dir: Any, source: Path) -> Path:
    if not isinstance(raw_run_dir, str) or not raw_run_dir.strip():
        return source.parent
    raw_path = Path(raw_run_dir)
    if raw_path.is_absolute():
        return raw_path
    if source.parent.name == raw_path.name and (source.parent / "_control").exists():
        return source.parent
    for ancestor in source.parents:
        candidate = ancestor / raw_path
        if (candidate / "_control").exists() or (candidate / "results.json").exists():
            return candidate
    return source.parent


def import_duel_results(args: Any) -> int:
    payload = read_json(args.source)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"{args.source}: expected a JSON object with rows[]")
    run_dir = resolve_run_dir(payload.get("run_dir"), args.source)
    existing_run_ids = {record.get("run_id") for record in load_records(args.path)}
    imported = 0
    skipped = 0
    args.path.parent.mkdir(parents=True, exist_ok=True)
    with args.path.open("a", encoding="utf-8") as handle:
        for row in rows:
            if not isinstance(row, dict):
                continue
            record = build_duel_record(row, source=args.source, run_dir=run_dir)
            if record is None:
                continue
            if args.tool != "all" and record["tool"] != args.tool:
                continue
            if not args.allow_duplicates and record["run_id"] in existing_run_ids:
                skipped += 1
                continue
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            existing_run_ids.add(record["run_id"])
            imported += 1
    print(json.dumps({"imported": imported, "path": str(args.path), "skipped": skipped}, indent=2, sort_keys=True))
    return 0
