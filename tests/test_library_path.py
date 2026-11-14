"""Explicit native libraries: exclusive paths, resolution order, and context
isolation.

The lookup order is: an explicit `library_path` argument (EXCLUSIVE — no
fallback), then the `ETASSIA_CDYLIB` environment variable, then the packaged
library, then the bare system library names.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from etassia import EtassiaError, NativeContext, Unported, detect, render
from etassia import _ffi

MISSING = "/nonexistent/etassia-py-tests/libetassia_ffi"
LIB_DIR = Path(_ffi.__file__).resolve().parent / "lib"
PACKAGED = [str(LIB_DIR / name) for name in _ffi._LIB_NAMES]


def test_explicit_path_is_the_only_candidate() -> None:
    assert _ffi._candidate_paths(MISSING) == [MISSING]


def test_resolution_order_env_then_packaged_then_system(monkeypatch) -> None:
    monkeypatch.setenv("ETASSIA_CDYLIB", "/env/libetassia_ffi.so")
    assert _ffi._candidate_paths(None) == ["/env/libetassia_ffi.so", *PACKAGED, *_ffi._LIB_NAMES]
    monkeypatch.delenv("ETASSIA_CDYLIB", raising=False)
    assert _ffi._candidate_paths(None) == [*PACKAGED, *_ffi._LIB_NAMES]


def test_explicit_path_never_falls_back(monkeypatch, real_library_path) -> None:
    # The environment names a working library; the explicit missing path must
    # still fail, because explicit paths are exclusive.
    monkeypatch.setenv("ETASSIA_CDYLIB", real_library_path)
    monkeypatch.setattr(_ffi, "_lib", None)
    with pytest.raises(EtassiaError) as raised:
        render("flowchart TD\n  A --> B\n", library_path=MISSING)
    assert MISSING in str(raised.value)


def test_explicit_path_renders_without_env(monkeypatch, real_library_path) -> None:
    monkeypatch.delenv("ETASSIA_CDYLIB", raising=False)
    monkeypatch.setattr(_ffi, "_lib", None)
    svg = render("flowchart TD\n  A --> B\n", library_path=real_library_path)
    assert svg.startswith("<svg")
    assert detect("pie\n  \"a\": 1\n", library_path=real_library_path) == "pie"


def test_both_path_and_context_is_a_caller_error(real_library_path) -> None:
    with pytest.raises(ValueError):
        render("flowchart TD\n  A --> B\n", library_path=real_library_path, native_context=NativeContext())


def test_env_var_drives_the_default_lookup(monkeypatch, real_library_path) -> None:
    monkeypatch.setenv("ETASSIA_CDYLIB", real_library_path)
    monkeypatch.setattr(_ffi, "_lib", None)
    assert render("flowchart TD\n  A --> B\n").startswith("<svg")


def test_bogus_env_falls_through_to_the_next_candidate(monkeypatch) -> None:
    # The environment is tried first but is not exclusive: a missing env
    # library falls through to the packaged library, then system names.
    monkeypatch.setenv("ETASSIA_CDYLIB", MISSING)
    monkeypatch.setattr(_ffi, "_lib", None)
    try:
        assert render("flowchart TD\n  A --> B\n").startswith("<svg")
    except EtassiaError:
        pytest.skip("no packaged or system cdylib behind the environment")


def test_native_context_is_isolated_from_the_default_loader(
    monkeypatch, real_library_path
) -> None:
    def forbid_default():
        raise AssertionError("a native context used the default loader")

    monkeypatch.setattr(_ffi, "load", forbid_default)
    monkeypatch.setattr(_ffi, "_lib", None)
    context = NativeContext(real_library_path)
    assert context.library_path == real_library_path
    assert context.render("flowchart TD\n  A --> B\n").startswith("<svg")
    assert context.detect("pie\n  \"a\": 1\n") == "pie"
    # The context shares one library across calls without binding the module
    # singleton.
    assert _ffi._lib is None


def test_native_context_missing_library_is_exclusive(monkeypatch) -> None:
    monkeypatch.setenv("ETASSIA_CDYLIB", "/nonexistent/etassia-py-tests/env-only")
    context = NativeContext(MISSING)
    with pytest.raises(EtassiaError) as raised:
        context.load()
    assert MISSING in str(raised.value)
    with pytest.raises(EtassiaError):
        context.render("flowchart TD\n  A --> B\n")


def test_typed_rejections_through_a_context(real_library_path) -> None:
    context = NativeContext(real_library_path)
    with pytest.raises(Unported):
        context.render("sankey-beta\na,b,1\n")
    with pytest.raises(EtassiaError):
        context.detect("")
