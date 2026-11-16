"""etassia — Python binding for the etassia diagram engine.

Renders Mermaid-syntax diagram sources to SVG through the etassia C ABI (the
same cdylib the Ruby and TypeScript runtimes ship), byte-identical with the
Ruby reference implementation on every ported diagram type.
"""

from ._ffi import (
    EtassiaError,
    NativeContext,
    RenderError,
    Unported,
    detect,
    engine_commit,
    load,
    render,
    render_dim,
)

try:
    # The installed distribution's version is authoritative: pyproject is
    # the single source, and a hardcoded literal here went stale in the
    # sibling product (parsanol ruby#369's packaging twin).
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("etassia")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0.dev0"

__all__ = [
    "EtassiaError",
    "NativeContext",
    "RenderError",
    "Unported",
    "__version__",
    "detect",
    "engine_commit",
    "load",
    "render",
]
