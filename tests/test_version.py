"""Version plumbing: the installed distribution version is authoritative, and
`engine_commit` carries the pinned etassia-rs commit (the C ABI has no
version symbol, so the pinned commit is the engine identity).
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

import pytest

import etassia

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_version_comes_from_the_installed_distribution() -> None:
    assert etassia.__version__ == importlib.metadata.version("etassia")


def test_version_matches_pyproject_in_a_source_checkout() -> None:
    if not PYPROJECT.is_file():
        pytest.skip("source checkout only (no pyproject.toml beside the package)")
    want = re.search(r'^version = "([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M).group(1)
    assert etassia.__version__ == want, f"installed {etassia.__version__}, pyproject {want}"


def test_engine_commit_is_a_full_sha() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", etassia.engine_commit()), etassia.engine_commit()


def test_engine_commit_is_the_packaged_pin() -> None:
    pin = Path(etassia.__file__).resolve().parent / "etassia-rs-version.txt"
    assert etassia.engine_commit() == pin.read_text(encoding="utf-8").strip()
