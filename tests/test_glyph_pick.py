#!/usr/bin/env python3
"""The icon generator must never fall back to initials when it has a word to go on.

WHAT WENT WRONG: all 36 app repos shipped the same monogram, because nothing ever
looked at what the app was. A new app scaffolded by Forge has a name and a landing
page - that is enough to pick a glyph that means something. This is the guard.

Run by .github/workflows/tests.yml via `unittest discover -s tests`.
"""
import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools", "make_icons.py")


def _load():
    spec = importlib.util.spec_from_file_location("make_icons", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class GlyphPickTest(unittest.TestCase):
    def test_obvious_names_get_an_obvious_glyph(self):
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
            self.assertEqual(glyph, expected, "%s -> %s, expected %s" % (name, glyph, expected))
            self.assertTrue(colour.startswith("#") and len(colour) == 7, colour)

    def test_unknown_app_returns_no_glyph_but_a_stable_colour(self):
        m = _load()
        glyph, colour = m.pick_glyph("zzz-nothing-matches-here", "")
        self.assertIsNone(glyph)          # caller draws a monogram, deliberately
        self.assertTrue(colour.startswith("#"))

    def test_every_glyph_draws_at_any_size(self):
        m = _load()
        for name in m.GLYPHS:
            for size in (48, 64, 192):
                img = m.draw_glyph(name, "#123456", size)
                self.assertEqual(img.size, (size, size))

    def test_description_is_used_when_the_name_is_blank(self):
        m = _load()
        glyph, _ = m.pick_glyph("app", "a private offline GST invoicing tool")
        self.assertEqual(glyph, "receipt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
