#!/usr/bin/env python3
"""kit-guard — refuse a kit that is retrofitted into a repository.

THE RULE, in the owner's words: kits are one-way. A kit LEARNS from repositories
(harvest, app -> kit) and is USED to build new apps. A kit is never retrofitted into a
repository - not an existing one, not a new one. There is no exception for a retrofit
that would be safe, additive or capability-preserving: the answer is no.

WHY THIS REPLACES THE PARITY GATE AS THE KIT GUARD. `retrofit-parity.py` asks whether a
retrofit was *damaging* - it passes anything that only adds. That permitted the thing the
rule forbids. This asks the only question that matters now: did a kit appear where one
was not before?

HOW A RETROFIT IS TOLD APART FROM A NEW APP. The distinguishing fact is not the kit, it
is the page. A new app brings its page and its kit in the same change, so the page is
NEW. A retrofit drops a kit into a page that was already shipping without it, so the page
is OLD. That is mechanical, it needs no judgement call, and it cannot be argued with:

  * a kit load added to a page that already existed  -> FAIL, a retrofit
  * a kit load on a page that is new in this change  -> pass, that is building new
  * a kit file added with no page loading it         -> FAIL, a kit with no consumer
  * anything REMOVED                                 -> pass, removals are always allowed

The last line matters: this tool must never make it harder to take a kit OUT. Removing a
retrofit is the repair this rule exists to make possible.

    python3 tools/kit-guard.py --base origin/main --root .
    python3 tools/kit-guard.py --self-test

Exit 0 when no kit was introduced, 1 when one was, 2 when the guard could not run (which
is not a pass - an unrun guard must never look like a green one).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

KIT_FILE = re.compile(r"-kit\.js$")
SKIP_DIRS = {".git", "node_modules", "vendor", "dist"}


# --------------------------------------------------------------------------- #
# Reading a page: which kits does it ask the browser to load?
# --------------------------------------------------------------------------- #
class _Scripts(HTMLParser):
    """The `src` of every <script> in a page.

    A real HTML parser rather than a regex, because a regex cannot tell a <script> tag
    from the text `<script>` inside a JS string - and this estate has an app whose whole
    script dies on exactly that confusion.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.srcs = []

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        for k, v in attrs:
            if k.lower() == "src" and v:
                self.srcs.append(v)


def kit_loads(html):
    """The basenames of the kits this page loads. `?v=2` and `#x` are not part of a name."""
    p = _Scripts()
    try:
        p.feed(html)
        p.close()
    except Exception:
        # A page we cannot parse is not a page we can clear; treat it as loading nothing
        # and let the capability check deal with it.
        pass
    out = set()
    for src in p.srcs:
        name = src.split("?")[0].split("#")[0].rstrip("/").split("/")[-1]
        if KIT_FILE.search(name):
            out.add(name)
    return out


# --------------------------------------------------------------------------- #
# The decision, kept pure so it can be tested without a repository
# --------------------------------------------------------------------------- #
def judge(before_pages, after_pages, before_kits, after_kits):
    """Every way this change introduced a kit. Empty list = the change is clean.

    before_pages / after_pages: {path: html}
    before_kits  / after_kits:  {path} of *-kit.js files in the repository
    """
    problems = []

    for page in sorted(set(before_pages) & set(after_pages)):
        added = kit_loads(after_pages[page]) - kit_loads(before_pages[page])
        for kit in sorted(added):
            problems.append(
                f"{page} now loads {kit}, and it did not before - a kit was retrofitted "
                f"into a page that already existed")

    new_pages = set(after_pages) - set(before_pages)
    added_files = set(after_kits) - set(before_kits)
    loaded = set()
    for html in after_pages.values():
        loaded |= kit_loads(html)
    for kit in sorted(added_files):
        if kit.rsplit("/", 1)[-1] not in loaded:
            problems.append(
                f"{kit} was added to the repository and no page loads it - a kit with no "
                f"consumer")

    return problems


# --------------------------------------------------------------------------- #
# Reading a repository at a commit
# --------------------------------------------------------------------------- #
def git(*args, root=".", check=True):
    r = subprocess.run(["git", "-C", root] + list(args),
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()[:300]}")
    return r


def files_at(ref, root="."):
    """Every tracked path at `ref` (or the working tree when ref is None)."""
    if ref is None:
        r = git("ls-files", root=root)
    else:
        r = git("ls-tree", "-r", "--name-only", ref, root=root)
    return [p for p in r.stdout.splitlines()
            if p and not (set(p.split("/")[:-1]) & SKIP_DIRS)]


def pages_at(ref, root=".", max_bytes=4_000_000, skipped=None):
    """{path: html} for every .html file at `ref`."""
    out = {}
    for path in files_at(ref, root):
        if not path.lower().endswith((".html", ".htm")):
            continue
        if ref is None:
            full = os.path.join(root, path)
            if not os.path.isfile(full) or os.path.getsize(full) > max_bytes:
                if skipped is not None:
                    skipped.append(path)
                continue
            out[path] = open(full, encoding="utf-8", errors="replace").read()
        else:
            r = git("show", f"{ref}:{path}", root=root, check=False)
            if r.returncode != 0 or len(r.stdout) > max_bytes:
                if skipped is not None:
                    skipped.append(path)
                continue
            out[path] = r.stdout
    return out


def kits_at(ref, root="."):
    return {p for p in files_at(ref, root) if KIT_FILE.search(p)}


def check(base, root=".", out=print):
    """Compare the working tree against `base`. Returns the exit code."""
    before_pages, before_skipped = {}, []
    after_pages, after_skipped = {}, []
    before_pages = pages_at(base, root, skipped=before_skipped)
    after_pages = pages_at(None, root, skipped=after_skipped)
    problems = judge(before_pages, after_pages, kits_at(base, root), kits_at(None, root))

    out(f"kit-guard: {len(before_pages)} page(s) at {base[:12]}, "
        f"{len(after_pages)} now, "
        f"{len(kits_at(base, root))} kit file(s) before, {len(kits_at(None, root))} now")

    # A page too large to read is a page we could not clear. Say so; do not imply a pass.
    unread = sorted(set(before_skipped) | set(after_skipped))
    if unread:
        out(f"kit-guard: WARNING {len(unread)} page(s) were too large to read and were "
            f"NOT checked: {', '.join(unread[:5])}")

    if not problems:
        out("kit-guard: OK - no kit was introduced by this change")
        return 0
    out("")
    for p in problems:
        out(f"  VIOLATION  {p}")
    out("")
    out("Kits are one-way: a kit learns from repositories and is used to build new apps. "
        "A kit is never retrofitted into a repository - not an existing one, not a new "
        "one. Remove the kit from the page, or build the app fresh on the kit.")
    return 1


# --------------------------------------------------------------------------- #
# --self-test: the cases this must catch AND the cases it must let pass
# --------------------------------------------------------------------------- #
def self_test():
    """A guard that cannot pass a legitimate change gets switched off, so both halves
    are tested - against a real git repository, not a fixture."""
    page = ("<html><body><h1>app</h1>"
            "<script src=\"app.js\"></script></body></html>")

    def page_with(*kits):
        tags = "".join(f'<script src="{k}"></script>' for k in kits)
        return f"<html><body><h1>app</h1>{tags}<script src=\"app.js\"></script></body></html>"

    cases = []

    # 1. a kit dropped into a page that already existed -> must fail
    cases.append(("a kit retrofitted into an existing page", True,
                  {"index.html": page},
                  {"index.html": page_with("export-kit.js")},
                  set(), set()))

    # 2. a new app that brings its page and its kit together -> must pass
    cases.append(("a new app built on a kit", False,
                  {"index.html": page},
                  {"index.html": page, "docs/play/index.html": page_with("web-kit.js")},
                  set(), {"docs/play/web-kit.js"}))

    # 3. a kit file added with nothing loading it -> must fail
    cases.append(("a kit file added with no consumer", True,
                  {"index.html": page},
                  {"index.html": page},
                  set(), {"export-kit.js"}))

    # 4. taking a kit OUT -> must pass. Removals are the repair, never the offence.
    cases.append(("a kit removed from an existing page", False,
                  {"index.html": page_with("export-kit.js")},
                  {"index.html": page},
                  {"export-kit.js"}, set()))

    # 5. an unrelated change -> must pass
    cases.append(("an edit that touches no kit", False,
                  {"index.html": page},
                  {"index.html": page.replace("app</h1>", "app v2</h1>")},
                  set(), set()))

    # 6. a second kit added to a page that already loaded one -> must fail
    cases.append(("a second kit added to a page that already had one", True,
                  {"index.html": page_with("web-kit.js")},
                  {"index.html": page_with("web-kit.js", "search-kit.js")},
                  {"web-kit.js"}, {"web-kit.js", "search-kit.js"}))

    # 7. the same kit, only re-ordered or versioned -> must pass
    cases.append(("a kit load re-ordered or version-bumped", False,
                  {"index.html": page_with("web-kit.js")},
                  {"index.html": page_with("web-kit.js?v=2")},
                  {"web-kit.js"}, {"web-kit.js"}))

    bad = 0
    for name, want_fail, before_p, after_p, before_k, after_k in cases:
        got = judge(before_p, after_p, before_k, after_k)
        ok = bool(got) == want_fail
        print(f"{'PASS' if ok else 'FAIL'}  {name}  ->  "
              f"{'refused' if got else 'allowed'} (wanted "
              f"{'refused' if want_fail else 'allowed'})")
        if not ok:
            bad += 1

    # and once through real git, so the plumbing is exercised, not just the decision
    with tempfile.TemporaryDirectory() as d:
        def run(*a):
            return subprocess.run(["git", "-C", d] + list(a), capture_output=True, text=True)
        run("init", "-q")
        run("config", "user.email", "t@t")
        run("config", "user.name", "t")
        open(os.path.join(d, "index.html"), "w").write(page)
        run("add", "-A"); run("commit", "-qm", "base")
        base = run("rev-parse", "HEAD").stdout.strip()
        ok = check(base, root=d, out=lambda *_: None) == 0
        print(f"{'PASS' if ok else 'FAIL'}  a real repository with no kit change  ->  allowed")
        bad += 0 if ok else 1

        open(os.path.join(d, "index.html"), "w").write(page_with("export-kit.js"))
        ok = check(base, root=d, out=lambda *_: None) == 1
        print(f"{'PASS' if ok else 'FAIL'}  a real repository with a retrofit  ->  refused")
        bad += 0 if ok else 1

    print(f"\n{len(cases) + 2} checks, {bad} failed")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Refuse a kit that is retrofitted into a repository.")
    ap.add_argument("--base", default="", help="the commit to compare against (e.g. origin/main)")
    ap.add_argument("--root", default=".", help="the repository root (default: .)")
    ap.add_argument("--max-bytes", type=int, default=4_000_000,
                    help="skip pages larger than this and say so (default 4 MB)")
    ap.add_argument("--self-test", action="store_true", help="test the guard both ways and exit")
    a = ap.parse_args(argv)

    if a.self_test:
        return self_test()
    if not a.base:
        print("kit-guard: --base is required (or --self-test). An unrun guard is not a pass.")
        return 2
    r = git("cat-file", "-e", f"{a.base}^{{commit}}", root=a.root, check=False)
    if r.returncode != 0:
        print(f"kit-guard: {a.base} is not a commit in this checkout - the guard could not run. "
              f"That is not a pass.")
        return 2
    return check(a.base, a.root)


if __name__ == "__main__":
    sys.exit(main())
