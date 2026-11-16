"""ctypes binding for the etassia C ABI (libetassia_ffi cdylib).

The C surface is the same three-symbol ABI the Ruby ffi tier drives:
`etassia_render` returns SVG on success or a JSON error wire, `etassia_detect`
returns the diagram type name on success or the same JSON wire, and
`etassia_free` releases each returned buffer at most once. Both workers return
the buffer BY VALUE as a `EtassiaBuf` struct. Nothing here interprets
diagrams — the engine bakes its own parse artifact at compile time, so this
module loads and verifies no artifact file.
"""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path

_LIB_NAMES = (
    "libetassia_ffi.dylib",
    "libetassia_ffi.so",
    "etassia_ffi.dll",  # cargo emits no lib prefix on windows
    "libetassia_ffi.dll",
)


class EtassiaError(RuntimeError):
    """The engine is unusable (library not found) or reported a hard error."""


class RenderError(EtassiaError):
    """The engine rejected the source with an error class other than Unported.

    `error_class` carries the wire class ("DiagramTypeError" for an
    unrecognized diagram, "ParseError" for a rejected body, "InvalidArgument"
    or "InvalidEncoding" for a malformed call); `line` and `col` carry the
    engine's position when it has one.
    """

    def __init__(self, wire: dict):
        self.wire = wire
        self.error_class = wire.get("class", "")
        self.message = wire.get("message", "")
        self.line = wire.get("line", 0)
        self.col = wire.get("col", 0)
        super().__init__(f"{self.error_class}: {self.message}")


class Unported(EtassiaError):
    """The diagram type is recognized but has no Rust renderer yet (class "Unported").

    `diagram_type` carries the type name from the wire message ("sankey",
    "unknown" for an unrecognized diagram, ...); callers may fall back to
    another implementation.
    """

    def __init__(self, wire: dict):
        self.wire = wire
        self.error_class = wire.get("class", "")
        self.diagram_type = wire.get("message", "")
        super().__init__(self.diagram_type)


class EtassiaBuf(ctypes.Structure):
    """The C ABI result: heap buffer (NUL-terminated UTF-8), byte length, status."""

    _fields_ = [
        ("ptr", ctypes.c_void_p),
        ("len", ctypes.c_size_t),
        ("status", ctypes.c_int),
    ]


def _candidate_paths(library_path: str | Path | None = None) -> list[str]:
    if library_path is not None:
        return [str(library_path)]  # explicit paths are exclusive: no fallback
    candidates: list[str] = []
    env = os.environ.get("ETASSIA_CDYLIB")
    if env:
        candidates.append(env)
    packaged = Path(__file__).resolve().parent / "lib"
    for name in _LIB_NAMES:
        candidates.append(str(packaged / name))
    for name in _LIB_NAMES:
        candidates.append(name)  # system loader search
    return candidates


_lib: ctypes.CDLL | None = None
_engine_commit: str | None = None


def _bind(lib: ctypes.CDLL) -> None:
    lib.etassia_render.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lib.etassia_render.restype = EtassiaBuf
    lib.etassia_detect.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
    lib.etassia_detect.restype = EtassiaBuf
    # DIM arrives with the same two-arg contract (etassia_render_dim in
    # crates/etassia-ffi); engines older than the DIM release do not
    # carry the symbol, and the library still loads — render_dim raises
    # the clear error at call time instead.
    try:
        lib.etassia_render_dim.argtypes = [ctypes.c_char_p, ctypes.c_size_t]
        lib.etassia_render_dim.restype = EtassiaBuf
    except AttributeError:
        pass
    # etassia_free takes the EtassiaBuf BY VALUE and frees the buffer at most once.
    lib.etassia_free.argtypes = [EtassiaBuf]
    lib.etassia_free.restype = None


def _load_library(library_path: str | Path | None = None) -> ctypes.CDLL:
    """Load and bind one library without changing the default context."""

    errors: list[str] = []
    lib: ctypes.CDLL | None = None
    for candidate in _candidate_paths(library_path):
        try:
            lib = ctypes.CDLL(candidate)
            break
        except OSError as error:  # noqa: PERF203 - small fixed list
            errors.append(f"{candidate}: {error}")
    if lib is None:
        raise EtassiaError(
            "libetassia_ffi not found (build it with `cargo build -p etassia-ffi "
            "--release` and point ETASSIA_CDYLIB at the dylib, or install a "
            "wheel that vendors it). Tried:\n  " + "\n  ".join(errors)
        )
    _bind(lib)
    return lib


def render_dim(
    document: str,
    *,
    library_path: str | Path | None = None,
    native_context: NativeContext | None = None,
) -> str:
    """Render a DIM 0.1 document to SVG; DIM has no fallback tier, so every
    failure raises RenderError (class "Unsupported" for a foreign DIM
    version). Engines without the export raise EtassiaError.
    """
    if not isinstance(document, str):
        raise TypeError("document must be a str")
    lib = _resolve_library(library_path, native_context)
    payload = document.encode("utf-8")
    worker = getattr(lib, "etassia_render_dim", None)
    if worker is None:
        raise EtassiaError(
            "the engine carries no etassia_render_dim export; it predates the DIM release"
        )
    status, data = _exchange(worker(payload, len(payload)), lib)
    if status != 0:
        _raise_for_wire(data)
    return data.decode("utf-8")


class NativeContext:
    """An independent, lazily loaded C ABI library.

    An explicit path is exclusive: failure never falls back to environment,
    packaged or system libraries. Sharing this object shares one native engine
    across calls without changing the module's default engine.
    """

    def __init__(self, library_path: str | Path | None = None):
        self.library_path = library_path
        self._lib: ctypes.CDLL | None = None

    def load(self) -> ctypes.CDLL:
        if self._lib is None:
            self._lib = _load_library(self.library_path)
        return self._lib

    def render(self, source: str) -> str:
        return render(source, native_context=self)

    def detect(self, source: str) -> str:
        return detect(source, native_context=self)


def load() -> ctypes.CDLL:
    """Load the default engine once, preserving existing lookup behavior."""
    global _lib
    if _lib is None:
        _lib = _load_library()
    return _lib


def engine_commit() -> str:
    """The etassia-rs commit this package pins (src/etassia/etassia-rs-version.txt).

    The C ABI carries no version symbol, so the pinned commit is the engine
    identity: every wheel vendors the cdylib built from exactly this commit.
    """
    global _engine_commit
    if _engine_commit is None:
        import importlib.resources

        resource = importlib.resources.files("etassia").joinpath("etassia-rs-version.txt")
        _engine_commit = resource.read_text(encoding="utf-8").strip()
    return _engine_commit


def _exchange(buf: EtassiaBuf, lib: ctypes.CDLL) -> tuple[int, bytes]:
    """Read a returned buffer's bytes and free it through the same library
    that produced it, including when the read itself fails."""
    try:
        if buf.ptr:
            data = ctypes.string_at(buf.ptr, buf.len)
        else:
            data = b""
    finally:
        lib.etassia_free(buf)
    return buf.status, data


def _raise_for_wire(data: bytes) -> None:
    try:
        wire = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EtassiaError(f"unparseable engine error payload: {data[:200]!r}") from error
    if not isinstance(wire, dict) or not isinstance(wire.get("class"), str):
        raise EtassiaError(f"invalid engine error wire: {data[:200]!r}")
    if wire["class"] == "Unported":
        raise Unported(wire)
    raise RenderError(wire)


def _resolve_library(
    library_path: str | Path | None, native_context: NativeContext | None
) -> ctypes.CDLL:
    """The library one call uses: an explicit path, a context, or the default.

    An explicit `library_path` loads an independent, exclusive library and
    never touches the module's default engine; `NativeContext` shares one
    engine across calls. Passing both is a caller error.
    """
    if library_path is not None and native_context is not None:
        raise ValueError("pass either library_path or native_context, not both")
    if native_context is not None:
        return native_context.load()
    if library_path is not None:
        return _load_library(library_path)
    return load()


def render(
    source: str,
    *,
    library_path: str | Path | None = None,
    native_context: NativeContext | None = None,
) -> str:
    """Render a diagram source to SVG; raises Unported or RenderError on failure."""
    if not isinstance(source, str):
        raise TypeError("source must be a str")
    lib = _resolve_library(library_path, native_context)
    payload = source.encode("utf-8")
    status, data = _exchange(lib.etassia_render(payload, len(payload), None), lib)
    if status != 0:
        _raise_for_wire(data)
    return data.decode("utf-8")


def detect(
    source: str,
    *,
    library_path: str | Path | None = None,
    native_context: NativeContext | None = None,
) -> str:
    """The diagram type name of `source`; raises RenderError when nothing matches."""
    if not isinstance(source, str):
        raise TypeError("source must be a str")
    lib = _resolve_library(library_path, native_context)
    payload = source.encode("utf-8")
    status, data = _exchange(lib.etassia_detect(payload, len(payload)), lib)
    if status != 0:
        _raise_for_wire(data)
    return data.decode("utf-8")
