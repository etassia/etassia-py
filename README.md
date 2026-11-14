# etassia (Python)

Etassia is a diagram-rendering engine that renders Mermaid-syntax diagram
sources to SVG, and the same source must produce the same SVG in every runtime
that embeds the engine. This package is the Python binding for that engine. It
drives `libetassia_ffi`, the C application binary interface (ABI) cdylib that
the Ruby binding ships, through Python's built-in `ctypes` library. The
package contains no second renderer and no reimplementation of any diagram
type: every diagram is rendered by the same native engine the other runtimes
use, and the rendered SVG is byte-identical with the Ruby reference
implementation.

```sh
pip install etassia
```

Each platform wheel **vendors** the cdylib, which `scripts/vendor_engine.sh`
compiles from the pinned etassia-rs commit, and the golden-parity suite runs
on every wheel platform at build time (the emulated legs included):

| platform | tag | proof |
|---|---|---|
| Linux x86_64 (glibc) | manylinux_2_35 | full suite, native runner |
| Linux aarch64 (glibc) | manylinux_2_35 | full suite, native arm runner |
| Linux aarch64 (musl) | musllinux_1_2 | full suite, native arm runner |
| Linux i686 (glibc) | manylinux_2_28 | full suite under qemu |
| Linux armv7l (musl) | musllinux_1_2 | full suite under qemu |
| Linux ppc64le | manylinux_2_28 | full suite under qemu |
| Linux s390x | manylinux_2_28 | big-endian; full suite under qemu |
| Linux riscv64 (musl) | musllinux_1_2 | full suite under qemu |
| macOS x86_64 + arm64 | macosx_11_0_universal2 | lipo'd engine; native runners |
| Windows x64 / ARM64 / x86 | win_amd64 / win_arm64 / win32 | full suite, native runner |

This package does not ship an sdist, because the Rust engine sources are a
submodule of this repository and are not part of the source archive, so a
source install could never build or load the engine. For local development, a
locally built library reaches the runtime through the `ETASSIA_CDYLIB`
environment variable, which the loader tries before the packaged library.

```python
import etassia

svg = etassia.render("flowchart TD\n  A[Start] --> B[End]\n")
diagram_type = etassia.detect('pie\n  "a": 1\n')     # "pie"

etassia.engine_commit()   # the pinned etassia-rs commit
etassia.__version__       # this package's version
```

On rejection, `render` and `detect` raise `Unported` when the engine's error
wire carries the class "Unported", which means the diagram type is recognized
but has no Rust renderer yet, so callers may fall back to another
implementation; `sankey-beta` sources behave this way. Every other error class
raises `RenderError`: `DiagramTypeError` when the source is not a recognized
diagram, and `ParseError` when the body is rejected for its type. The engine
bakes its parse artifact into the cdylib at compile time; this package loads
no artifact file and verifies no artifact checksum.

## Releases

etassia is one product on **four runtimes**: **rs** (crates.io +
`@etassia/wasm` + release binaries), **ruby** (rubygems), **python** (PyPI,
this package), and **typescript** (npm, `etassia` — the wasm-backed runtime).
**Every engine update releases all four together**; a release that ships some
runtimes and not the rest is incomplete. This package's `version` and the
pinned engine commit in `src/etassia/etassia-rs-version.txt` move together in
one ride commit, and every wheel then vendors the cdylib built from that
exact commit.

## Status and honest boundaries (v0.1)

| Capability | State |
|---|---|
| Native render, byte-identical SVG | **works** — 1183 of the 1206 golden-corpus cases render through the cdylib byte-identically with the Ruby implementation, with zero mismatches |
| Diagram type detection | **works** — `detect` returns the corpus type name for every recognized source and reports `DiagramTypeError` otherwise |
| Unported routing | **works** — the remaining 23 cases (the `error` bucket and unrecognized sources routed to `unknown`) raise `Unported`, and `sankey-beta` is declined the same way, matching the ruby binding's native spec |
| Explicit native libraries | **works** — exclusive `library_path`, shared `NativeContext`, `ETASSIA_CDYLIB` |
| Wheels on PyPI | not yet published — `release.yml` builds and audits the platform wheels; the trusted-publisher registration is owner-side |

## Development

```sh
cargo build -p etassia-ffi --release          # in etassia-rs
export ETASSIA_CDYLIB=$RS/target/release/libetassia_ffi.dylib
python3 -m pip install -e . pytest
python3 -m pytest tests -q
```

The tests skip cleanly when no cdylib is reachable and skip the corpus gate
when the golden directory is absent; with the submodule checked out, the
default corpus path (`etassia-rs/golden`) resolves and the gate runs.
`scripts/vendor_engine.sh` fetches the engine sources for the pinned commit
from codeload and builds the cdylib into `src/etassia/lib/`; the wheel build
runs it on every platform, and on macOS it builds both slices and combines
them into one universal2 engine. The corpus grows deliberately as diagram
types land, so its counts in the tests are floors, not pins.

## Explicit native libraries

Every public function accepts an optional `library_path` argument, which is
exclusive: it names the one library to load, and a failure to load it never
falls back to the environment variable, the packaged library, or a system
library. To share one engine between calls, a caller creates
`NativeContext(library_path)` and passes it as `native_context=`; each context
binds its own render, detect and free functions, every returned buffer is
freed through the library that produced it, and an explicit path or context
never changes the module's default engine. The default lookup order, used
when neither argument is present, is the `ETASSIA_CDYLIB` environment
variable, then the packaged library, then the bare system library names.
