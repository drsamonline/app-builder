#!/usr/bin/env python3
"""The proof for the default launcher icons: a checkout of THIS kit builds an APK.

WHAT WENT WRONG, exactly.

`apk/app/src/main/AndroidManifest.xml` has said

    android:icon="@mipmap/ic_launcher"
    android:roundIcon="@mipmap/ic_launcher_round"

since the icon work, but `apk/app/src/main/res/` carried no mipmap at all: the
icons were only ever written at BUILD time, by the "Generate the launcher icons"
step in `.github/workflows/build.yml`. Callers call that reusable workflow at a
PINNED SHA (app-companion-forge and ~17 others pin 34fa725, which predates the
icon step) while `actions/checkout` of the kit follows the DEFAULT BRANCH. So on
2026-10-28 at 15:58 UTC eighteen repositories ran an OLD workflow against a NEW
manifest, no mipmap was ever written, and AAPT failed every one of them with:

    error: resource mipmap/ic_launcher ... not found
    error: resource mipmap/ic_launcher_round ... not found

The pinned caller is not the bug; a template that only compiles after a build
step has run is. A manifest may only reference a resource that is IN the tree.

So the defaults are committed (they are the monogram tile make_icons.py draws
when an app has no icon of its own), and this test asserts the invariant the
failure broke: every @mipmap the manifest names resolves to a real PNG, at every
density, straight out of git.

    python3 -m unittest discover -s tests -v

MIT. (c) 2026 Dr Sohil Momin.
"""
import os
import re
import struct
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RES = os.path.join(ROOT, "apk", "app", "src", "main", "res")
MANIFEST = os.path.join(ROOT, "apk", "app", "src", "main", "AndroidManifest.xml")

ANDROID = "{http://schemas.android.com/apk/res/android}"

# The densities make_icons.py writes, and the size it writes at each one.
DENSITIES = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}


def png_size(path):
    """(width, height) from the PNG IHDR, without needing Pillow."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("%s is not a PNG" % path)
    if head[12:16] != b"IHDR":
        raise ValueError("%s has no IHDR chunk" % path)
    return struct.unpack(">II", head[16:24])


def manifest_mipmaps():
    """Every @mipmap/<name> the manifest points at, as names."""
    root = ET.parse(MANIFEST).getroot()
    found = set()
    for el in root.iter():
        for attr in ("icon", "roundIcon"):
            value = el.get(ANDROID + attr)
            if value is None:
                continue
            m = re.fullmatch(r"@mipmap/([A-Za-z0-9_]+)", value)
            if m:
                found.add(m.group(1))
    return found


class ManifestIconsResolve(unittest.TestCase):
    def test_manifest_names_at_least_one_mipmap(self):
        """If this is empty the rest of the file proves nothing - fail loudly."""
        names = manifest_mipmaps()
        self.assertTrue(names, "AndroidManifest.xml references no @mipmap/ resource")

    def test_every_named_mipmap_exists_at_every_density(self):
        """The exact assertion that failed in eighteen repositories."""
        names = manifest_mipmaps()
        missing = []
        for name in sorted(names):
            for folder in DENSITIES:
                path = os.path.join(RES, folder, name + ".png")
                if not os.path.isfile(path):
                    missing.append(os.path.relpath(path, ROOT))
        self.assertEqual(
            missing, [],
            "the manifest references a mipmap that is not in the tree - a pinned "
            "caller of build.yml never runs the icon step, so AAPT fails with "
            "'resource mipmap/<name> not found'. Missing:\n  "
            + "\n  ".join(missing),
        )

    def test_every_mipmap_is_a_square_png_of_the_right_size(self):
        for name in sorted(manifest_mipmaps()):
            for folder, size in DENSITIES.items():
                path = os.path.join(RES, folder, name + ".png")
                with self.subTest(name=name, folder=folder):
                    w, h = png_size(path)
                    self.assertEqual((w, h), (size, size),
                                     "%s should be %dpx square" % (path, size))

    def test_the_round_icon_is_actually_round(self):
        """A round icon that is a copy of the square one is not a round icon.

        The corners of a circular mask are transparent; a square tile's are not.
        Cheap check, no Pillow: compare the two files' bytes and their corner
        alpha via a tiny PNG decode is overkill - so compare file bytes, which is
        what a straight copy produces.
        """
        for folder in DENSITIES:
            square = os.path.join(RES, folder, "ic_launcher.png")
            round_ = os.path.join(RES, folder, "ic_launcher_round.png")
            if not (os.path.isfile(square) and os.path.isfile(round_)):
                continue                      # covered by the existence test
            with open(square, "rb") as fh:
                a = fh.read()
            with open(round_, "rb") as fh:
                b = fh.read()
            with self.subTest(folder=folder):
                self.assertNotEqual(a, b, "%s: the round icon is a copy of the square one"
                                    % folder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
