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


