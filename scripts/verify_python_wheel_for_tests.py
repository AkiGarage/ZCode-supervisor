"""Importable test shim for scripts/verify-python-wheel."""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path


SCRIPT = Path(__file__).with_name("verify-python-wheel")
LOADER = SourceFileLoader("verify_python_wheel", str(SCRIPT))
SPEC = importlib.util.spec_from_loader("verify_python_wheel", LOADER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load verify-python-wheel")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

REQUIRED_ENTRY_POINTS = MODULE.REQUIRED_ENTRY_POINTS
main = MODULE.main
