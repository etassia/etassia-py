"""Unported routing: the engine declines recognized-but-unported types with
class "Unported", and this binding reports them as the `Unported` exception
so callers can fall back to another implementation.

The expectations here mirror the ruby binding's native_spec.rb.
"""

from __future__ import annotations

import pytest

from etassia import EtassiaError, RenderError, Unported, detect, render

UNPORTED_SOURCE = "sankey-beta\na,b,1\n"
UNRECOGNIZED_SOURCE = "not a diagram at all\n"


def test_unported_type_raises_unported(engine) -> None:
    with pytest.raises(Unported) as raised:
        render(UNPORTED_SOURCE)
    # The str form is the type name, matching the ruby binding's message.
    assert str(raised.value) == "sankey"
    assert raised.value.diagram_type == "sankey"
    assert raised.value.wire == {
        "class": "Unported",
        "message": "sankey",
        "line": 0,
        "col": 0,
    }


def test_unrecognized_source_renders_as_the_unknown_fallback(engine) -> None:
    # `detect` reports DiagramTypeError for unrecognized sources, but the
    # engine's render path routes them to the Ruby-fallback "unknown" bucket.
    with pytest.raises(Unported) as raised:
        render(UNRECOGNIZED_SOURCE)
    assert raised.value.diagram_type == "unknown"
    assert not isinstance(raised.value, RenderError)


def test_unported_is_not_render_error_and_both_are_etassia_errors(engine) -> None:
    with pytest.raises(Unported) as raised:
        render(UNPORTED_SOURCE)
    assert not isinstance(raised.value, RenderError)
    assert isinstance(raised.value, EtassiaError)
    with pytest.raises(RenderError) as other:
        detect("")
    assert not isinstance(other.value, Unported)
    assert isinstance(other.value, EtassiaError)


def test_callers_may_fall_back_on_unported(engine) -> None:
    rendered: list[str] = []
    try:
        rendered.append(render(UNPORTED_SOURCE))
    except Unported:
        rendered.append("<svg>fallback</svg>")
    assert rendered == ["<svg>fallback</svg>"]
