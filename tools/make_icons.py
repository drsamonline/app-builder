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


# --------------------------------------------------------------------------- #
# Glyphs - chosen from the app's own name and description
#
# A new app used to fall back to two initials on a coloured square. That is what
# you get when nobody looked at the app, and it is why 36 repos shipped the same
# tile. Each glyph below is drawn from primitives on a 48x48 grid, so it renders
# at any size and needs nothing but Pillow.
# --------------------------------------------------------------------------- #
# primitives: ("r",x,y,w,h,radius) ("c",cx,cy,r) ("l",x1,y1,x2,y2)
#             ("pl",[(x,y),...])   ("poly",[(x,y),...])
GLYPHS = {
    "calendar": [("r", 11, 14, 26, 24, 3), ("l", 11, 21, 37, 21), ("l", 18, 10, 18, 17),
                 ("l", 30, 10, 30, 17), ("c", 19, 28, 2), ("c", 27, 28, 2)],
    "envelope": [("r", 9, 14, 30, 21, 3), ("pl", [(10, 16), (24, 27), (38, 16)]), ("l", 24, 27, 24, 33)],
    "lock": [("r", 13, 22, 22, 17, 3), ("pl", [(18, 22), (18, 17), (19, 14), (24, 12), (29, 14), (30, 17), (30, 22)]),
             ("c", 24, 30, 2)],
    "book": [("r", 12, 11, 18, 26, 3), ("l", 17, 11, 17, 37), ("l", 24, 20, 29, 20), ("l", 24, 26, 29, 26)],
    "receipt": [("poly", [(14, 10), (34, 10), (34, 38), (29, 35), (24, 38), (19, 35), (14, 38)]),
                ("l", 19, 19, 29, 19), ("l", 19, 25, 29, 25)],
    "search": [("c", 22, 21, 9), ("l", 29, 28, 38, 37)],
    "pulse": [("pl", [(8, 25), (15, 25), (18, 16), (23, 34), (27, 22), (30, 25), (40, 25)])],
    "wave": [("pl", [(8, 24), (12, 15), (16, 33), (20, 15), (24, 33), (28, 15), (32, 33), (36, 15), (40, 24)])],
    "grid": [("r", 10, 10, 11, 11, 2), ("r", 27, 10, 11, 11, 2), ("r", 10, 27, 11, 11, 2), ("r", 27, 27, 11, 11, 2)],
    "city": [("poly", [(9, 38), (9, 24), (18, 24), (18, 38)]), ("poly", [(18, 38), (18, 15), (29, 15), (29, 38)]),
             ("poly", [(29, 38), (29, 28), (39, 28), (39, 38)]), ("l", 9, 38, 39, 38)],
    "note": [("c", 18, 32, 5), ("l", 23, 32, 23, 13), ("l", 23, 13, 35, 10), ("l", 35, 10, 35, 29), ("c", 30, 29, 5)],
    "bolt": [("poly", [(27, 8), (14, 27), (22, 27), (19, 40), (34, 20), (25, 20)])],
    "crosshair": [("c", 24, 24, 11), ("l", 24, 7, 24, 14), ("l", 24, 34, 24, 41), ("l", 7, 24, 14, 24), ("l", 34, 24, 41, 24)],
    "cross": [("poly", [(20, 12), (28, 12), (28, 20), (36, 20), (36, 28), (28, 28), (28, 36), (20, 36), (20, 28), (12, 28), (12, 20), (20, 20)])],
    "joystick": [("r", 12, 28, 24, 10, 5), ("l", 24, 28, 24, 16), ("c", 24, 13, 4)],
    "network": [("c", 24, 13, 4), ("c", 13, 33, 4), ("c", 35, 33, 4), ("l", 21, 17, 16, 29), ("l", 27, 17, 32, 29), ("l", 17, 33, 31, 33)],
    "transfer": [("pl", [(10, 18), (32, 18)]), ("pl", [(26, 12), (32, 18), (26, 24)]),
                 ("pl", [(38, 30), (16, 30)]), ("pl", [(22, 24), (16, 30), (22, 36)])],
    "camera": [("poly", [(10, 17), (16, 17), (19, 13), (29, 13), (32, 17), (38, 17), (38, 37), (10, 37)]), ("c", 24, 27, 6)],
    "prism": [("poly", [(24, 10), (40, 38), (8, 38)]), ("l", 24, 10, 24, 38), ("l", 14, 30, 34, 22)],
    "flag": [("l", 14, 40, 14, 10), ("poly", [(14, 12), (32, 12), (28, 19), (32, 26), (14, 26)])],
    "quill": [("poly", [(34, 12), (16, 26), (12, 34), (20, 30), (34, 12)]), ("l", 14, 34, 22, 26)],
    "cup": [("poly", [(12, 16), (34, 16), (32, 34), (14, 34)]), ("pl", [(34, 20), (37, 20), (39, 25), (37, 30), (34, 30)]), ("l", 11, 39, 37, 39)],
    "terminal": [("r", 9, 12, 30, 24, 3), ("pl", [(15, 21), (20, 25), (15, 29)]), ("l", 25, 30, 33, 30)],
    "pen": [("poly", [(12, 36), (15, 28), (33, 10), (38, 15), (20, 33)]), ("l", 30, 13, 35, 18)],
    "brain": [("c", 19, 24, 9), ("c", 29, 24, 9), ("l", 24, 15, 24, 33)],
    "hand": [("poly", [(16, 26), (16, 16), (19, 13), (22, 16), (22, 24), (22, 13), (25, 10), (28, 13), (28, 24),
                       (28, 18), (31, 15), (34, 18), (34, 30), (30, 38), (20, 38), (13, 31)])],
    "book-open": [("pl", [(24, 15), (12, 12), (12, 34), (24, 37)]), ("pl", [(24, 15), (36, 12), (36, 34), (24, 37)]),
                  ("l", 24, 15, 24, 37)],
}

# first match wins: the earlier an entry, the more specific the words
KEYWORDS = [
    (("invoice", "billing", "bill", "gst", "receipt", "account"), "receipt", "#059669"),
    (("calendar", "today", "daily", "streak", "planner", "habit"), "calendar", "#16a34a"),
    (("note", "seal", "secret", "vault", "strongbox", "passphrase"), "envelope", "#4f46e5"),
    (("encrypt", "lock", "pin", "protect", "cipher", "secure"), "lock", "#b91c1c"),
    (("pdf", "document", "doc"), "book", "#be123c"),
    (("repertory", "rubric", "materia", "remedy", "homeopath", "kent", "boericke"), "search", "#0f766e"),
    (("book", "read", "chapter", "study", "learn"), "book-open", "#15803d"),
    (("health", "bmi", "bmr", "tdee", "clinical", "medical", "dose", "pulse"), "pulse", "#0d9488"),
    (("first", "aid", "emergency", "triage", "injur"), "cross", "#dc2626"),
    (("sound", "audio", "music", "ambient", "mixer", "synth", "wave"), "wave", "#0891b2"),
    (("dance", "rhythm", "beat", "song", "symphony", "melody"), "note", "#db2777"),
    (("poet", "poem", "rhyme", "metre", "verse", "write", "quill"), "quill", "#e11d48"),
    (("game", "play", "arcade", "rpg", "quest", "adventure"), "joystick", "#ec4899"),
    (("shooter", "strike", "gun", "fight", "combat", "arena"), "crosshair", "#f97316"),
    (("runner", "speed", "fast", "blink", "rapid", "instant"), "bolt", "#06b6d4"),
    (("city", "build", "colony", "idle", "empire", "settle"), "city", "#475569"),
    (("transfer", "share", "send", "sync", "transport"), "transfer", "#0e7490"),
    (("camera", "scan", "qr", "photo", "code", "optical", "prism", "light"), "camera", "#d97706"),
    (("lan", "room", "canteen", "wifi", "network", "share", "board", "whiteboard"), "network", "#ea580c"),
    (("panchang", "astro", "almanac", "moon", "sun", "tithi", "nakshatra"), "prism", "#ea580c"),
    (("base", "unit", "convert", "timezone", "number", "grid"), "grid", "#2563eb"),
    (("memory", "mnemo", "brain", "recall", "flash", "revis"), "brain", "#9333ea"),
    (("skin", "hand", "derma", "track"), "hand", "#c2410c"),
    (("console", "terminal", "forge", "cli", "tool"), "terminal", "#92400e"),
    (("companion", "book", "guide"), "book", "#7c3aed"),
]

# fallback colours, picked by name so an unnamed app is still stable and distinct
PALETTE = ["#16a34a", "#0891b2", "#4f46e5", "#b45309", "#be123c",
           "#0f766e", "#7c3aed", "#c2410c", "#2563eb", "#db2777"]


def pick_glyph(name, description=""):
    """A glyph that means something, from the app's own words. None if nothing fits."""
    text = ("%s %s" % (name or "", description or "")).lower().replace("-", " ")
    for words, glyph, colour in KEYWORDS:
        if any(w in text for w in words):
            return glyph, colour
    return None, PALETTE[sum(bytearray((name or "app").encode())) % len(PALETTE)]


def draw_glyph(glyph, colour, size=512):
    """Render a glyph on a rounded tile, drawn at 8x then downsampled for clean edges."""
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.23), fill=colour)
    k = S / 48.0
    w = max(2, int(2.4 * k))
    for op in GLYPHS[glyph]:
        kind = op[0]
        if kind == "r":
            _, x, y, rw, rh, rad = op
            d.rounded_rectangle([x * k, y * k, (x + rw) * k, (y + rh) * k],
                                radius=int(rad * k), outline="white", width=w)
        elif kind == "c":
            _, cx, cy, r = op
            d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k],
                      fill="white" if r <= 2.6 else None,
                      outline=None if r <= 2.6 else "white", width=None if r <= 2.6 else w)
        elif kind == "l":
            _, x1, y1, x2, y2 = op
            d.line([x1 * k, y1 * k, x2 * k, y2 * k], fill="white", width=w, joint="curve")
        elif kind in ("pl", "poly"):
            pts = [(px * k, py * k) for px, py in op[1]]
            if kind == "poly":
                d.polygon(pts, outline="white", width=w)
            else:
                d.line(pts, fill="white", width=w, joint="curve")
    return img.resize((size, size), Image.LANCZOS)


def load_icon(app_dir, name):
    src = find_source(app_dir)
    if src:
        print("icon source: %s" % src, flush=True)
        img = Image.open(src).convert("RGBA")
        side = max(img.size)
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
        return square
    # No artwork. Rather than two initials, look at what the app says about itself:
    # its landing page title and description, plus its name. A new app scaffolded
    # by Forge therefore gets a glyph that means something without anyone drawing
    # anything, which is the whole point of putting this in the shared workflow.
    desc = ""
    page = os.path.join(app_dir, "docs", "index.html")
    try:
        with open(page, encoding="utf-8", errors="replace") as fh:
            html = fh.read(4000)
        import re as _re
        m = _re.search(r"<title[^>]*>([^<]{0,160})", html, _re.I)
        if m:
            desc += " " + m.group(1)
        m = _re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']{0,200})', html, _re.I)
        if m:
            desc += " " + m.group(1)
    except Exception:
        pass

    glyph, colour = pick_glyph(name, desc)
    if glyph:
        print("icon source: none - drawing the '%s' glyph (matched from the app's own words)" % glyph,
              flush=True)
        return draw_glyph(glyph, colour, 512)

    print("icon source: none and nothing matched - drawing a monogram tile", flush=True)
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
