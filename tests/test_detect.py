"""Detection: the type name for recognized sources, RenderError otherwise.

The type names are the corpus directory names ("pie", "state_diagram", ...),
the same vocabulary the Ruby binding exposes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from etassia import EtassiaError, RenderError, detect

CORPUS_DIR = Path(
    os.environ.get("ETASSIA_CORPUS_DIR", "")
    or Path(__file__).resolve().parents[1] / "etassia-rs" / "golden"
)

# The corpus grows as diagram types land; the type count is a floor, not a pin.
MIN_TYPES = 20

DETECTED = [
    ("flowchart TD\n  A --> B\n", "flowchart"),
    ("sequenceDiagram\n  A->>B: hi\n", "sequence"),
    ("classDiagram\n  class A\n", "class_diagram"),
    ("stateDiagram-v2\n  [*] --> a\n", "state_diagram"),
    ("erDiagram\n  a ||--o{ b : has\n", "er_diagram"),
    ("pie\n  \"a\": 1\n", "pie"),
    ("gantt\n  title t\n", "gantt"),
    ("sankey-beta\na,b,1\n", "sankey"),
    ("mindmap\n  root\n", "mindmap"),
]


def golden_cases() -> list[dict]:
    manifest = CORPUS_DIR / "manifest.json"
    if not CORPUS_DIR.is_dir() or not manifest.is_file():
        pytest.skip("etassia-rs/golden not present (set ETASSIA_CORPUS_DIR)")
    cases = json.loads(manifest.read_text(encoding="utf-8"))["cases"]
    assert cases, "corpus manifest is empty"
    return cases


def test_detect_returns_the_corpus_type_name(engine) -> None:
    for source, expected in DETECTED:
        assert detect(source) == expected, f"{source!r} detected as {detect(source)!r}, want {expected}"


def test_detect_rejects_unrecognized_sources(engine) -> None:
    # "" and unrecognized text carry the engine's DiagramTypeError class,
    # which this binding reports as RenderError (never Unported).
    for source in ("", "not a diagram at all\n"):
        with pytest.raises(RenderError) as raised:
            detect(source)
        assert raised.value.error_class == "DiagramTypeError"


def test_render_error_is_an_etassia_error(engine) -> None:
    with pytest.raises(EtassiaError):
        detect("not a diagram at all\n")


def test_detect_is_total_and_in_vocabulary_over_the_corpus(engine) -> None:
    """For every corpus case, detect returns a name from the corpus type
    vocabulary or raises DiagramTypeError. The manifest's `type` field is the
    corpus's own classification, not a detect oracle (cases of one type sit in
    another type's directory), so only the vocabulary is asserted here."""
    vocabulary = {case["type"] for case in golden_cases()}
    assert len(vocabulary) >= MIN_TYPES, f"unexpectedly small vocabulary: {sorted(vocabulary)}"
    detected = 0
    for case in golden_cases():
        source = (CORPUS_DIR / case["case"]).read_bytes().decode("utf-8")
        try:
            got = detect(source)
        except RenderError as raised:
            assert raised.error_class == "DiagramTypeError", f"{case['case']}: {raised}"
            continue
        assert got in vocabulary, f"{case['case']}: detect {got!r} outside the corpus vocabulary"
        detected += 1
    assert detected >= MIN_TYPES, f"unexpectedly few detections: {detected}"
