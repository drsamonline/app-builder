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


def _days(iso: str | None) -> float | None:
    if not iso or NOW is None:
        return None
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except Exception:
        return None
    return (NOW - t).total_seconds() / 86400


def score(r: dict) -> dict:
    """The heuristic score, broken out so a UI can show WHY a repo ranks where it does."""
    lic = (r.get("license") or "").lower()
    pushed, created = _days(r.get("pushed_at") or r.get("pushed")), _days(r.get("created_at") or r.get("created"))
    releases = int(r.get("releases") or 0)
    rel_age = _days(r.get("latest_release_at") or r.get("released_at"))

    aspects = {
        "homepage and description": bool(r.get("homepage")) and bool(r.get("description")),
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
        "stars": lg(r.get("stars") or r.get("stargazers_count")),
        "forks": lg(r.get("forks") or r.get("forks_count")),
        "watchers": lg(r.get("watchers") or r.get("subscribers_count")) - 1,
        "commits": lg(r.get("commits")) - 1,
        "contributors": lg(r.get("contributors")) - 1,
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
    return {"delta": now - int(prev), "previous": int(prev), "window_days": window_days, "basis": "snapshot"}


def build(repos: list[dict], history: list[dict]) -> dict:
    rows = []
    for r in repos:
        if not isinstance(r, dict):
            continue
        name = r.get("name") or r.get("key")
        if not name:
            continue
        s = score(r)
        stars = int(r.get("stars") or r.get("stargazers_count") or 0)
        rows.append({
            "name": name,
            "stars": stars,
            "views": int(r.get("views") or 0),
            "clones": int(r.get("clones") or 0),
            "quality": s["quality"],
            "activity": activity(r),
            "aspects": s["aspects"],
            "movement": movement(name, stars, history),
