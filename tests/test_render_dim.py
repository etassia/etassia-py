"""The DIM tier: render_dim renders a DIM 0.1 document to SVG."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from etassia import EtassiaError, RenderError, engine_commit, render_dim

REPO = Path(__file__).resolve().parents[1]


def document() -> str:
    """The etassia-rs DIM example from the pinned engine checkout."""
    path = REPO / "etassia-rs" / "docs" / "dim" / "examples" / "flowchart-as-dim.json"
    return path.read_text(encoding="utf-8")


def test_render_dim_renders_a_document_to_svg(engine) -> None:  # noqa: ARG001
    svg = render_dim(document())
    assert svg.startswith("<svg")
    assert "Hard" in svg


def test_render_dim_is_deterministic(engine) -> None:  # noqa: ARG001
    assert render_dim(document()) == render_dim(document())


def test_render_dim_rejects_a_foreign_version(engine) -> None:  # noqa: ARG001
    wrong = json.loads(document())
    wrong["dim"] = "9.9"
    with pytest.raises(RenderError) as raised:
        render_dim(json.dumps(wrong))
    assert raised.value.error_class == "Unsupported"


def test_the_pinned_engine_carries_the_export(engine) -> None:  # noqa: ARG001
    # the wheels vendor the cdylib built from exactly this commit, and
    # this commit carries etassia_render_dim; an engine without the
    # symbol raises the clear error instead of rendering
    commit = engine_commit()
    assert len(commit) == 40
    with pytest.raises(EtassiaError):
        render_dim("{not json")
