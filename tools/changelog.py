#!/usr/bin/env python3
"""rule-changelog — the CONSUMER.

A changelog is written WITH the change, not reconstructed later. Each repo carries
a `changes/` directory holding one small file per change; this consumer reads the
pending files, bumps `VERSION`, prepends a dated section to `CHANGELOG.md`, and
deletes what it consumed.

The mechanism is Changesets' (MIT) - the IDEA, not the tool. Changesets is a Node
monorepo tool; we are zero-dependency across many separate repos, so each repo
versions on its own and the mechanism is reimplemented here in about a hundred
lines.

Four things this buys, all of them concrete:
  * we SELL this - a buyer asks what changed in a version, and now there is an answer
  * the store's blog posts updates - this is their source
  * support - "which version has this bug?" becomes answerable
  * the release record - PROGRESS.log records activity, not releases

Guarantees:
  * IDEMPOTENT. No pending files means no change: no VERSION bump, no CHANGELOG
    edit, no commit. That is what stops the workflow re-triggering itself, on top
    of the `[skip ci]` on the commit.
  * The consumer is the ONLY thing that writes CHANGELOG.md. Do not edit it by
    hand, and do not let a second mechanism near it.
  * No pending files means no empty release.

File format in changes/ - YAML front matter, then the note:

    ---
    bump: patch
    ---

    Fixed the crash when a note contained an apostrophe.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

ORDER = {"patch": 1, "minor": 2, "major": 3}


def parse_change(p: Path) -> tuple[str, str]:
    """Return (bump, note). Defaults to patch; a bad bump is treated as patch."""
    text = p.read_text(encoding="utf-8")
    bump = "patch"
    body = text
    m = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        head, body = m.group(1), m.group(2)
        for line in head.splitlines():
            k, _, v = line.partition(":")
            if k.strip().lower() == "bump":
                v = v.strip().lower()
                if v in ORDER:
                    bump = v
    note = " ".join(body.split()).strip() or p.stem.replace("-", " ")
    return bump, note


def read_version(d: Path) -> str:
    f = d / "VERSION"
    if f.exists():
        v = f.read_text(encoding="utf-8").strip()
        if re.fullmatch(r"\d+\.\d+\.\d+", v):
            return v
    return "0.0.0"


def bump_version(v: str, kind: str) -> str:
    major, minor, patch = (int(x) for x in v.split("."))
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    d = Path(os.environ.get("CHANGELOG_DIR", ".")).resolve()
    changes = d / "changes"
    if not changes.is_dir():
        print("no changes/ directory - nothing to consume")
        return 0

    pending = sorted(p for p in changes.glob("*.md") if p.name.lower() != "readme.md")
    pending = [p for p in pending if p.is_file()]
    if not pending:
        print("no pending changes - the changelog does not change")
        return 0

    entries = [parse_change(p) for p in pending]
    kind = max((b for b, _ in entries), key=lambda b: ORDER[b])
    old = read_version(d)
    new = bump_version(old, kind)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")

    section = [f"## {new} — {today}", ""]
    for _, note in entries:
        section.append(f"- {note}")
    section.append("")

    cl = d / "CHANGELOG.md"
    if cl.exists():
        head, _, rest = cl.read_text(encoding="utf-8").partition("\n## ")
        new_cl = head.rstrip("\n") + "\n\n" + "\n".join(section) + ("\n## " + rest if rest else "")
    else:
        new_cl = (f"# Changelog — {d.name}\n\nNewest first. Generated from `changes/`;\n"
                  "do not edit by hand.\n\n" + "\n".join(section))

    (d / "VERSION").write_text(new + "\n", encoding="utf-8")
    cl.write_text(new_cl, encoding="utf-8")
    # the release notes are the section itself - a changelog gives a release its
    # TAG and its PUBLISHED NOTES, which is what a buyer, a store page or a blog
    # post actually links to
    (d / ".release-notes.md").write_text("\n".join(section), encoding="utf-8")
    for p in pending:
        p.unlink()

    print(f"{old} -> {new} ({kind}); consumed {len(pending)} change file(s)")
    for _, note in entries:
        print(f"  - {note}")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"version={new}\n")
            fh.write(f"previous={old}\n")
            fh.write(f"bump={kind}\n")
            fh.write(f"released=true\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
