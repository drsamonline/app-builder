#!/usr/bin/env python3
"""make_adaptive_icon.py — write Android adaptive-icon resources for an app.

    python3 make_adaptive_icon.py --app app-repo/docs/play --res builder/apk/app/src/main/res

Android 8+ masks a launcher icon to whatever shape the device uses. A plain PNG is
letterboxed inside that mask; an *adaptive* icon supplies two layers — a background
that fills the shape and a foreground that is guaranteed to survive the crop — so
the icon looks native on every launcher.

This is OPT-IN in the pipeline (`adaptive_icon: true`), because it writes into the
APK's resource tree: an app whose project already defines these resources would
otherwise get a duplicate-resource error.

WHAT IT LOOKS FOR, in the app directory (same search order as make_icons.py):

    icon-adaptive-foreground.png   the glyph, transparent ground
    icon-adaptive-background.png   the ground, no glyph

If neither exists it derives both from the ordinary icon: the foreground is the
icon's artwork scaled into the 66% safe zone, and the background is the icon's own
dominant colour. That means an app with one PNG still gets a shaped icon.

WHAT IT WRITES (108dp, so 108/162/216/324/432 px at mdpi..xxxhdpi):

    mipmap-{m,h,xh,xxh,xxxh}dpi/ic_launcher_foreground.png
    mipmap-{m,h,xh,xxh,xxxh}dpi/ic_launcher_background.png
    mipmap-anydpi-v26/ic_launcher.xml
    mipmap-anydpi-v26/ic_launcher_round.xml

The background is a PNG rather than a <color> in values/, deliberately: a values
file would collide with whatever the APK project already calls its colours, and a
duplicate resource is a build failure, not a warning.

MIT. (c) 2026 Dr Sohil Momin.
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

try:
    from PIL import Image
except ImportError:                                    # pragma: no cover
    print("Pillow is required (the pipeline installs it)", file=sys.stderr)
    raise SystemExit(2)

DENSITIES = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
ICON_NAMES = ("icon.png", "icon.jpg", "docs/icon.png", "assets/icon.png")
# In the app directory first, then beside it: an app that keeps its artwork in
# docs/assets should not have to copy two PNGs into the directory it ships, where
# they would ride along into the APK's www assets for no reason.
FG_NAMES = ("icon-adaptive-foreground.png", "docs/icon-adaptive-foreground.png",
            "assets/icon-adaptive-foreground.png", "../assets/icon-adaptive-foreground.png",
            "../icon-adaptive-foreground.png")
BG_NAMES = ("icon-adaptive-background.png", "docs/icon-adaptive-background.png",
            "assets/icon-adaptive-background.png", "../assets/icon-adaptive-background.png",
            "../icon-adaptive-background.png")

ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@mipmap/ic_launcher_background" />
    <foreground android:drawable="@mipmap/ic_launcher_foreground" />
</adaptive-icon>
"""


def find(app_dir: str, names: tuple[str, ...]) -> str | None:
    for n in names:
        p = os.path.join(app_dir, n)
        if os.path.isfile(p):
            return p
    return None


def dominant_colour(img: Image.Image) -> tuple[int, int, int]:
    """The most common colour that is not transparent, ignoring near-white/near-black."""
    rgba = img.convert("RGBA").resize((64, 64), Image.LANCZOS)
    counts: Counter[tuple[int, int, int]] = Counter()
    for r, g, b, a in rgba.getdata():
        if a < 200:
            continue
        if (r, g, b) in ((255, 255, 255), (0, 0, 0)):
            continue
        counts[(r // 8 * 8, g // 8 * 8, b // 8 * 8)] += 1
    if not counts:
        return (225, 29, 72)          # the estate's crimson, as a last resort
    return counts.most_common(1)[0][0]


def centred(art: Image.Image, canvas: int, ratio: float) -> Image.Image:
    """Place `art` on a transparent square canvas at `ratio` of its width."""
    art = art.convert("RGBA")
    side = max(1, int(canvas * ratio))
    scale = min(side / art.width, side / art.height)
    art = art.resize((max(1, int(art.width * scale)), max(1, int(art.height * scale))), Image.LANCZOS)
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.paste(art, ((canvas - art.width) // 2, (canvas - art.height) // 2), art)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, help="the app directory (app_src)")
    ap.add_argument("--res", required=True, help="the APK project's res directory")
    args = ap.parse_args()

    if not os.path.isdir(args.app):
        print(f"no app directory at {args.app}", file=sys.stderr)
        return 2

    icon_path = find(args.app, ICON_NAMES)
    fg_path = find(args.app, FG_NAMES)
    bg_path = find(args.app, BG_NAMES)

    if not icon_path and not fg_path:
        print("no icon in the app directory — nothing to make adaptive", file=sys.stderr)
        return 1

    base = Image.open(icon_path) if icon_path else Image.open(fg_path)

    if fg_path:
        foreground = Image.open(fg_path).convert("RGBA")
        # a supplied foreground is already drawn for the safe zone
        fg_ratio = 1.0
    else:
        foreground = base
        fg_ratio = 0.66

    if bg_path:
        background = Image.open(bg_path).convert("RGB")
    else:
        background = Image.new("RGB", (512, 512), dominant_colour(base))

    made = []
    for density, size in DENSITIES.items():
        folder = os.path.join(args.res, f"mipmap-{density}")
        os.makedirs(folder, exist_ok=True)

        fg = centred(foreground, size, fg_ratio)
        fg.save(os.path.join(folder, "ic_launcher_foreground.png"))
        made.append(f"{folder}/ic_launcher_foreground.png")

        bg = background.resize((size, size), Image.LANCZOS)
        bg.save(os.path.join(folder, "ic_launcher_background.png"))
        made.append(f"{folder}/ic_launcher_background.png")

    anydpi = os.path.join(args.res, "mipmap-anydpi-v26")
    os.makedirs(anydpi, exist_ok=True)
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        with open(os.path.join(anydpi, name), "w", encoding="utf-8") as fh:
            fh.write(ADAPTIVE_XML)
        made.append(f"{anydpi}/{name}")

    print(f"adaptive icon: {len(made)} files in {args.res}")
    print(f"  foreground from {fg_path or icon_path}")
    bg_from = bg_path if bg_path else "the icon's dominant colour"
    print(f"  background from {bg_from}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
