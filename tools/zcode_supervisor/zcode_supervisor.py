#!/usr/bin/env python3
"""Safety and quality gate for Codex-managed ZCode work."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .auto_route import add_auto_route_parser
    from .repo_setup import install_repo_command
except ImportError:  # pragma: no cover - direct script execution
    from auto_route import add_auto_route_parser
    from repo_setup import install_repo_command

VERSION = 1
SKIP_DIRS = {".git", "node_modules", "__pycache__", "dist", "build", "coverage"}
SECRET_PATH_NEEDLES = (".env", "id_rsa", "id_ed25519", ".ssh", "credential", "credentials")
TASK_CLASSES = (
    "small-fix",
    "long-horizon",
    "architecture",
    "root-cause",
    "production-gate",
    "mobile-debug",
    "research",
)
WORKSPACE_KINDS = ("regular", "worktree", "disposable", "fixture")
FULL_ACCESS_SAFE_WORKSPACE_KINDS = {"worktree", "disposable", "fixture"}
RISK_BUDGETS = ("low", "medium", "high")
DEFAULT_CONTEXT_POLICY = (
    "Use targeted reads and file references first. Do not paste or request the "
    "whole repository unless the task class requires project-level inventory."
)
SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[^'\"\s]{12,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
PROVIDER_OVERLOAD_PATTERN = re.compile(r"temporarily overloaded|try again later|overloaded_error", re.I)
MAX_HASH_BYTES = 1_000_000
MAX_COLOR_SAMPLE_BYTES = 50_000_000
MAX_COLOR_SAMPLE_DECOMPRESSED_BYTES = 50_000_000
DEFAULT_VISION_SERVICE = "zai-mcp-server"
IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
COLOR_SAMPLE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class Snapshot:
    workspace: Path
    files: dict[str, dict[str, Any]]
    skipped_secret_files: list[str]
    skipped_large_files: list[str]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def emit_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def fail(message: str) -> int:
    emit_json({"ok": False, "error": message})
    return 1


def inside_workspace(workspace: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(workspace.resolve())
        return True
    except ValueError:
        return False


def is_secret_path(path: Path) -> bool:
    lowered = str(path).lower()
    return any(needle in lowered for needle in SECRET_PATH_NEEDLES)


def normalize_rel_path(workspace: Path, raw: str) -> str:
    candidate = Path(raw)
    absolute = candidate if candidate.is_absolute() else workspace / candidate
    absolute = absolute.resolve()
    if not inside_workspace(workspace, absolute):
        raise ValueError(f"path escapes workspace: {raw}")
    rel = absolute.relative_to(workspace.resolve()).as_posix()
    if is_secret_path(Path(rel)):
        raise ValueError(f"secret-like path is not allowed: {raw}")
    return rel


def normalize_vision_image(workspace: Path, raw: str) -> str:
    rel = normalize_rel_path(workspace, raw)
    path = workspace / rel
    if not path.is_file():
        raise ValueError(f"vision image does not exist: {raw}")
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"vision image must be an image file: {raw}")
    return rel


def parse_color_sample(workspace: Path, raw: str) -> dict[str, Any]:
    if "=" not in raw or "@" not in raw:
        raise ValueError("vision color sample must use name=image.png@x,y")
    name, target = raw.split("=", 1)
    image_raw, coords = target.rsplit("@", 1)
    name = name.strip()
    if not COLOR_SAMPLE_NAME_PATTERN.match(name):
        raise ValueError(f"invalid vision color sample name: {name}")
    rel = normalize_vision_image(workspace, image_raw.strip())
    try:
        x_raw, y_raw = coords.split(",", 1)
        x = int(x_raw)
        y = int(y_raw)
    except ValueError as exc:
        raise ValueError(f"invalid vision color sample coordinates: {raw}") from exc
    if x < 0 or y < 0:
        raise ValueError(f"vision color sample coordinates must be non-negative: {raw}")
    rgba = read_png_pixel(workspace / rel, x, y)
    return {
        "name": name,
        "image": rel,
        "x": x,
        "y": y,
        "hex": f"#{rgba[0]:02X}{rgba[1]:02X}{rgba[2]:02X}",
        "rgba": list(rgba),
    }


def read_png_pixel(path: Path, x: int, y: int) -> tuple[int, int, int, int]:
    if path.stat().st_size > MAX_COLOR_SAMPLE_BYTES:
        raise ValueError(f"vision color sample image is too large: {path.name}")
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"vision color samples currently require PNG files: {path.name}")
    offset = 8
    width = height = bit_depth = color_type = interlace = None
    idat_parts: list[bytes] = []
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError(f"invalid PNG chunk header: {path.name}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise ValueError(f"truncated PNG chunk: {path.name}")
        chunk = data[offset + 8:offset + 8 + length]
        offset = chunk_end
        if kind == b"IHDR":
            if length != 13:
                raise ValueError(f"invalid PNG IHDR chunk: {path.name}")
            width, height, bit_depth, color_type, _compression, _filter, interlace = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            idat_parts.append(chunk)
        elif kind == b"IEND":
            break
    if None in {width, height, bit_depth, color_type, interlace} or not idat_parts:
        raise ValueError(f"invalid PNG data: {path.name}")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid PNG dimensions: {path.name}")
    if bit_depth != 8 or color_type not in {2, 6} or interlace != 0:
        raise ValueError("vision color samples support non-interlaced 8-bit RGB/RGBA PNG files only")
    if x >= width or y >= height:
        raise ValueError(f"vision color sample outside image bounds: {path.name}@{x},{y}")
    channels = 4 if color_type == 6 else 3
    row_size = width * channels
    expected_size = (row_size + 1) * height
    if expected_size > MAX_COLOR_SAMPLE_DECOMPRESSED_BYTES:
        raise ValueError(f"vision color sample image is too large after decompression: {path.name}")
    decompressor = zlib.decompressobj()
    try:
        raw = decompressor.decompress(b"".join(idat_parts), expected_size)
    except zlib.error as exc:
        raise ValueError(f"invalid PNG image data: {path.name}") from exc
    if decompressor.unconsumed_tail:
        raise ValueError(f"vision color sample image exceeds decompression limit: {path.name}")
    if not decompressor.eof:
        raise ValueError(f"truncated PNG image data: {path.name}")
    if len(raw) < expected_size:
        raise ValueError(f"truncated PNG image data: {path.name}")
    rows: list[bytearray] = []
    cursor = 0
    for _row_index in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor:cursor + row_size])
        cursor += row_size
        previous = rows[-1] if rows else bytearray(row_size)
        unfilter_png_row(row, previous, filter_type, channels)
        rows.append(row)
    index = x * channels
    row = rows[y]
    alpha = row[index + 3] if channels == 4 else 255
    return row[index], row[index + 1], row[index + 2], alpha


def unfilter_png_row(row: bytearray, previous: bytearray, filter_type: int, channels: int) -> None:
    if filter_type == 0:
        return
    for index, value in enumerate(row):
        left = row[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if filter_type == 1:
            row[index] = (value + left) & 0xFF
        elif filter_type == 2:
            row[index] = (value + up) & 0xFF
        elif filter_type == 3:
            row[index] = (value + ((left + up) // 2)) & 0xFF
        elif filter_type == 4:
            row[index] = (value + paeth(left, up, up_left)) & 0xFF
        else:
            raise ValueError(f"unsupported PNG filter type: {filter_type}")


def paeth(left: int, up: int, up_left: int) -> int:
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def approximate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return value


def validation_danger_reason(command: str) -> str | None:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return f"invalid validation command: {exc}"
    if not argv:
        return "empty validation command"
    executable = Path(argv[0]).name.lower()
    lowered = " ".join(argv).lower()
    if executable in {"sudo", "su"}:
        return f"unsafe validation command: {argv[0]}"
    if executable == "rm" and any(item.startswith("-") and "r" in item.lower() for item in argv[1:]):
        return "unsafe validation command: rm recursive delete"
    if executable == "git" and len(argv) > 1 and argv[1] in {"clean", "reset", "checkout", "restore"}:
        return f"unsafe validation command: git {argv[1]}"
    if executable == "chmod" and any("777" in item for item in argv[1:]):
        return "unsafe validation command: chmod 777"
    if executable in {"bash", "sh", "zsh"} and any(item in {"-c", "-lc"} for item in argv[1:]):
        destructive_shell = r"\brm\s+-[^\s]*r|\bgit\s+(clean|reset|checkout|restore)\b|\bchmod\s+777\b"
        if re.search(destructive_shell, lowered):
            return "unsafe validation shell command"
    return None


def first_regex_group(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def classify_provider_error(*, stdout: str = "", stderr: str = "", exit_code: int | None = None) -> dict[str, Any]:
    text = f"{stderr}\n{stdout}"
    provider_code = first_regex_group(
        text,
        (
            r"providerCode:\s*['\"]?(\d+)['\"]?",
            r'"providerCode"\s*:\s*"(\d+)"',
            r"\[(\d{3,})\]\[",
            r"\bcode:\s*['\"]?(\d{3,})['\"]?",
            r'"code"\s*:\s*"(\d{3,})"',
        ),
    )
    temporary = bool(PROVIDER_OVERLOAD_PATTERN.search(text)) or provider_code == "1305"
    exit_143 = exit_code == 143
    provider_error = bool(
        re.search(r"ProviderBusinessError|PROVIDER_BUSINESS_ERROR|isProviderBusinessError:\s*true", text)
        or temporary
        or provider_code == "1305"
        or exit_143
    )
    provider_message = first_regex_group(
        text,
        (
            r"providerMessage:\s*'([^']+)'",
            r'providerMessage:\s*"([^"]+)"',
            r'"providerMessage"\s*:\s*"([^"]+)"',
            r"ProviderBusinessError:\s*([^\n]+)",
        ),
    )
    if provider_message is None and exit_143:
        provider_message = "ZCode CLI exited with code 143"
    return {
        "provider_error": provider_error,
        "provider_code": provider_code,
        "provider_message": provider_message,
        "provider_id": first_regex_group(text, (r"providerId:\s*'([^']+)'", r'providerId:\s*"([^"]+)"', r'"providerId"\s*:\s*"([^"]+)"')),
        "provider_kind": first_regex_group(text, (r"providerKind:\s*'([^']+)'", r'providerKind:\s*"([^"]+)"', r'"providerKind"\s*:\s*"([^"]+)"')),
        "provider_error_temporary": temporary,
        "retryable_provider_error": provider_error and (temporary or exit_143),
    }


def classify_provider_run_state(provider: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    if not provider.get("provider_error"):
        return {"supervisor_state": "cli_error", "partial_artifacts_possible": False, "safe_to_retry_later": False}
    changed_count = audit.get("changed_count") if audit else None
    if changed_count == 0 and provider.get("retryable_provider_error"):
        return {"supervisor_state": "retryable_provider_error", "partial_artifacts_possible": False, "safe_to_retry_later": True}
    if isinstance(changed_count, int) and changed_count > 0 and audit and audit.get("ok") is True:
        return {"supervisor_state": "partial_success", "partial_artifacts_possible": True, "safe_to_retry_later": False}
    partial_possible = changed_count is None or not isinstance(changed_count, int) or changed_count > 0
    return {"supervisor_state": "unsafe_partial", "partial_artifacts_possible": partial_possible, "safe_to_retry_later": False}


def make_prompt(packet: dict[str, Any]) -> str:
    allowed = ", ".join(packet["allowed_files"]) or "NONE"
    forbidden = ", ".join(packet["forbidden_files"]) or "secrets, .env*, credentials, files outside workspace"
    max_changed = packet["max_changed_files"] or "not set"
    prefix = "/goal " if packet["goal"] else ""
    vision = packet.get("vision") if isinstance(packet.get("vision"), dict) else {}
    vision_block = ""
    if vision.get("required"):
        images = ", ".join(vision.get("image_files") or []) or "runtime screenshots or attached images"
        service = vision.get("service") or DEFAULT_VISION_SERVICE
        samples = vision.get("color_samples") or []
        sample_lines = ""
        if samples:
            rendered = "\n".join(
                f"- {sample['name']}: {sample['image']}@{sample['x']},{sample['y']} = {sample['hex']}"
                for sample in samples
            )
            sample_lines = (
                "Deterministic color samples, use these exact values instead of estimating sampled colors:\n"
                f"{rendered}\n"
            )
        vision_block = (
            "Vision/image policy:\n"
            "- GLM-5.2 is text-only; do not guess from image filenames or surrounding text.\n"
            f"- Use ZCode's built-in image service/MCP before relying on image details. Preferred service: {service}.\n"
            f"- Required image context: {images}.\n"
            f"{sample_lines}"
            "- If reporting colors as hex, normalize them as uppercase #RRGGBB unless the task says otherwise.\n"
            "- If image understanding is unavailable, stop and report vision_service_unavailable.\n\n"
        )
    return (
        f"{prefix}You are a ZCode worker under Codex audit.\n"
        f"Workspace: {packet['workspace']}\n"
        f"Workspace kind: {packet['workspace_kind']}\n"
        f"Objective: {packet['objective']}\n"
        f"GLM-5.2 task class: {packet['task_class']}\n"
        f"GLM-5.2 effort: {packet['effort']}\n"
        f"Risk budget: {packet['risk_budget']}\n"
        f"Max changed files: {max_changed}\n"
        f"Context policy: {packet['context_policy']}\n"
        f"Allowed files: {allowed}\n"
        f"Forbidden files: {forbidden}\n"
        f"Validation: {packet['validation']} (run by Codex supervisor after the ZCode turn)\n\n"
        f"{vision_block}"
        "Rules:\n"
        "- Read only the minimum files needed.\n"
        "- Use project-wide context only to preserve architecture, call chains, "
        "interfaces, or standards that affect the task.\n"
        "- For root-cause tasks, analyze the call chain and regression surface before editing.\n"
        "- For production-gate tasks, enforce style, dependency, test, and commit-boundary constraints.\n"
        "- If the task needs broader risk than the packet allows, stop and report.\n"
        "- Do not inspect or edit secrets, credentials, .env*, or files outside the workspace.\n"
        "- Do not edit tests unless they are explicitly in Allowed files.\n"
        "- Prefer the smallest fix that satisfies the objective.\n"
        "- Do not run the validation command yourself; Codex supervisor runs it after your response.\n\n"
        "Final report: changed files, validation result, remaining risks, accept/inspect/reject recommendation."
    )


def packet_command(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        return fail(f"workspace does not exist: {workspace}")
    try:
        allowed = [normalize_rel_path(workspace, item) for item in args.allowed]
        forbidden = [normalize_rel_path(workspace, item) for item in args.forbidden]
        vision_images = [normalize_vision_image(workspace, item) for item in args.vision_image]
        color_samples = [parse_color_sample(workspace, item) for item in args.vision_color_sample]
    except ValueError as exc:
        return fail(str(exc))
    if (
        args.mode == "Full Access"
        and args.workspace_kind not in FULL_ACCESS_SAFE_WORKSPACE_KINDS
        and not args.allow_regular_full_access
    ):
        return fail("Full Access requires --workspace-kind worktree, disposable, or fixture")
    danger = validation_danger_reason(args.validation)
    if danger:
        return fail(danger)
    vision_service = args.vision_service.strip() or DEFAULT_VISION_SERVICE
    sampled_images = [sample["image"] for sample in color_samples]
    image_files = sorted(set(vision_images + sampled_images))

    packet = {
        "version": VERSION,
        "created_at": utc_now(),
        "workspace": str(workspace),
        "workspace_kind": args.workspace_kind,
        "objective": args.objective.strip(),
        "allowed_files": sorted(set(allowed)),
        "forbidden_files": sorted(set(forbidden)),
        "validation": args.validation.strip(),
        "mode": args.mode,
        "effort": args.effort,
        "task_class": args.task_class,
        "risk_budget": args.risk_budget,
        "max_changed_files": args.max_changed_files,
        "context_policy": args.context_policy.strip(),
        "goal": args.goal,
        "vision": {
            "required": bool(args.vision_required or image_files or color_samples),
            "service": vision_service,
            "image_files": image_files,
            "color_samples": color_samples,
            "model_limit": "GLM-5.2 is text-only; use ZCode image service for visual understanding.",
        },
    }
    prompt = make_prompt(packet)
    packet["prompt"] = prompt
    packet["prompt_chars"] = len(prompt)
    packet["approx_prompt_tokens"] = approximate_tokens(prompt)
    if packet["prompt_chars"] > args.max_prompt_chars:
        return fail(f"prompt exceeds max chars: {packet['prompt_chars']} > {args.max_prompt_chars}")
    write_json(args.out, packet)
    if args.prompt_out:
        args.prompt_out.parent.mkdir(parents=True, exist_ok=True)
        args.prompt_out.write_text(prompt, encoding="utf-8")
    emit_json(packet)
    return 0


def should_skip(path: Path) -> bool:
    return any(part in SKIP_DIRS for part in path.parts)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_snapshot(workspace: Path) -> Snapshot:
    files: dict[str, dict[str, Any]] = {}
    skipped_secret_files: list[str] = []
    skipped_large_files: list[str] = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file() or should_skip(path.relative_to(workspace)):
            continue
        rel = path.relative_to(workspace).as_posix()
        if is_secret_path(Path(rel)):
            skipped_secret_files.append(rel)
            continue
        size = path.stat().st_size
        if size > MAX_HASH_BYTES:
            skipped_large_files.append(rel)
            continue
        files[rel] = {"sha256": hash_file(path), "size": size}
    return Snapshot(workspace, files, skipped_secret_files, skipped_large_files)


def snapshot_command(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    if not workspace.is_dir():
        return fail(f"workspace does not exist: {workspace}")
    snapshot = build_snapshot(workspace)
    payload = {
        "version": VERSION,
        "created_at": utc_now(),
        "workspace": str(snapshot.workspace),
        "files": snapshot.files,
        "skipped_secret_files": snapshot.skipped_secret_files,
        "skipped_large_files": snapshot.skipped_large_files,
    }
    write_json(args.out, payload)
    emit_json(payload)
    return 0


def compare_files(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[str]]:
    before_keys = set(before)
    after_keys = set(after)
    modified = sorted(rel for rel in before_keys & after_keys if before[rel]["sha256"] != after[rel]["sha256"])
    return {
        "added": sorted(after_keys - before_keys),
        "deleted": sorted(before_keys - after_keys),
        "modified": modified,
    }


def scan_changed_files(workspace: Path, changed: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for rel in changed:
        path = workspace / rel
        if not path.exists() or is_secret_path(Path(rel)) or path.stat().st_size > MAX_HASH_BYTES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"file": rel, "type": "secret_pattern"})
                break
    return findings


def run_validation(workspace: Path, command: str, timeout: int) -> dict[str, Any]:
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return {"ok": False, "returncode": 127, "error": f"invalid validation command: {exc}"}
    if not argv:
        return {"ok": False, "returncode": 127, "error": "empty validation command"}
    try:
        result = subprocess.run(
            argv,
            cwd=workspace,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {"ok": False, "returncode": 127, "error": f"command not found: {argv[0]}"}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": 124, "error": f"validation timed out after {timeout}s", "stdout": exc.stdout or "", "stderr": exc.stderr or ""}
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def audit_command(args: argparse.Namespace) -> int:
    workspace = args.workspace.resolve()
    packet = read_json(args.packet)
    before = read_json(args.snapshot)
    after_snapshot = build_snapshot(workspace)
    changes = compare_files(before["files"], after_snapshot.files)
    changed = sorted(changes["added"] + changes["deleted"] + changes["modified"])
    allowed = set(packet.get("allowed_files", []))
    forbidden = set(packet.get("forbidden_files", []))
    violations: list[dict[str, Any]] = []

    if str(workspace) != str(Path(packet.get("workspace", "")).resolve()):
        violations.append({"type": "packet_workspace_mismatch", "packet_workspace": packet.get("workspace")})
    if str(workspace) != str(Path(before.get("workspace", "")).resolve()):
        violations.append({"type": "snapshot_workspace_mismatch", "snapshot_workspace": before.get("workspace")})

    if not allowed:
        violations.append({"type": "missing_allowed_files", "message": "packet must declare allowed files"})
    outside_allowed = [rel for rel in changed if rel not in allowed]
    if outside_allowed:
        violations.append({"type": "outside_allowed_files", "files": outside_allowed})
    max_changed_files = packet.get("max_changed_files", 0)
    if (
        isinstance(max_changed_files, int)
        and max_changed_files > 0
        and len(changed) > max_changed_files
    ):
        violations.append(
            {"type": "max_changed_files_exceeded", "limit": max_changed_files, "actual": len(changed)}
        )
    forbidden_changed = [rel for rel in changed if rel in forbidden]
    if forbidden_changed:
        violations.append({"type": "forbidden_files_changed", "files": forbidden_changed})
    secret_findings = scan_changed_files(workspace, changed)
    if secret_findings:
        violations.append({"type": "secret_pattern", "findings": secret_findings})

    validation_command = packet.get("validation", "")
    danger = validation_danger_reason(validation_command)
    if danger:
        validation = {"ok": False, "returncode": 127, "error": danger}
        violations.append({"type": "unsafe_validation_command", "message": danger})
    else:
        validation = run_validation(workspace, validation_command, args.validation_timeout)
        if not validation["ok"]:
            violations.append({"type": "validation_failed", "returncode": validation.get("returncode")})

    payload = {
        "ok": not violations,
        "workspace": str(workspace),
        "packet": str(args.packet),
        "changed_files": changes,
        "changed_count": len(changed),
        "validation": validation,
        "violations": violations,
        "skipped_secret_files": after_snapshot.skipped_secret_files,
        "skipped_large_files": after_snapshot.skipped_large_files,
    }
    emit_json(payload)
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supervise Codex-managed ZCode work.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    packet = subparsers.add_parser("packet", help="Create a compact ZCode task packet.")
    packet.add_argument("--workspace", type=Path, required=True)
    packet.add_argument("--objective", required=True)
    packet.add_argument("--allowed", action="append", default=[])
    packet.add_argument("--forbidden", action="append", default=[])
    packet.add_argument("--validation", required=True)
    packet.add_argument("--mode", choices=("Plan", "Auto Edit", "Full Access", "Confirm Before Changes"), default="Auto Edit")
    packet.add_argument("--workspace-kind", choices=WORKSPACE_KINDS, default="regular")
    packet.add_argument("--allow-regular-full-access", action="store_true")
    packet.add_argument("--effort", choices=("high", "max"), default="max")
    packet.add_argument("--task-class", choices=TASK_CLASSES, default="small-fix")
    packet.add_argument("--risk-budget", choices=RISK_BUDGETS, default="low")
    packet.add_argument("--max-changed-files", type=non_negative_int, default=0)
    packet.add_argument("--context-policy", default=DEFAULT_CONTEXT_POLICY)
    packet.add_argument("--vision-image", action="append", default=[])
    packet.add_argument("--vision-color-sample", action="append", default=[])
    packet.add_argument("--vision-required", action="store_true")
    packet.add_argument("--vision-service", default=DEFAULT_VISION_SERVICE)
    packet.add_argument("--goal", action="store_true")
    packet.add_argument("--max-prompt-chars", type=int, default=5000)
    packet.add_argument("--out", type=Path, required=True)
    packet.add_argument("--prompt-out", type=Path)
    packet.set_defaults(func=packet_command)

    snapshot = subparsers.add_parser("snapshot", help="Snapshot a workspace before ZCode edits.")
    snapshot.add_argument("--workspace", type=Path, required=True)
    snapshot.add_argument("--out", type=Path, required=True)
    snapshot.set_defaults(func=snapshot_command)

    audit = subparsers.add_parser("audit", help="Audit ZCode edits against packet and snapshot.")
    audit.add_argument("--workspace", type=Path, required=True)
    audit.add_argument("--snapshot", type=Path, required=True)
    audit.add_argument("--packet", type=Path, required=True)
    audit.add_argument("--validation-timeout", type=int, default=60)
    audit.set_defaults(func=audit_command)

    add_auto_route_parser(subparsers)

    install = subparsers.add_parser("install-repo", help="Install repo-local Codex-to-ZCode routing hints.")
    install.add_argument("--repo", type=Path, required=True)
    install.add_argument("--write-agents", action="store_true")
    install.add_argument("--skip-vision-mcp", action="store_true")
    install.add_argument("--vision-mcp-server", default=DEFAULT_VISION_SERVICE)
    install.add_argument("--vision-mcp-package", default="@z_ai/mcp-server")
    install.add_argument("--force", action="store_true")
    install.set_defaults(func=install_repo_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
