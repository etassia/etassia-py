"""Render parity: every golden case through the engine, byte-compared to the
Ruby-generated SVG.

Mirrors crates/etassia/tests/golden.rs and the ruby binding's golden replay:
the engine's SVG must be byte-identical with the reference implementation on
every ported diagram type. The corpus's fallback buckets (`error`, `unknown`,
plus any type the engine declines such as `sankey`) may raise Unported; they
are counted, never compared.
"""

from __future__ import annotations

import collections
import json
import os
from pathlib import Path

import pytest

from etassia import Unported, render

# The corpus's fallback buckets that exist to prove the Ruby fallback path;
# every other corpus type is ported and must render byte-identically.
FALLBACK_TYPES = {"error", "unknown", "sankey"}

CORPUS_DIR = Path(
    os.environ.get("ETASSIA_CORPUS_DIR", "")
    or Path(__file__).resolve().parents[1] / "etassia-rs" / "golden"
)

# The corpus grows as diagram types land (a new type ships with its cases in
# the same ride), so these are floors, not pins.
MIN_PAIRS = 20
MIN_MATCHED = 1000


def golden_cases() -> list[dict]:
    manifest = CORPUS_DIR / "manifest.json"
    if not CORPUS_DIR.is_dir() or not manifest.is_file():
        pytest.skip("etassia-rs/golden not present (set ETASSIA_CORPUS_DIR)")
    cases = json.loads(manifest.read_text(encoding="utf-8"))["cases"]
    assert cases, "corpus manifest is empty"
    return cases


def test_every_golden_case_byte_identical(engine) -> None:
    counts: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])  # match, unported, fail
    first_failure: dict[str, str] = {}
    for case in golden_cases():
        source = (CORPUS_DIR / case["case"]).read_bytes().decode("utf-8")
        want = (CORPUS_DIR / case["case"].replace(".mmd", ".svg")).read_bytes()
        row = counts[case["type"]]
        try:
            got = render(source)
        except Unported:
            row[1] += 1
            continue
        if got.encode("utf-8") == want:
            row[0] += 1
        else:
            row[2] += 1
            first_failure.setdefault(case["type"], case["case"])
    for diagram_type, (ok, unported, bad) in sorted(counts.items()):
        print(f"{diagram_type:16} match={ok:4} unported={unported:3} mismatch={bad:3}")
    total = [sum(row[i] for row in counts.values()) for i in range(3)]
    print("TOTAL match=%d unported=%d mismatch=%d" % tuple(total))
    mismatches = {t: row[2] for t, row in counts.items() if row[2]}
    assert not mismatches, f"not byte-identical: {mismatches} first={first_failure}"
    ported_unported = {
        t: row[1] for t, row in counts.items() if row[1] and t not in FALLBACK_TYPES
    }
    assert not ported_unported, f"ported types raised Unported: {ported_unported}"
    assert total[0] + total[1] >= MIN_PAIRS, f"unexpectedly small corpus: {total[0] + total[1]}"
    assert total[0] >= MIN_MATCHED, f"natively matched count dropped: {total[0]}"
