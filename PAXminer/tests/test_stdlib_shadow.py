"""Directories inserted onto sys.path must not shadow the standard library."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_PATH_DIRS = (
    _ROOT,
    _ROOT / "database_management",
    _ROOT / "achievements",
    _ROOT / "kotter",
)


def test_handler_path_dirs_do_not_shadow_stdlib():
    names = getattr(sys, "stdlib_module_names", None)
    if names is None:
        pytest.skip("stdlib_module_names needs Python 3.10 or newer")
    clashes = []
    for folder in _PATH_DIRS:
        for path in folder.glob("*.py"):
            if path.stem in names:
                clashes.append(path.relative_to(_ROOT).as_posix())
    assert clashes == []
