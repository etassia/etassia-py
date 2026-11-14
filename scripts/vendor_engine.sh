#!/usr/bin/env bash
# Vendor the engine into the wheel build (the cibuildwheel BEFORE_ALL).
#
# Runs INSIDE each wheel build environment — native runners, and the
# QEMU-emulated manylinux/musllinux containers for the cross-arch
# legs, where the emulated host is the target: rustup installs the
# emulated toolchain and cargo builds natively for it (the
# leptris/leptris-py#346 pattern). macOS builds both slices and lipos
# a universal2 engine; Windows legs pass ETASSIA_RUST_TARGET for the
# cross arches (the runner stays x64).
#
# The ENGINE SOURCE comes from the pinned release tree
# (src/etassia/etassia-rs-version.txt carries the release COMMIT; the
# engine ships without tags), fetched here: cibuildwheel copies only the
# package directory into its build containers, and a submodule's
# content does not ride along — the leptris-py codeload pattern, with
# the commit bumped by every ride PR.
set -eu
cd "$(dirname "$0")/.."

# DNS under QEMU emulation flakes (curl error 6, which is outside the
# default --retry set, while --retry-all-errors needs curl 7.71+ and
# the manylinux_2_28 images ship 7.61) - so the retry loop lives in
# the shell, and the body lands in a file before any pipe consumes it.
fetch_to() {
  url="${1:?}" out="${2:?}" attempt=1
  while :; do
    if curl --proto '=https' --retry 5 --connect-timeout 30 -sSL \
      -o "$out" "$url"; then
      return 0
    fi
    [ "$attempt" -ge 5 ] && return 1
    attempt=$((attempt + 1))
    sleep 5
  done
}

echo "vendor_engine: uname -m=$(uname -m)"
case "$(uname -m)" in
  armv7l | armv8l)
    # the musllinux armv7 image ships a rust whose std cannot serve
    # armv7-unknown-linux-musleabihf (E0463 at compile time), so the
    # image's rust is replaced wholesale by Alpine edge's, which is
    # dylib-capable and new enough for the engine's MSRV. No rustup
    # anywhere in this container.
    apk add -q rust cargo \
      --repository http://dl-cdn.alpinelinux.org/alpine/edge/main \
      --allow-untrusted
    ;;
  *)
    if ! command -v cargo >/dev/null 2>&1; then
      fetch_to https://sh.rustup.rs tmp/rustup-init.sh
      sh tmp/rustup-init.sh -y --profile minimal
      export PATH="$HOME/.cargo/bin:/usr/bin:$PATH"
    fi
    ;;
esac

commit="$(cat src/etassia/etassia-rs-version.txt)"
mkdir -p tmp/engine
fetch_to "https://codeload.github.com/etassia/etassia-rs/tar.gz/${commit}" \
  tmp/engine.tar.gz
tar xz --strip-components=1 -C tmp/engine < tmp/engine.tar.gz

mkdir -p src/etassia/lib

build() {
  extra="${1:-}"
  (cd tmp/engine && cargo build -p etassia-ffi --release $extra)
}

# The runner-side cross link (the Windows-leg pattern, on Linux too):
# cargo-zigbuild supplies the foreign-musl C toolchain via zig cc; the
# emulated container never runs a toolchain installer, it only smokes
# the finished wheel.
build_cross() {
  target="${1:?cross mode needs ETASSIA_RUST_TARGET}"
  (cd tmp/engine && cargo zigbuild -p etassia-ffi --release --target "$target")
}

os="$(uname -s)"
case "$os" in
  Linux)
    lib="libetassia_ffi.so"
    out="tmp/engine/target/release/libetassia_ffi.so"
    if [ -n "${ETASSIA_RUST_TARGET:-}" ]; then
      rustup target add "$ETASSIA_RUST_TARGET"
      build_cross "$ETASSIA_RUST_TARGET"
      out="tmp/engine/target/$ETASSIA_RUST_TARGET/release/libetassia_ffi.so"
    else
    case "$(uname -m)" in
      x86_64 | aarch64)
        # the emulated container is the target: a plain host build
        build
        ;;
      i686)
        rustup target add i686-unknown-linux-gnu
        build "--target i686-unknown-linux-gnu"
        out="tmp/engine/target/i686-unknown-linux-gnu/release/libetassia_ffi.so"
        ;;
      armv7l | armv8l)
        # apk's rust targets the native armv7-musl directly and ships
        # no rustup - a target add is both unneeded and impossible
        if command -v rustup >/dev/null 2>&1; then
          rustup target add armv7-unknown-linux-musleabihf
        fi
        build "--target armv7-unknown-linux-musleabihf"
        out="tmp/engine/target/armv7-unknown-linux-musleabihf/release/libetassia_ffi.so"
        ;;
      ppc64le)
        rustup target add powerpc64le-unknown-linux-gnu
        build "--target powerpc64le-unknown-linux-gnu"
        out="tmp/engine/target/powerpc64le-unknown-linux-gnu/release/libetassia_ffi.so"
        ;;
      s390x)
        rustup target add s390x-unknown-linux-gnu
        build "--target s390x-unknown-linux-gnu"
        out="tmp/engine/target/s390x-unknown-linux-gnu/release/libetassia_ffi.so"
        ;;
      riscv64)
        # the riscv64 tier ships musl-only today (the glibc images left
        # quay entirely) - ETASSIA_MUSL=1 selects the musl triple
        if [ "${ETASSIA_MUSL:-}" = "1" ]; then
          rustup target add riscv64gc-unknown-linux-musl
          build "--target riscv64gc-unknown-linux-musl"
          out="tmp/engine/target/riscv64gc-unknown-linux-musl/release/libetassia_ffi.so"
        else
          rustup target add riscv64gc-unknown-linux-gnu
          build "--target riscv64gc-unknown-linux-gnu"
          out="tmp/engine/target/riscv64gc-unknown-linux-gnu/release/libetassia_ffi.so"
        fi
        ;;
      *)
        echo "unsupported linux arch $(uname -m)" >&2
        exit 1
        ;;
    esac
    fi
    cp "$out" "src/etassia/lib/$lib"
    ;;

  Darwin)
    # universal2: both slices built, lipo'd into one engine
    rustup target add x86_64-apple-darwin aarch64-apple-darwin
    build "--target x86_64-apple-darwin"
    build "--target aarch64-apple-darwin"
    lipo -create \
      tmp/engine/target/x86_64-apple-darwin/release/libetassia_ffi.dylib \
      tmp/engine/target/aarch64-apple-darwin/release/libetassia_ffi.dylib \
      -output src/etassia/lib/libetassia_ffi.dylib
    ;;

  MINGW* | MSYS* | CYGWIN*)
    target="${ETASSIA_RUST_TARGET:-}"
    if [ -n "$target" ]; then
      rustup target add "$target"
      build "--target $target"
      out="tmp/engine/target/$target/release/etassia_ffi.dll"
    else
      build
      out="tmp/engine/target/release/etassia_ffi.dll"
    fi
    cp "$out" "src/etassia/lib/etassia_ffi.dll"
    ;;

  *)
    echo "unsupported OS $os" >&2
    exit 1
    ;;
esac

echo "vendored from etassia-rs @${commit:0,12}: $(ls src/etassia/lib)"
