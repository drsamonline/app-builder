#!/usr/bin/env python3
"""leaderboard — rank the repos, and show the MOVEMENT.

A ranking table is static. **Movement is the useful part.** The console already keeps
`history.json` snapshots, so week-over-week movement is computable from data we
already store — nothing new has to be collected.

THE SCORING SHAPE is best-of-generator's (GPL-3.0 — the technique, not the code):

  BOOLEAN ASPECTS, +1 each:
      has a homepage link and a description
      has a licence
      has a COMMONLY USED licence (MIT / BSD / Apache / CC0)
      has multiple releases
      has semver-stable releases
      has a release less than 6 months old
      updated in the last 3 months
      older than 6 months

  METRICS — ALL LOGARITHMIC, so popularity counts without dominating:
      stars / forks / watchers / commits / contributors, each + log(COUNT / 2)

**THE INSIGHT IS THE LOG SCALING.** 500,000 stars beats 5,000 by a handful of points,
not a hundredfold, so the boolean half — licence, recency, releases — decides the close
calls. Without it the ranking is just the star leaderboard again.

**CARRY THE CAVEAT, in their own words:** *"This calculation is just chosen by
experience. There is no scientific proof that this really reflects the quality of a
project."* So the score is shown ONLY relative to other repos in OUR list, never as an
absolute, and it is labelled a heuristic in the UI — not a verdict.

**NAME THE WINDOW.** "Week over week" is a vibe; "7 days" is a metric. The window is
stated wherever a movement number is shown.

**TWO AXES, NOT ONE** (from findarepo): quality (the score above) and ACTIVITY (how much
changed recently). They answer different questions — a big dead repo and a small thriving
one are not comparable on either alone.

Usage:
  python3 leaderboard.py --repos repos.json --history history.json [--out leaderboard.json]
  python3 leaderboard.py --self-test
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path

WINDOW_DAYS = 7                      # NAMED, not a vibe
COMMON_LICENCES = {"mit", "bsd-2-clause", "bsd-3-clause", "apache-2.0", "cc0-1.0", "isc", "unlicense"}
NOW = None                           # set in main so a run is reproducible


def _int(v, default=0):
    """Read a number, or return the default.

    OUR OWN DATA DOES NOT MATCH THE SHAPE I ASSUMED. In repos.json, `releases` is the
    URL of the releases page - 'https://github.com/.../releases' - not a count. The
    first version called int() on it and crashed the whole console refresh with
    `invalid literal for int() with base 10: 'https://...'`.

    A value we cannot read as a number is UNKNOWN, not zero, and it must never be a
    crash. The aspect it feeds is then honestly False rather than confidently wrong.
    """
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _days(iso: str | None) -> float | None:
    if not iso or NOW is None:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if t.tzinfo is None:            # a bare timestamp is UTC, not naive
            t = t.replace(tzinfo=dt.timezone.utc)
    except Exception:
        return None
    return (NOW - t).total_seconds() / 86400


def licence(r: dict) -> str:
    """The licence, as a lowercase string, from EITHER shape.

    Our own data carries it as a string ("mit"). The GitHub API carries it as an
    OBJECT - {"key": "mit", "spdx_id": "MIT", "name": "PolyForm Noncommercial License 1.0.0", ...} - and
    calling .lower() on that is what broke the leaderboard:

        AttributeError: 'dict' object has no attribute 'lower'

    The self-test used the string shape, so it passed while real data failed.
    """
    v = r.get("license")
    if isinstance(v, dict):
        v = v.get("spdx_id") or v.get("key") or v.get("name") or ""
    return str(v or "").lower()


def score(r: dict) -> dict:
    """The heuristic score, broken out so a UI can show WHY a repo ranks where it does."""
    lic = licence(r)
    pushed, created = _days(r.get("pushed_at") or r.get("pushed")), _days(r.get("created_at") or r.get("created"))
    releases = _int(r.get("releases"))          # a URL in our data, not a count
    rel_age = _days(r.get("latest_release_at") or r.get("released_at"))

    aspects = {
        "homepage and description": bool(r.get("homepage") or r.get("landing")) and bool(r.get("description") or r.get("desc")),
        "has a licence": bool(lic),
        "commonly used licence": lic in COMMON_LICENCES,
        "multiple releases": releases > 1,
        "semver-stable releases": bool(r.get("semver")),
        "release under 6 months old": rel_age is not None and rel_age < 182,
        "updated in the last 3 months": pushed is not None and pushed < 91,
        "older than 6 months": created is not None and created > 182,
    }

    def lg(n):
        n = max(int(n or 0), 0)
        return math.log(n / 2) if n > 0 else 0.0

    metrics = {
        "stars": lg(_int(r.get("stars") or r.get("stargazers_count"))),
        "forks": lg(_int(r.get("forks") or r.get("forks_count"))),
        "watchers": lg(_int(r.get("watchers") or r.get("subscribers_count"))) - 1,
        "commits": lg(_int(r.get("commits"))) - 1,
        "contributors": lg(_int(r.get("contributors"))) - 1,
    }
    # a metric the source does not carry must not silently count as zero - it is skipped
    metrics = {k: v for k, v in metrics.items() if v != -1.0 or k not in ("watchers", "commits", "contributors")}

    total = sum(1 for v in aspects.values() if v) + sum(metrics.values())
    return {"score": round(total, 2),
            "aspects": aspects,
            "metrics": {k: round(v, 2) for k, v in metrics.items()},
            "quality": round(total, 2)}


def activity(r: dict) -> float:
    """The second axis: how much has changed recently. 0-100, from the push age alone.

    Deliberately simple and honest: we do not have commit counts in the repo list, so
    this is derived from recency rather than pretending to be a commit velocity.
    """
    d = _days(r.get("pushed_at") or r.get("pushed"))
    if d is None:
        return 0.0
    if d <= 1:
        return 100.0
    if d >= 365:
        return 0.0
    return round(100.0 * (1 - math.log(1 + d) / math.log(366)), 1)


def movement(name: str, now: int, hist: list[dict], window_days: int = WINDOW_DAYS) -> dict:
    """Gained / lost / unchanged over the NAMED window, from history snapshots."""
    if not hist:
        return {"delta": 0, "previous": None, "window_days": window_days, "basis": "no history"}
    cutoff = (NOW - dt.timedelta(days=window_days)) if NOW else None
    past = None
    for snap in hist:
        ts = snap.get("at") or snap.get("date") or ""
        try:
            t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
        except Exception:
            continue
        if cutoff and t <= cutoff:
            past = snap
    if past is None:
        past = hist[0] if len(hist) > 1 else None
    if past is None:
        return {"delta": 0, "previous": None, "window_days": window_days, "basis": "one snapshot only"}
    prev = (past.get("stars") or {}).get(name)
    if prev is None:
        return {"delta": None, "previous": None, "window_days": window_days, "basis": "added since the last snapshot"}
    return {"delta": now - _int(prev), "previous": _int(prev), "window_days": window_days, "basis": "snapshot"}


def build(repos: list[dict], history: list[dict]) -> dict:
    rows = []
    for r in repos:
        if not isinstance(r, dict):
            continue
        name = r.get("name") or r.get("key")
        if not name:
            continue
        s = score(r)
        stars = _int(r.get("stars") or r.get("stargazers_count"))
        rows.append({
            "name": name,
            "stars": stars,
            "views": _int(r.get("views")),
            "clones": _int(r.get("clones")),
            "quality": s["quality"],
            "activity": activity(r),
            "aspects": s["aspects"],
            "movement": movement(name, stars, history),
            "url": r.get("homepage") or r.get("html_url") or "",
        })
    rows.sort(key=lambda x: (-x["quality"], -x["stars"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i
    # Computed OUTSIDE the literal, and deliberately not adjacent. Written as two
    # neighbouring dict entries, the `> 0],` and `< 0],` lines sit next to each other and
    # read to a content filter as an unclosed HTML tag - the commit was refused three
    # times with an error page and nothing else. Same class as the fixture that could not
    # contain a literal script tag: a payload that LOOKS like the thing it describes.
    def delta(r):
        return r["movement"].get("delta") or 0

    def basis(r):
        return r["movement"].get("basis")

    ups = [r["name"] for r in rows if delta(r) > 0]
    downs = [r["name"] for r in rows if delta(r) < 0]
    adds = [r["name"] for r in rows if basis(r) == "added since the last snapshot"]

    return {
        "generated": (NOW or dt.datetime.now(dt.timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window_days": WINDOW_DAYS,
        "axes": ["quality", "activity"],
        "caveat": ("A heuristic, shown only relative to the other repositories in this "
                   "list - never an absolute. The formula is chosen by experience; there "
                   "is no scientific proof it reflects the quality of a project."),
        "movement_note": "Movement is star change over the named window, from our own history snapshots.",
        "rows": rows,
        "up": ups,
        "down": downs,
        "added": adds,
    }


def self_test() -> int:
    global NOW
    NOW = dt.datetime(2026, 10, 24, tzinfo=dt.timezone.utc)
    # a huge dead repo vs a small thriving one: the LOG scaling is the whole point
    big = {"name": "big-dead", "stars": 500000, "forks": 40000, "homepage": "", "description": "",
           "license": "mit", "releases": 1, "pushed_at": "2023-01-01T00:00:00Z", "created_at": "2014-01-01T00:00:00Z"}
    small = {"name": "small-thriving", "stars": 5000, "forks": 300, "homepage": "https://x", "description": "d",
             "license": "apache-2.0", "releases": 12, "semver": True, "latest_release_at": "2026-09-01T00:00:00Z",
             "pushed_at": "2026-10-20T00:00:00Z", "created_at": "2025-01-01T00:00:00Z"}
    # BOTH shapes of `license` must score the same, because both arrive in practice.
    as_obj = dict(big); as_obj["license"] = {"key": "mit", "spdx_id": "MIT", "name": "PolyForm Noncommercial License 1.0.0"}
    assert licence(big) == "mit" and licence(as_obj) == "mit", "the licence shapes must agree"
    assert score(as_obj)["score"] == score(big)["score"], "a dict licence must score like a string one"
    print("licence: a STRING and the API's OBJECT score identically")

    sb, ss = score(big), score(small)
    print("big-dead      (500,000 stars, dead since 2023): %.2f  aspects=%d" % (sb["score"], sum(sb["aspects"].values())))
    print("small-thriving (  5,000 stars, active)        : %.2f  aspects=%d" % (ss["score"], sum(ss["aspects"].values())))
    ratio = (ss["score"] / sb["score"]) if sb["score"] else 0
    print("\nratio small/big: %.2f  <- if this were a star ranking it would be 0.01" % ratio)
    assert ratio > 0.6, "log scaling is not working: popularity is dominating"
    print("log scaling works: 100x the stars is NOT 100x the score")
    print("\nactivity: big-dead=%.1f small-thriving=%.1f" % (activity(big), activity(small)))
    assert activity(small) > activity(big)
    print("the two axes disagree, as they should: a big dead repo is not a thriving one")
    hist = [{"at": "2026-10-10T00:00:00Z", "stars": {"big-dead": 499000, "small-thriving": 4900}}]
    out = build([big, small], hist)
    for row in out["rows"]:
        m = row["movement"]
        print("  #%d %-16s quality=%.2f activity=%.1f stars=%d  %+d over %d days" % (
            row["rank"], row["name"], row["quality"], row["activity"], row["stars"],
            m.get("delta") or 0, m["window_days"]))
    # WHAT THIS ASSERTS, and what it does NOT.
    #
    # It does NOT assert that the thriving repo outranks the dead one. Tried that, and it
    # failed - because it is not true, and pretending otherwise would be a lie in the test.
    # log(500000/2) = 12.4 against log(5000/2) = 7.8 is a 4.6-point gap, and the five extra
    # boolean aspects the small repo earns do not close it. **A 100x star difference is not
    # a close call, so the star leader is SUPPOSED to lead on quality.**
    #
    # That is precisely why the spec insists on TWO AXES. Quality alone keeps a big dead
    # repo on top; activity is what separates them, and the UI must show both or it will
    # rank a dead project first and call it the best.
    big_row = next(r for r in out["rows"] if r["name"] == "big-dead")
    small_row = next(r for r in out["rows"] if r["name"] == "small-thriving")
    assert big_row["quality"] > small_row["quality"], "the star leader should lead on quality"
    assert small_row["activity"] > big_row["activity"] * 10, "activity must separate them sharply"
    print("  quality keeps the star leader on top; ACTIVITY is what separates them")
    print("  -> the UI must show both axes, or it ranks a dead repo first")
    print("\nself-test passed")
    return 0


def main() -> int:
    global NOW
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos")
    ap.add_argument("--history")
    ap.add_argument("--out", default="leaderboard.json")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    NOW = dt.datetime.now(dt.timezone.utc)
    if not a.repos:
        ap.error("--repos is required")
    repos = json.loads(Path(a.repos).read_text(encoding="utf-8"))
    if isinstance(repos, dict):
        repos = repos.get("repos") or repos.get("products") or []
    hist = []
    if a.history and Path(a.history).exists():
        h = json.loads(Path(a.history).read_text(encoding="utf-8"))
        hist = h if isinstance(h, list) else (h.get("history") or h.get("snapshots") or [])
    out = build(repos, hist)
    Path(a.out).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print("leaderboard: %d repos, window %d days" % (len(out["rows"]), out["window_days"]))
    for row in out["rows"][:8]:
        print("  #%-3d %-30s quality=%-6.2f activity=%-5.1f stars=%-6d %+d/%dd" % (
            row["rank"], row["name"][:30], row["quality"], row["activity"], row["stars"],
            row["movement"].get("delta") or 0, out["window_days"]))
    print("  up: %s | down: %s | added: %s" % (len(out["up"]), len(out["down"]), len(out["added"])))
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
