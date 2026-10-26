#!/usr/bin/env python3
"""retrofit-parity — refuse a retrofit that makes the app weaker.

THE PROBLEM THIS SOLVES, in the words of the run that created it:

    A retrofit on read-live-transform-app wired export-kit into the page - correct -
    and then DELETED the guarded fallback that had been doing every export, because
    the page had never loaded the kit. It also added a green test asserting the
    fallback was gone. Tests passing was the proof, and the tests had been edited.

PROMPTS/retrofit.md says "keep the repo's own public API so its tests still pass".
A test can be changed. A capability cannot be argued with: either the app can still
do the thing, or it cannot. This compares the app before and after and fails on any
REMOVAL.

What it checks, in order of what has actually cost time here:

  1. DATA      every <script type="application/json"> block still parses, and the
               parsed content is unchanged. (b7cdb158 left two unescaped quotes in
               the book JSON; JSON.parse threw and the whole app script never ran.)
  2. FALLBACK  a call guarded by `if (window.X && ...)` must not become bare. That
               guard is what lets the app work with no kit loaded.
  3. STANDALONE a kit global used unguarded must be present IN the page - inlined or
               by a script src. Otherwise the app only works on the author's disk.
  4. API       no public function name and no element id may disappear.

Additions are always fine. This tool never fails a change that only adds.

Usage:
  python3 tools/retrofit-parity.py BEFORE.html AFTER.html
  python3 tools/retrofit-parity.py --git REPO_DIR [--ref-before REF] [--ref-after REF]
  python3 tools/retrofit-parity.py BEFORE AFTER --json

Exit code 0 = nothing removed. 1 = a capability was removed; do not merge.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# globals the estate's kits publish. A bare reference to one of these means the app
# needs the kit to be present; a guarded reference means it can survive without it.
KIT_GLOBALS = ["Export", "Loom", "WebKit"]
# a marker string each kit carries in its own source, so an inlined copy is provable
KIT_MARKERS = {
    "Export": "export-kit",
    "Loom": "web-kit",
    "WebKit": "web-kit",
}

JSON_BLOCK = re.compile(
    r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', re.S)
FUNCTION = re.compile(r'function\s+([A-Za-z_$][\w$]*)\s*\(')
ELEMENT_ID = re.compile(r'\bid=["\']([\w-]+)["\']')
GUARDED = re.compile(r'if\s*\(\s*window\.(\w+)\s*&&')
SCRIPT_SRC = re.compile(r'<script[^>]*\bsrc=["\']([^"\']+)["\']')


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def surface(html: str) -> dict:
    """Everything about the app that a retrofit could quietly take away."""
    json_blocks = []
    for raw in JSON_BLOCK.findall(html):
        try:
            json_blocks.append(("ok", json.loads(raw)))
        except Exception as exc:                                   # noqa: BLE001
            json_blocks.append(("broken", f"{type(exc).__name__}: {exc}"))

    guarded = {}
    for g in GUARDED.findall(html):
        guarded[g] = guarded.get(g, 0) + 1

    srcs = SCRIPT_SRC.findall(html)
    # "inlined" must mean the kit's CODE is in the page. A bare substring test is
    # wrong here: `<script src="export-kit.js">` contains "export-kit" too, so an
    # external kit counted as inlined and the standalone check went quiet.
    inlined = {}
    for g in KIT_GLOBALS:
        external = any(KIT_MARKERS[g] in s for s in srcs)
        inlined[g] = (KIT_MARKERS[g] in html) and not external

    # a global is "available" if its code travels with the page, inlined or by src.
    # A kit loaded as a sibling file is available; whether that satisfies the
    # single-file promise is a separate question this tool does not police.
    available = {g: inlined[g] or any(KIT_MARKERS[g] in s for s in srcs) for g in KIT_GLOBALS}

    # a call is "bare" when the global is used, never guarded, and the kit is absent
    bare = {}
    for g in KIT_GLOBALS:
        calls = len(re.findall(r'(?<![\w$.])' + g + r'\s*\.\s*\w+\s*\(', html))
        if calls and not guarded.get(g) and not available[g]:
            bare[g] = calls

    return {
        "functions": set(FUNCTION.findall(html)),
        "ids": set(ELEMENT_ID.findall(html)),
        "json": json_blocks,
        "guarded": guarded,
        "script_src": srcs,
        "inlined": inlined,
        "available": available,
        "bare": bare,
    }


def compare(before: dict, after: dict, allow_data_change: bool = False):
    """Return (reasons this must not merge, warnings). Empty first list = clean."""
    bad: list[str] = []
    warn: list[str] = []

    # 1. the app's data must still parse, and must not have been edited
    b_json = [d for s, d in before["json"] if s == "ok"]
    for i, (status, data) in enumerate(after["json"]):
        if status != "ok":
            bad.append(f"DATA: embedded JSON block {i} no longer parses — {data}. "
                       "The whole app script dies on this.")
    a_json = [d for s, d in after["json"] if s == "ok"]
    if len(a_json) == len(b_json):
        for i, (b, a) in enumerate(zip(b_json, a_json)):
            if b != a:
                msg = (f"DATA: embedded JSON block {i} changed content "
                       f"({len(json.dumps(b))} -> {len(json.dumps(a))} chars).")
                # a retrofit must not edit the app's data; a CONTENT change may be
                # legitimate (a new chapter), so CI may downgrade it to a warning.
                # A block that no longer PARSES is always fatal - that is the one
                # that kills the whole app script.
                (warn if allow_data_change else bad).append(
                    msg + (" (allowed by --allow-data-change)" if allow_data_change
                           else " A retrofit must not edit the app's data."))

    # 2. a guard that was there must not be gone
    for g, n in before["guarded"].items():
        if after["guarded"].get(g, 0) < n:
            bad.append(
                f"FALLBACK: `if (window.{g} && ...)` guarded {n} call site(s) before, "
                f"{after['guarded'].get(g, 0)} after. That guard is what lets the app "
                "work with no kit loaded — it is a capability, not clutter.")

    # 3. the kit must still be reachable. Two shapes, both real losses:
    #    - the kit was available and the change took it away
    #    - the code calls a kit that is not there at all
    for g in KIT_GLOBALS:
        was, now = before["available"].get(g, False), after["available"].get(g, False)
        if was and not now:
            bad.append(f"STANDALONE: {g} was available to the page before and is gone "
                       "after — the kit is no longer loaded or inlined.")
        if after["bare"].get(g):
            bad.append(f"STANDALONE: {after['bare'][g]} `{g}.` call(s) with no guard "
                       f"and no {g} in the page or its scripts — that call cannot work.")

    # 4. the public surface
    for f in sorted(before["functions"] - after["functions"]):
        bad.append(f"API: function `{f}()` was removed.")
    for i in sorted(before["ids"] - after["ids"]):
        bad.append(f"API: element id `{i}` was removed.")

    return bad, warn


def from_git(repo: str, ref_before: str, ref_after: str, path: str) -> tuple[str, str]:
    def show(ref: str) -> str:
        return subprocess.run(["git", "-C", repo, "show", f"{ref}:{path}"],
                              capture_output=True, text=True, check=True).stdout
    return show(ref_before), show(ref_after)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fail a retrofit that removes a capability.")
    ap.add_argument("before", nargs="?", help="path to the app HTML before the change")
    ap.add_argument("after", nargs="?", help="path to the app HTML after the change")
    ap.add_argument("--git", metavar="REPO", help="compare two refs of a repo instead")
    ap.add_argument("--ref-before", default="HEAD~1")
    ap.add_argument("--ref-after", default="HEAD")
    ap.add_argument("--path", default="index.html")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--allow-data-change", action="store_true",
                    help="warn, rather than fail, when an embedded JSON block's CONTENT "
                         "changed (a new chapter). A block that stops parsing still fails.")
    args = ap.parse_args()

    if args.git:
        b, a = from_git(args.git, args.ref_before, args.ref_after, args.path)
        label = f"{args.git} {args.ref_before}..{args.ref_after}:{args.path}"
    elif args.before and args.after:
        b, a = read(args.before), read(args.after)
        label = f"{args.before} -> {args.after}"
    else:
        ap.error("give BEFORE AFTER, or --git REPO")

    before, after = surface(b), surface(a)
    bad, warn = compare(before, after, args.allow_data_change)

    added = (sorted(after["functions"] - before["functions"])
             + ["id:" + i for i in sorted(after["ids"] - before["ids"])])

    if args.json:
        print(json.dumps({"label": label, "ok": not bad, "removed": bad,
                          "warnings": warn, "added": added}, indent=2))
    else:
        print(f"retrofit-parity: {label}")
        print(f"  functions {len(before['functions'])} -> {len(after['functions'])}"
              f"   ids {len(before['ids'])} -> {len(after['ids'])}"
              f"   guarded {before['guarded']} -> {after['guarded']}"
              f"   json blocks {len(before['json'])} -> {len(after['json'])}")
        if added:
            print(f"  added (fine): {', '.join(added[:8])}"
                  + (" …" if len(added) > 8 else ""))
        for w in warn:
            print("  ! " + w)
        if bad:
            print(f"\nREFUSED — {len(bad)} capability removal(s):")
            for r in bad:
                print("  ✗ " + r)
            print("\nA retrofit must leave the app able to do everything it could do "
                  "before. Fix the change, or argue it in the PR — do not merge this.")
        else:
            print("\nOK — nothing removed.")

    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
