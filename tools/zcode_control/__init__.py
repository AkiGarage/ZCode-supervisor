"""Python entrypoint wrapper for the bundled Node controller."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    controller = Path(__file__).resolve().with_name("zcodectl.mjs")
    try:
        return subprocess.call(["node", str(controller), *(argv if argv is not None else sys.argv[1:])])
    except FileNotFoundError:
        print("zcodectl requires Node.js on PATH. Install Node.js and retry.", file=sys.stderr)
        return 127
