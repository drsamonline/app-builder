#!/usr/bin/env python3
"""Generate an app's release icons from one source image.

Looks in the app repo for, in order:

    docs/icon.png  assets/icon.png  icon.png
    docs/icon.svg  assets/icon.svg  icon.svg      (needs cairosvg)

If neither exists it draws a deterministic monogram tile from the app name, so a
build can never ship without an icon. That fallback is the point: forty repos
have no icon today, and a wrong-but-present icon beats the default Android robot
and the default PyInstaller logo.

Outputs, by flag:

    --ico out/icon.ico              a multi-size Windows icon, 16..256
    --res <src/main/res>            mipmap-{m,h,xh,xxh,xxxh}dpi/ic_launcher.png
                                    and ic_launcher_round.png

Usage:
    python make_icons.py --app app-repo/docs --name today-card --ico out/icon.ico
    python make_icons.py --app app-repo/docs --name today-card --res builder/apk/app/src/main/res
"""
import argparse
import colorsys
import hashlib
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]
MIPMAPS = {
    "mipmap-mdpi": 48,
    "mipmap-hdpi": 72,
    "mipmap-xhdpi": 96,
    "mipmap-xxhdpi": 144,
    "mipmap-xxxhdpi": 192,
}
CANDIDATES = ("docs/icon.png", "assets/icon.png", "icon.png",
              "docs/icon.jpg", "assets/icon.jpg", "icon.jpg")
SVG_CANDIDATES = ("docs/icon.svg", "assets/icon.svg", "icon.svg")


def find_source(app_dir):
    """The best available source image, or None."""
    for rel in CANDIDATES:
        p = os.path.join(app_dir, rel)
        if os.path.isfile(p):
            return p
    for rel in SVG_CANDIDATES:
        p = os.path.join(app_dir, rel)
        if not os.path.isfile(p):
            continue
        try:
            import cairosvg                                    # noqa: F401
            out = os.path.join(os.path.dirname(os.path.abspath(p)), ".icon-raster.png")
            cairosvg.svg2png(url=p, write_to=out, output_width=512, output_height=512)
            return out
        except Exception as exc:                               # noqa: BLE001
            print("note: %s found but could not be rasterised (%s)" % (rel, exc), flush=True)
    return None


def initials(name):
    words = [w for w in "".join(c if c.isalnum() else " " for c in name).split() if w]
    if not words:
        return "?"
    if len(words) == 1:
        w = words[0]
        return (w[:2] if len(w) > 1 else w).upper()
    return (words[0][0] + words[1][0]).upper()


def monogram(name, size=512):
    """A deterministic tile: same name always gives the same colour and letters."""
    digest = hashlib.sha256(name.lower().encode()).digest()
    hue = digest[0] / 255.0
    r, g, b = colorsys.hls_to_rgb(hue, 0.42, 0.55)
    bg = (int(r * 255), int(g * 255), int(b * 255), 255)

    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)
    text = initials(name)
    font = None
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "C:/Windows/Fonts/arialbd.ttf",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf"):
        if os.path.isfile(path):
            try:
                font = ImageFont.truetype(path, int(size * 0.42))
                break
            except Exception:                                  # noqa: BLE001
                pass
    if font is None:
        font = ImageFont.load_default()
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(((size - (box[2] - box[0])) / 2 - box[0],
               (size - (box[3] - box[1])) / 2 - box[1]),
              text, font=font, fill=(255, 255, 255, 255))
    return img


def load_icon(app_dir, name):
    src = find_source(app_dir)
    if src:
        print("icon source: %s" % src, flush=True)
        img = Image.open(src).convert("RGBA")
        side = max(img.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
        return square
    print("icon source: none - drawing a monogram tile from the app name", flush=True)
    return monogram(name)


def circular(img, size):
    """The same artwork, masked to a circle, for Android's round icon."""
    base = img.resize((size, size), Image.LANCZOS)
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    mask = mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


def write_ico(img, path):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.resize((256, 256), Image.LANCZOS).save(path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
    print("wrote %s (%d sizes)" % (path, len(ICO_SIZES)), flush=True)


def write_mipmaps(img, res_dir):
    for folder, size in MIPMAPS.items():
        out_dir = os.path.join(res_dir, folder)
        os.makedirs(out_dir, exist_ok=True)
        img.resize((size, size), Image.LANCZOS).save(os.path.join(out_dir, "ic_launcher.png"))
        circular(img, size).save(os.path.join(out_dir, "ic_launcher_round.png"))
        print("wrote %s/ic_launcher.png (%dpx) + round" % (folder, size), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True, help="path to the app repo (or its docs dir)")
    ap.add_argument("--name", required=True, help="app name, used for the monogram fallback")
    ap.add_argument("--ico", default="", help="write a Windows .ico here")
    ap.add_argument("--res", default="", help="write Android mipmaps into this res dir")
    args = ap.parse_args()

    if not (args.ico or args.res):
        sys.exit("nothing to do: pass --ico and/or --res")

    if not os.path.isdir(args.app):
        sys.exit("app path not found: %s" % args.app)

    img = load_icon(args.app, args.name)
    if args.ico:
        write_ico(img, args.ico)
    if args.res:
        write_mipmaps(img, args.res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
