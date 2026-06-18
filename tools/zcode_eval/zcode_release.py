#!/usr/bin/env python3
"""Check official ZCode releases against this supervisor baseline."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.zcode_eval.zcode_eval import find_zcode_apps, read_app_info

CHANGELOG_URL = "https://zcode.z.ai/en/changelog"
VERSION_LINE = re.compile(r"^(?P<version>\d+\.\d+\.\d+)\s+Released\s+(?P<date>.+)$")
BARE_VERSION_LINE = re.compile(r"^(?P<version>\d+\.\d+\.\d+)$")
RELEASED_LINE = re.compile(r"^Released\s+(?P<date>.+)$")
SKIP_NOTE_LINES = {"Download", "New Features", "Bug Fixes"}


@dataclass(frozen=True)
class Release:
    version: str
    released: str
    notes: list[str]
    source_url: str


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(unescape(text))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def version_tuple(version: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in version.split("."))  # type: ignore[return-value]


def text_from_html(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return "\n".join(parser.parts)


def normalize_changelog_text(raw: str) -> str:
    if "<" in raw and ">" in raw:
        return text_from_html(raw)
    return raw


def fetch_text(url: str, timeout: int) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ZCode-supervisor release monitor"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return text_from_html(response.read().decode("utf-8", errors="replace"))


def parse_releases(text: str, source_url: str = CHANGELOG_URL) -> list[Release]:
    lines = [line.strip() for line in normalize_changelog_text(text).splitlines() if line.strip()]
    version_rows: list[tuple[int, int, str, str]] = []
    for index, line in enumerate(lines):
        match = VERSION_LINE.match(line)
        if match:
            version_rows.append((index, index + 1, match.group("version"), match.group("date")))
            continue
        bare = BARE_VERSION_LINE.match(line)
        if bare and index + 1 < len(lines):
            released = RELEASED_LINE.match(lines[index + 1])
            if released:
                version_rows.append((index, index + 2, bare.group("version"), released.group("date")))
    releases: list[Release] = []
    for row_index, (line_index, notes_start, version, released) in enumerate(version_rows):
        next_index = version_rows[row_index + 1][0] if row_index + 1 < len(version_rows) else len(lines)
        section = lines[notes_start:next_index]
        notes = clean_notes(section, version)
        releases.append(Release(version=version, released=released, notes=notes, source_url=source_url))
    return releases


def clean_notes(section: list[str], version: str) -> list[str]:
    notes: list[str] = []
    for line in section:
        if line in SKIP_NOTE_LINES:
            continue
        if line == f"Release v{version}" or line == f"ZCode {version} Update":
            continue
        if line.startswith("##"):
            continue
        notes.append(line)
    return notes[:40]


def latest_release(text: str, source_url: str) -> Release:
    releases = parse_releases(text, source_url)
    if not releases:
        raise ValueError("no ZCode release rows found in changelog")
    return max(releases, key=lambda release: version_tuple(release.version))


def load_baseline(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def local_apps() -> list[dict[str, Any]]:
    return [read_app_info(path).__dict__ for path in find_zcode_apps()]


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    text = Path(args.html_file).read_text(encoding="utf-8") if args.html_file else fetch_text(args.url, args.timeout)
    release = latest_release(text, args.url)
    baseline = load_baseline(args.baseline)
    baseline_version = args.known_version or baseline.get("version")
    update_available = bool(baseline_version and version_tuple(release.version) > version_tuple(baseline_version))
    return {
        "checked_at": utc_now(),
        "source_url": args.url,
        "baseline_version": baseline_version,
        "latest": release.__dict__,
        "update_available": update_available,
        "installed_apps": local_apps() if args.include_installed else [],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown(path: Path, payload: dict[str, Any]) -> None:
    latest = payload["latest"]
    lines = [
        f"# ZCode Release Check: {latest['version']}",
        "",
        f"- checked_at: {payload['checked_at']}",
        f"- baseline_version: {payload.get('baseline_version') or 'unknown'}",
        f"- update_available: {payload['update_available']}",
        f"- source: {payload['source_url']}",
        "",
        "## Release Notes",
        "",
    ]
    lines.extend(f"- {note}" for note in latest.get("notes", []))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_github_output(path: Path, payload: dict[str, Any]) -> None:
    latest = payload["latest"]
    lines = [
        f"latest_version={latest['version']}",
        f"baseline_version={payload.get('baseline_version') or ''}",
        f"update_available={str(payload['update_available']).lower()}",
        f"release_url={payload['source_url']}",
        f"issue_title=ZCode update detected: v{latest['version']}",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def check_command(args: argparse.Namespace) -> int:
    try:
        payload = build_payload(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    if args.json_out:
        write_json(args.json_out, payload)
    if args.markdown_out:
        write_markdown(args.markdown_out, payload)
    if args.github_output:
        append_github_output(args.github_output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check official ZCode release updates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check = subparsers.add_parser("check", help="Compare latest official ZCode release to a baseline.")
    check.add_argument("--url", default=CHANGELOG_URL)
    check.add_argument("--baseline", type=Path)
    check.add_argument("--known-version")
    check.add_argument("--html-file", type=Path, help="Use a local changelog HTML/text fixture.")
    check.add_argument("--timeout", type=int, default=15)
    check.add_argument("--include-installed", action="store_true")
    check.add_argument("--json-out", type=Path)
    check.add_argument("--markdown-out", type=Path)
    check.add_argument("--github-output", type=Path)
    check.set_defaults(func=check_command)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
