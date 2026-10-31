"""The icon generator must never fall back to initials when it has a word to go on.

This is the guard for the thing that went wrong across 36 repos: every app shipped
the same monogram because nothing looked at what the app actually was. A new app
scaffolded by Forge has a name and a landing page; that is enough to pick a glyph.
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools", "make_icons.py")


def _load():
    spec = importlib.util.spec_from_file_location("make_icons", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_glyph_matches_obvious_names():
    m = _load()
    cases = [
        ("invoice-maker", "GST billing", "receipt"),
        ("my-calendar", "daily planner with streaks", "calendar"),
        ("app-vault", "sealed notes, opened once", "envelope"),
        ("pdf-splitter", "merge and split PDFs", "book"),
        ("sound-mixer", "ambient sound layers", "wave"),
        ("repertory-pro", "homeopathic rubric grading", "search"),
    ]
    for name, desc, expected in cases:
        glyph, colour = m.pick_glyph(name, desc)
        assert glyph == expected, "%s -> %s, expected %s" % (name, glyph, expected)
        assert colour.startswith("#") and len(colour) == 7


def test_unknown_app_still_gets_a_colour():
    m = _load()
    glyph, colour = m.pick_glyph("zzz-nothing-matches-here", "")
    assert glyph is None          # caller falls back to a monogram, deliberately
    assert colour.startswith("#")  # but the tile colour is still stable and distinct


def test_every_glyph_draws():
    m = _load()
    for name in m.GLYPHS:
        img = m.draw_glyph(name, "#123456", 64)
        assert img.size == (64, 64)


if __name__ == "__main__":
    test_glyph_matches_obvious_names()
    test_unknown_app_still_gets_a_colour()
    test_every_glyph_draws()
    print("all glyph tests passed")
