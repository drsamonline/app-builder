#!/usr/bin/env python3
"""The proof for the adaptive-icon step: an SVG-only app is not "no icon".

WHAT WENT WRONG, exactly.

kitbox carries `app/icon.svg` and nothing else. `make_icons.py` knows about SVG
(it rasterises it through cairosvg, and falls back to a monogram tile when
cairosvg is absent), but `make_adaptive_icon.py` only ever looked for PNG/JPG.
So on 2026-11-08 the pipeline wrote the launcher icons fine and then died in the
opt-in adaptive step with

    no icon in the app directory — nothing to make adaptive
    ##[error]Process completed with exit code 1

which skipped the release and the demo deploy. The app had an icon; the script
could not see it.

What this test pins down:

  1. SVG-only app, cairosvg present  -> the full adaptive set is written, exit 0
  2. SVG-only app, cairosvg absent   -> a clear skip, exit 0, NOTHING written
     (the ordinary launcher icon make_icons.py wrote is still a valid APK)
  3. PNG app                          -> unchanged: the full set, exit 0
  4. app with no artwork at all       -> still exit 1 with the original message

    python3 -m unittest discover -s tests -v

MIT. (c) 2026 Dr Sohil Momin.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, os.pardir, "tools", "make_adaptive_icon.py")

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
       '<rect width="64" height="64" fill="#1f2937"/>'
       '<circle cx="32" cy="32" r="18" fill="#e11d48"/></svg>')

DENSITIES = ("mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi")


def run(app_dir, res_dir, extra_path=None):
    env = dict(os.environ)
    if extra_path:
        env["PYTHONPATH"] = extra_path + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run([sys.executable, SCRIPT, "--app", app_dir, "--res", res_dir],
                          capture_output=True, text=True, env=env)


class AdaptiveIconSvg(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="adaptive-")
        self.app = os.path.join(self.tmp, "app")
        self.res = os.path.join(self.tmp, "res")
        os.makedirs(self.app)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def written(self):
        return sorted(os.path.join(d, f) for d, _, fs in os.walk(self.res) for f in fs)

    def assert_full_set(self):
        files = self.written()
        for d in DENSITIES:
            for name in ("ic_launcher_foreground.png", "ic_launcher_background.png"):
                self.assertIn(os.path.join(self.res, f"mipmap-{d}", name), files)
        for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
            self.assertIn(os.path.join(self.res, "mipmap-anydpi-v26", name), files)
        self.assertEqual(len(files), 12)

    def test_svg_only_app_is_built_when_cairosvg_is_available(self):
        try:
            import cairosvg                                     # noqa: F401
        except ImportError:
            self.skipTest("cairosvg is not installed here — case 2 covers that path")
        with open(os.path.join(self.app, "icon.svg"), "w", encoding="utf-8") as fh:
            fh.write(SVG)
        r = run(self.app, self.res)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("no icon in the app directory", r.stderr)
        self.assert_full_set()
        # The rasterised artwork is a scratch file, not a shipped asset.
        self.assertFalse(os.path.exists(os.path.join(self.app, "icon.png")))

    def test_svg_without_cairosvg_skips_loudly_and_writes_nothing(self):
        with open(os.path.join(self.app, "icon.svg"), "w", encoding="utf-8") as fh:
            fh.write(SVG)
        # A cairosvg that cannot be imported, so the script takes the real ImportError path.
        stub = os.path.join(self.tmp, "stub")
        os.makedirs(stub)
        with open(os.path.join(stub, "cairosvg.py"), "w", encoding="utf-8") as fh:
            fh.write("raise ImportError('not installed')\n")
        r = run(self.app, self.res, extra_path=stub)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("cairosvg is not available", r.stderr)
        self.assertNotIn("no icon in the app directory", r.stderr)
        self.assertEqual(self.written(), [])

    def test_png_app_is_unchanged(self):
        from PIL import Image                     # the script requires Pillow itself
        Image.new("RGBA", (64, 64), (31, 41, 55, 255)).save(os.path.join(self.app, "icon.png"))
        r = run(self.app, self.res)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_full_set()

    def test_an_app_with_no_artwork_still_fails(self):
        r = run(self.app, self.res)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no icon in the app directory", r.stderr)
        self.assertEqual(self.written(), [])


if __name__ == "__main__":
    unittest.main()
