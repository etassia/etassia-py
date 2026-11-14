"""Shared fixtures: the engine and the golden corpus, or a clean skip."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

from etassia import _ffi

REPO = Path(__file__).resolve().parents[1]
CORPUS_DIR = Path(os.environ.get("ETASSIA_CORPUS_DIR", "") or REPO / "etassia-rs" / "golden")


@pytest.fixture(scope="session")
def engine() -> ctypes.CDLL:
    """The default engine, loaded once; skips the test when nothing is loadable."""
    try:
        return _ffi._load_library()
    except _ffi.EtassiaError as error:
        pytest.skip(f"no etassia cdylib available: {error}")


@pytest.fixture(scope="session")
def real_library_path() -> str:
    """One existing cdylib path for explicit-path tests; skips when none exists."""
    env = os.environ.get("ETASSIA_CDYLIB")
    if env and Path(env).exists():
        return env
    libdir = Path(_ffi.__file__).resolve().parent / "lib"
    for name in _ffi._LIB_NAMES:
        candidate = libdir / name
        if candidate.exists():
            return str(candidate)
    pytest.skip("no real etassia cdylib available (set ETASSIA_CDYLIB or vendor one)")
