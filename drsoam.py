#!/usr/bin/env python3
"""drsoam.py — ONE shared module for every drsamonline refresh.

It fetches the repo list once and emits any of four outputs:

    python3 drsoam.py dashboard    # -> data.json                 (the console)
    python3 drsoam.py store        # -> docs/data/products.json   (the store)
    python3 drsoam.py posts        # -> docs/data/posts.json      (the blog)
    python3 drsoam.py plan         # -> rewrites the plan's status block

The point: **one exclusion list**, so the four outputs can never drift apart.
Previously each generator carried its own copy of the meta-repo list, and they
diverged (Matneo was excluded in one and not another).

Dependency-free. Set GH_TOKEN to raise the API rate limit.

PolyForm Noncommercial License 1.0.0. (c) 2026 Dr Sohil Momin.
"""
import base64, json, os, re, sys, urllib.request, urllib.parse, datetime
from collections import Counter

OWNER = "drsamonline"

# ---- the ONE exclusion list -------------------------------------------------
# Not products: the tooling, the storefront itself, and the kits.
META = {
    "drsamonline", "drsamonline.github.io", "app-builder", "skills", "profile-kit",
    "forge", "registry", "knowledge", "dashboard", "Matneo",
}
KITS = {
    "web-kit", "optical-kit", "crypto-kit", "compress-kit", "lan-kit", "game-kit",
    "astro-kit", "repertory-kit", "search-kit", "srs-kit", "book-kit", "case-kit",
    "frame-kit", "export-kit",
}

HOMEOPATHY = {"kent-repertory-explorer", "boericke-repertory", "remedy-relationship-explorer",
              "MATERIA-MEDICA-BUILDER", "open-materia-medica", "whispering-body-first-aid",
              "gentle-pediatrics-companion", "skin-case-tracker", "unstoppable-mind-companion",
              "mnemosyne-companion", "the-symphony-companion"}
HEALTH = {"bmi-bmr-tdee-macros-fluid-calculator"}
GAMES = {"neon-games", "neon-runner", "retro-strike", "idle-city-ages-of-growth",
         "dance-fight", "aethelgard-games", "AethelgardVN"}
DATA = {"homoeopathic-materia-medica-repertory-json", "OMM"}
UTILITIES = {"offline-pdf-toolkit", "CLDR", "TTB", "All4ONE", "ULTIMATE-WINDOWS-OPTIMIZER",
             "The_Browser", "NEO", "SmartNotes", "conqueror-os", "ambient-sound-studio",
             "read-live-transform-app", "smartbill-app", "HMS", "lexora", "lockhtml"}
FEATURED = {"today-card", "kent-repertory-explorer", "bmi-bmr-tdee-macros-fluid-calculator"}


_CACHE = {}

# Every URL whose fetch FAILED this run, with the reason. A failed fetch and an
# empty result are DIFFERENT things: on 2026-10-25 every authenticated call was
# refused (core quota 0/60) and the module still wrote an empty changes.json and
# a 335-byte feed.xml over the live ones - it reported "no activity" when the
# truth was "could not look". Nothing may be published on a failed fetch.
FAILED = {}


class FetchError(RuntimeError):
    """A fetch that failed. Distinct from a fetch that returned nothing."""


def _get(url):
    # in-process memo: one fetch per URL per run (fewer API calls, faster)
    if url in _CACHE:
        return _CACHE[url]
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "drsoam"})
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except Exception as e:
        FAILED[url] = "%s: %s" % (type(e).__name__, e)
        raise FetchError(FAILED[url]) from e
    _CACHE[url] = data
    return data


def repos():
    """Every live (non-fork) repo, most recently pushed first."""
    r = _get("https://api.github.com/users/%s/repos?per_page=100&sort=pushed" % OWNER)
    return [x for x in r if not x.get("fork")]


_KIT_IDS = None


def _kits():
    """The kit ids: the built-in set PLUS whatever the registry lists (so a new
    kit can never leak into the products list)."""
    global _KIT_IDS
    if _KIT_IDS is None:
        _KIT_IDS = set(KITS) | {k.get("id") for k in kit_list() if k.get("id")}
    return _KIT_IDS


def products(rs=None):
    """The product repos: live, not meta, not a kit.

    A repo whose name ends in '-kit' is ALWAYS a kit - that naming rule means a
    new kit can never leak into the products list even if the registry lags.
    """
    kits = _kits()
    return [r for r in (rs or repos())
            if r["name"] not in META and r["name"] not in kits and not r["name"].endswith("-kit")]


def kit_list():
    """The kits, from the registry's deps.json (the source of truth).

    Reads via the authenticated contents API (the registry is private), and
    accepts either shape: a list of ids, or a list of {id,status} objects.
    Always unioned with the built-in KITS, so a kit can never be missed.
    """
    ids = set(KITS)
    try:
        d = _get("https://api.github.com/repos/%s/registry/contents/deps.json" % OWNER)
        raw = base64.b64decode((d.get("content") or "").replace("\n", "")).decode("utf-8")
        for k in json.loads(raw).get("kits", []):
            if isinstance(k, str):
                ids.add(k)
            elif isinstance(k, dict) and str(k.get("status", "live")) == "live":
                ids.add(k.get("id") or k.get("name"))
    except Exception:
        pass
    ids.discard(None)
    return [{"id": k} for k in sorted(ids)]


def category(n):
    if n in HOMEOPATHY: return "Homeopathy"
    if n in HEALTH: return "Health Tools"
    if n in GAMES: return "Games"
    if n in DATA: return "Data"
    if n in UTILITIES: return "Utilities"
    return "HTML Apps"


def first_sentence(s):
    s = (s or "").strip()
    for end in (". ", "! ", "? "):
        if end in s:
            return s.split(end)[0] + end.strip()
    return s


def pages_url(n):
    return "https://drsamonline.github.io/%s/" % n


def shot(n):
    return "https://drsamonline.github.io/assets/shots/%s.webp" % n


def home(r):
    return r.get("homepage") or pages_url(r["name"])


def score(r):
    return sum([bool(r.get("description")), bool(r.get("license")), bool(r.get("homepage")),
                bool(r.get("has_pages")), not r.get("archived")])


# ---- the four outputs -------------------------------------------------------
# ---- the roadmap shown on the console ("next to come") ---------------------
def roadmap(rs=None):
    """Next to come — DERIVED from live data, because a hard-coded list goes stale.

    This was a fixed list and it drifted: it still queued `audio-kit` long after
    audio-kit was built, so the panel told the owner to wait for work already done.
    A list a human has to remember to edit will always lag; this reads the repos.

    The queue itself lives in the private master list, which the dashboard's token
    cannot read — so this shows what IS observable and says so, rather than guessing.
    """
    rs = rs or repos()
    kits = sorted(r["name"] for r in rs if r["name"].endswith("-kit"))
    prods = [r for r in rs if r["name"] not in META]
    return [
        {"what": "Kits built — %d: %s" % (len(kits), ", ".join(kits)),
         "state": "done", "link": "https://github.com/%s?tab=repositories&q=kit" % OWNER},
        {"what": "Retrofit — adopt a kit into the apps that still hand-roll it. The queue is "
                 "DERIVED from the audit (registry/audit.json), not from a list someone edits",
         "state": "in progress", "link": "https://github.com/drsamonline/forge"},
        {"what": "Apps live — %d products, %d of them pushed in the last 30 days"
                 % (len(prods), sum(1 for r in prods if (r.get("pushed_at") or "") >= _days_ago(30))),
         "state": "done", "link": "https://drsamonline.github.io/"},
        {"what": "The unbuilt queue lives in the master list, which is PRIVATE — the console cannot "
                 "read it, so it is not shown here rather than shown stale",
         "state": "not visible", "link": "https://github.com/drsamonline/knowledge"},
        {"what": "Forge as a licensed product — the commercial pack",
         "state": "planned", "link": "https://github.com/drsamonline/forge"},
    ]


def _days_ago(n):
    return (datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ")


def attention():
    """Open pull requests and issues that need the owner (the approvals inbox)."""
    try:
        q = urllib.parse.quote("is:open user:" + OWNER)
        url = "https://api.github.com/search/issues" + "?" + "q=" + q + "&" + "per_page=20"
        d = _get(url)
        out = []
        for i in d.get("items") or []:
            out.append({"title": i.get("title") or "",
                        "repo": (i.get("repository_url") or "").rsplit("/", 1)[-1],
                        "url": i.get("html_url"),
                        "kind": "PR" if i.get("pull_request") else "issue",
                        "created": i.get("created_at")})
        return out
    except Exception:
        return []


def controls():
    """Deep-links to each workflow's page, where "Run workflow" dispatches it."""
    return [{"label": a["name"], "what": a["what"],
             "url": "https://github.com/%s/%s/actions/workflows/%s" % (OWNER, a["repo"], a["file"])}
            for a in AUTOMATIONS]


def _auth_get(url, tok):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "drsoam"})
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def quota():
    """Actions budget.

    GitHub RETIRED the user-level billing API (it returns 410 Gone), so the live
    figure is ESTIMATED from the private repos' run durations instead. That needs a
    token that can read those repos' Actions runs - a CLASSIC PAT with the 'repo'
    scope, supplied as the BILLING_TOKEN secret.
    """
    out = {"available": False, "included_minutes": 2000,
           "note": "Actions minutes are free on public repos; the private repos draw on the free 2,000 min/month."}
    tok = os.environ.get("BILLING_TOKEN") or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    # 1) try the (retired) billing endpoint first - harmless if it 410s
    try:
        d = _auth_get("https://api.github.com/users/%s/settings/billing/actions" % OWNER, tok)
        out["available"] = True
        out["used_minutes"] = d.get("total_minutes_used")
        out["included_minutes"] = d.get("included_minutes") or 2000
        out["source"] = "billing api"
    except Exception:
        pass
    # 2) estimate this month's private-repo minutes from run durations
    try:
        mstart = datetime.datetime.now(datetime.timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        total, n = 0.0, 0
        for repo in ("forge", "registry", "knowledge"):
            page = 1
            while page <= 3:
                url = ("https://api.github.com/repos/%s/%s/actions/runs" % (OWNER, repo)
                       + "?" + "per_page=100" + "&" + "page=" + str(page))
                batch = _auth_get(url, tok).get("workflow_runs") or []
                for w in batch:
                    s0 = w.get("run_started_at") or w.get("created_at")
                    e0 = w.get("updated_at")
                    if not s0 or not e0:
                        continue
                    try:
                        s = datetime.datetime.fromisoformat(s0.replace("Z", "+00:00"))
                        e = datetime.datetime.fromisoformat(e0.replace("Z", "+00:00"))
                    except Exception:
                        continue
                    if s < mstart:
                        continue
                    total += max(0.0, (e - s).total_seconds()) / 60.0
                    n += 1
                if len(batch) < 100:
                    break
                page += 1
        out["private_runs"] = n
        out["estimated_minutes"] = round(total, 1)
        if not out["available"]:
            out["note"] = ("Actions minutes are free on public repos; the private repos draw on the free "
                            "2,000 min/month. The billing API is retired (410 Gone), so this is an ESTIMATE "
                            "from %d private-repo run(s) this month." % n)
    except Exception:
        out["private_runs"] = None
        if not out["available"]:
            out["note"] += (" Set BILLING_TOKEN to a CLASSIC PAT with the 'repo' scope so usage can be "
                             "estimated from the private repos' run durations.")
    return out


def changes():
    """A recent-activity feed: pushes, PRs and releases across the account."""
    try:
        d = _get("https://api.github.com/users/%s/events" % OWNER + "?" + "per_page=30")
        out = []
        for e in d:
            t = e.get("type") or ""
            repo = (e.get("repo") or {}).get("name", "").split("/")[-1]
            p = e.get("payload") or {}
            text = ""
            if t == "PushEvent":
                cs = p.get("commits") or []
                if cs:
                    text = (cs[-1].get("message") or "").split("\n")[0][:110]
                else:
                    br = (p.get("ref") or "").split("/")[-1]
                    n = p.get("size") or p.get("distinct_size") or 0
                    text = ("%d commit(s) to %s" % (n, br)) if n else ("pushed to " + br)
            elif t == "PullRequestEvent":
                text = (p.get("action", "") + ": " + ((p.get("pull_request") or {}).get("title") or ""))[:110]
            elif t == "IssuesEvent":
                text = (p.get("action", "") + ": " + ((p.get("issue") or {}).get("title") or ""))[:110]
            out.append({"type": t.replace("Event", ""), "repo": repo,
                        "when": e.get("created_at"), "text": text})
        return out[:20]
    except Exception:
        # None means COULD NOT LOOK. An empty list would mean "we looked, and
        # nothing happened" - and publishing that deletes the live feed.
        return None


def update_history(snap):
    """Append today's snapshot to history.json (idempotent), so the charts can
    show change over weeks instead of a single day."""
    hist = []
    if os.path.exists("history.json"):
        try:
            hist = json.load(open("history.json", encoding="utf-8")).get("history", [])
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("date") != snap["date"]]
    hist.append(snap)
    hist.sort(key=lambda h: h["date"])
    hist = hist[-90:]
    write("history.json", {"generated": snap["date"], "history": hist})
    return hist



def plan_block(rs=None):
    """Built vs planned — the idea list reconciled against the live repos.

    plan.json ships WITH the dashboard (public), so there is no token and no API
    call: the console owns the plan and reconciles it against the repo list it
    already fetches. The idea list is a FORWARD plan and the live repos are what
    exists, so the overlap is reported honestly rather than pretended away.
    """
    if not os.path.exists("plan.json"):
        return None
    try:
        plan = json.load(open("plan.json", encoding="utf-8"))
    except Exception:
        return None
    apps = plan.get("apps") or []
    if not apps:
        return None

    def sl(s):
        return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")

    live = {}
    for r in (rs or repos()):
        n = r["name"]
        if n in META or n.endswith("-kit"):
            continue
        live[sl(n)] = n

    built = 0
    for a in apps:
        s = sl(a.get("slug") or a.get("name"))
        if s in live:
            a["built"] = True
            a["repo"] = live[s]
            built += 1
        else:
            a["built"] = False

    planned_slugs = {sl(a.get("name")) for a in apps}
    not_planned = [n for s, n in live.items() if s not in planned_slugs]
    return {
        "planned": len(apps),
        "built": built,
        "unbuilt": len(apps) - built,
        "live_products": len(live),
        "live_not_planned": len(not_planned),
        "link": "https://github.com/%s/dashboard/blob/main/plan.json" % OWNER,
    }



def paused():
    """Projects deliberately parked — NOT deleted, and not lost.

    paused.json ships WITH the dashboard (public), exactly like plan.json, so
    there is no token and no API call. A parked project keeps its spec and its
    study doc; this only records why it stopped and what would resume it, so it
    is visible on the console instead of being forgotten in a backlog.
    """
    if not os.path.exists("paused.json"):
        return []
    try:
        d = json.load(open("paused.json", encoding="utf-8"))
    except Exception:
        return []
    out = []
    for i in (d.get("items") or []):
        out.append({
            "id": i.get("id") or "",
            "name": i.get("name") or i.get("id") or "",
            "what": i.get("what") or "",
            "why": i.get("why") or "",
            "resume": i.get("resume") or "",
            "spec": i.get("spec") or "",
            "since": i.get("since") or "",
        })
    return out


def traffic(rs=None):
    """Views, clones, referrers and popular pages (GitHub keeps only 14 days).

    Needs a token with PUSH access to each repo. The Actions-read token does not
    have that, so we PROBE once and, if it is refused, say so plainly rather than
    making hundreds of calls that all fail. It lights up by itself when a suitable
    token is supplied.
    """
    rs = rs or repos()
    names = [r["name"] for r in rs if r["name"] not in META]
    out = {"available": False, "window": "14 days",
           "note": "Needs a token with push access to the repos (the Actions-read token is not enough).",
           "repos": {}}
    tok = (os.environ.get("TRAFFIC_TOKEN") or os.environ.get("BILLING_TOKEN")
           or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    if not names or not tok:
        return out
    base = "https://api.github.com/repos/%s/" % OWNER
    try:
        _auth_get(base + names[0] + "/traffic/views", tok)   # the probe
    except Exception:
        return out
    out["available"] = True
    out["note"] = "Last 14 days — GitHub's retention window."
    for n in names:
        try:
            v = _auth_get(base + n + "/traffic/views", tok)
            c = _auth_get(base + n + "/traffic/clones", tok)
            rf = _auth_get(base + n + "/traffic/popular/referrers", tok)
            pp = _auth_get(base + n + "/traffic/popular/paths", tok)
            out["repos"][n] = {
                "views": v.get("count") or 0, "uniques": v.get("uniques") or 0,
                "clones": c.get("count") or 0, "clone_uniques": c.get("uniques") or 0,
                "referrers": [{"from": x.get("referrer"), "count": x.get("count")} for x in (rf or [])][:5],
                "paths": [{"path": x.get("path"), "count": x.get("count"), "title": x.get("title")} for x in (pp or [])][:5],
            }
        except Exception:
            out["repos"][n] = {}
    return out


def community(rs=None):
    """What OTHER people did: stars, forks and watchers — and who forked what.

    The counts come free with the repo list. The per-fork detail is fetched ONLY
    for repos that actually have forks, so this costs almost nothing while the
    projects are young, and stays correct once they aren't.
    """
    rs = rs or repos()
    tot = {"stars": 0, "forks": 0, "watchers": 0}
    out, detail = [], {}
    for r in rs:
        n = r["name"]
        if n in META:
            continue
        st = r.get("stargazers_count") or 0
        fk = r.get("forks_count") or 0
        wt = r.get("subscribers_count") or r.get("watchers_count") or 0
        tot["stars"] += st
        tot["forks"] += fk
        tot["watchers"] += wt
        if st or fk or wt:
            out.append({"name": n, "stars": st, "forks": fk, "watchers": wt,
                        "html_url": r.get("html_url")})
        if fk:
            url = ("https://api.github.com/repos/%s/%s/forks" % (OWNER, n)
                   + "?" + "per_page=100" + "&" + "sort=newest")
            try:
                detail[n] = [{"who": (f.get("owner") or {}).get("login"),
                              "full_name": f.get("full_name"),
                              "url": f.get("html_url"),
                              "stars": f.get("stargazers_count") or 0,
                              "created": (f.get("created_at") or "")[:10]}
                             for f in (_get(url) or [])]
            except Exception:
                detail[n] = []
    out.sort(key=lambda x: (x["stars"], x["forks"]), reverse=True)

    # issues and pull requests opened by someone OTHER than the owner
    ext = {"issues": 0, "prs": 0, "items": []}
    try:
        q = urllib.parse.quote("is:open user:%s -author:%s" % (OWNER, OWNER))
        d = _get("https://api.github.com/search/issues" + "?" + "q=" + q + "&" + "per_page=100")
        for i in (d.get("items") or []):
            ext["prs" if i.get("pull_request") else "issues"] += 1
            ext["items"].append({"title": i.get("title") or "",
                                 "repo": (i.get("repository_url") or "").rsplit("/", 1)[-1],
                                 "url": i.get("html_url"),
                                 "who": (i.get("user") or {}).get("login") or ""})
    except Exception:
        pass

    return {"totals": tot, "repos": out, "forks": detail,
            "forked_repos": sum(1 for v in detail.values() if v), "external": ext}


def dashboard():
    rs = repos()
    prods = products(rs)
    # the kit count comes from the repo list itself (a name ending in -kit), so it
    # is always right even when the private registry can't be read
    kits = [r["name"] for r in rs if r["name"].endswith("-kit") and r["name"] not in META] or [k["id"] for k in kit_list()]
    rows, conf, cats = [], {}, {}
    for r in prods:
        s = score(r)
        c = category(r["name"])
        rows.append({
            "name": r["name"], "description": r.get("description") or "",
            "pushed_at": r.get("pushed_at"), "homepage": home(r),
            "html_url": r.get("html_url"), "download": "", "category": c,
            "status": "%d/5" % s, "status_tone": "ok" if s >= 4 else ("warn" if s >= 3 else "bad"),
        })
        conf[str(s)] = conf.get(str(s), 0) + 1
        cats[c] = cats.get(c, 0) + 1
    rows.sort(key=lambda x: (x["pushed_at"] or ""), reverse=True)
    total = len(rows)
    avg = round(sum(int(x["status"].split("/")[0]) for x in rows) / total, 1) if total else 0.0

    # activity: pushes per day, over the last 14 days, across every repo
    day_counts = Counter((r.get("pushed_at") or "")[:10] for r in rs if r.get("pushed_at"))
    today = datetime.date.today()
    activity = []
    for i in range(13, -1, -1):
        d = (today - datetime.timedelta(days=i)).isoformat()
        activity.append({"date": d, "count": day_counts.get(d, 0)})

    pushed_today = {}
    for r in rs:
        if (r.get("pushed_at") or "")[:10] == today.isoformat():
            pushed_today[r["name"]] = 1

    autos = automation()
    bad = [a for a in autos if str(a.get("conclusion", "")).lower() in ("failure", "cancelled", "timed_out")]
    plan = plan_block(rs)

    cards = [
        {"title": "Products", "value": str(total), "tone": ""},
        {"title": "Kits", "value": str(len(kits)), "tone": "ok"},
        {"title": "Avg conformance", "value": "%s/5" % avg, "tone": "ok" if avg >= 4 else "warn"},
        {"title": "Automations", "value": str(len(autos)), "tone": "ok"},
    ]
    if plan:
        cards.append({"title": "Built / planned", "value": "%s / %s" % (plan.get("built"), plan.get("planned")), "tone": ""})

    return {
        "generated": today.isoformat(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reckoning": "%d products · %d kits · avg conformance %s/5 · updated automatically."
                     % (total, len(kits), avg),
        "health": "bad" if bad else "ok",
        "cards": cards,
        "summary": {"products": total, "kits": len(kits), "avg": avg,
                    "pushes": sum(a["count"] for a in activity), "byrepo": pushed_today},
        "stats": {"conformance": conf, "categories": cats},
        "activity": activity,
        "attention": attention(),
        "controls": controls(),
        "quota": quota(),
        "changes": changes(),
        "automation": autos,
        "roadmap": roadmap(rs),
        "plan": plan,
        "paused": paused(),
        "leaderboard": leaderboard(rs),
        "community": community(rs),
        "traffic": traffic(rs),
        "repos": rows,
        "links": {"store": "https://drsamonline.github.io/Matneo/",
                  "hub": "https://drsamonline.github.io/",
                  "forge": "https://github.com/%s/forge" % OWNER,
                  "registry": "https://github.com/%s/registry" % OWNER,
                  "knowledge": "https://github.com/%s/knowledge" % OWNER,
                  "actions": "https://github.com/%s?tab=repositories" % OWNER},
    }



# ---- the leaderboard: rank, and MOVEMENT (tools/leaderboard.py) -------------
# A ranking table is static; movement is the useful part, and the console already keeps
# history.json, so it is computable from data we already store. The score is a HEURISTIC
# and is shown only relative to our own repos - never as an absolute.
def leaderboard(rs=None):
    """The ranked rows plus the movement, computed by the shared tool."""
    import importlib.util, pathlib, datetime as _dt
    p = pathlib.Path(__file__).with_name("tools") / "leaderboard.py"
    if not p.exists():
        p = pathlib.Path(__file__).parent / "leaderboard.py"
    try:
        spec = importlib.util.spec_from_file_location("leaderboard", p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    except Exception as e:
        return {"error": f"leaderboard tool unavailable: {type(e).__name__}"}
    m.NOW = _dt.datetime.now(_dt.timezone.utc)
    rs = rs if rs is not None else repos()
    hist = []
    try:
        if os.path.exists("history.json"):
            h = json.load(open("history.json", encoding="utf-8"))
            hist = h if isinstance(h, list) else (h.get("history") or h.get("snapshots") or [])
    except Exception:
        pass
    # A tool bug must DEGRADE the console, not break it. The first version wrapped only
    # the import, so an int() crash inside build() took the whole refresh down with it.
    try:
        return m.build(rs, hist)
    except Exception as e:
        return {"error": f"leaderboard failed: {type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# WHAT MATNEO SELLS
#
# The store listed every repo as "Free / open-source", so it was SELLING NOTHING
# while looking like a shop - 46 free apps presented as a catalogue. The commercial
# plan is explicit: you sell FORGE (the control plane), and "the apps remain your
# free, open brand". So the catalogue is the LICENCE, and the apps belong to the hub.
#
# The prices are deliberately NOT invented here: the plan sets the tiers and leaves
# the numbers to TERMS.md, so the store says "Paid" and links to the terms.
# --------------------------------------------------------------------------- #
HUB = "https://drsamonline.github.io/"

FOR_SALE = [
    {"id": "forge-personal", "title": "Forge — Personal licence", "category": "Licence",
     "type": "licence", "price": "Free", "link": HUB, "landingPage": HUB,
     "image": "", "sourceRepo": "%s/forge" % OWNER, "license": "Proprietary (EULA)",
     "tagline": "Use Forge on your own non-commercial repos.",
     "description": "Run the whole system — the workflows, the kits, the queue, the console — "
                    "on your own non-commercial repositories. Attribution required; no resale.",
     "tags": ["licence", "personal"], "buyLinks": [], "rating": {"avg": 0, "count": 0}, "featured": True},
    {"id": "forge-commercial", "title": "Forge — Commercial licence", "category": "Licence",
     "type": "licence", "price": "Paid", "link": HUB, "landingPage": HUB,
     "image": "", "sourceRepo": "%s/forge" % OWNER, "license": "Proprietary (EULA)",
     "tagline": "Use Forge in commercial work, for one entity.",
     "description": "For companies, freelancers and client work: use Forge in commercial projects "
                    "for one entity. Terms and pricing are in TERMS.md.",
     "tags": ["licence", "commercial"], "buyLinks": [], "rating": {"avg": 0, "count": 0}, "featured": True},
    {"id": "forge-reseller", "title": "Forge — Reseller / OEM licence", "category": "Licence",
     "type": "licence", "price": "Paid", "link": HUB, "landingPage": HUB,
     "image": "", "sourceRepo": "%s/forge" % OWNER, "license": "Proprietary (EULA)",
     "tagline": "Bundle Forge into your own product.",
     "description": "Embed Forge in something you ship and resell. A higher tier, with terms and "
                    "pricing in TERMS.md.",
     "tags": ["licence", "oem"], "buyLinks": [], "rating": {"avg": 0, "count": 0}, "featured": False},
]


def store():
    """The catalogue: WHAT IS FOR SALE.

    It used to be every repo, each hard-coded "Free / open-source" - a shop selling
    nothing, with 46 free apps presented as products. The apps are free and they
    belong to the hub; this catalogue is the licence.
    """
    cat = [dict(x) for x in FOR_SALE]
    ids = [p["id"] for p in cat]
    assert len(ids) == len(set(ids)), "duplicate id in catalogue"
    cat.sort(key=lambda p: (not p.get("featured"), p["title"].lower()))
    return cat

def posts():
    """The product blog: posts about WHAT MATNEO SELLS.

    It used to emit one post per repo - 24 free-app announcements, which is a
    changelog of free things, not a product blog. Matneo carries no free-repo
    posts: those listings belong to the hub. Every post here is about something
    the shop actually offers.
    """
    out = []
    for p in store():
        out.append({
            "title": p["title"],
            "repo": p["id"],
            "category": "For sale" if p["price"] != "Free" else "Licence",
            "date": datetime.date.today().isoformat(),
            "summary": p.get("description") or p.get("tagline") or "",
            "url": p.get("link") or HUB,
            "source": p.get("sourceRepo") or "",
            "image": p.get("image") or "",
            "kind": "product",
            "price": p.get("price") or "",
        })
    out.sort(key=lambda p: (p["price"] == "Free", p["title"]))
    return {"generated": datetime.date.today().isoformat(), "posts": out}

def plan_status(path):
    """Rewrite the plan's FORGE:STATUS block from live data (kits included)."""
    rs = repos()
    prods = products(rs)
    kits = kit_list()
    newest = sorted(prods, key=lambda r: r.get("pushed_at") or "", reverse=True)[:5]
    L = []
    L.append("_Auto-generated %s by `drsoam.py plan`._" % datetime.date.today().isoformat())
    L.append("")
    L.append("- **Repos live:** %d (products %d, kits %d, meta %d)"
             % (len(rs), len(prods), len(kits), len(rs) - len(prods) - len(kits)))
    L.append("- **Kits live (%d):** %s" % (len(kits), ", ".join("`%s`" % k.get("id") for k in kits)))
    L.append("- **Most recently updated products:**")
    for r in newest:
        L.append("  - `%s` — %s" % (r["name"], (r.get("description") or "").strip()[:80]))
    L.append("- **Store / console / registry:** refreshed by the same scheduled pass (and by their")
    L.append("  own GitHub Actions), so this plan and the live surfaces never drift.")
    block = "<!-- FORGE:STATUS:START -->\n" + "\n".join(L) + "\n<!-- FORGE:STATUS:END -->"
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if "<!-- FORGE:STATUS:START -->" in text and "<!-- FORGE:STATUS:END -->" in text:
        text = re.sub(r"<!-- FORGE:STATUS:START -->.*?<!-- FORGE:STATUS:END -->", block, text, flags=re.S)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("plan status updated")


# ---- automation status (what self-updates, and when it last ran) -----------
AUTOMATIONS = [
    {"repo": "drsamonline.github.io", "file": "refresh-hub.yml", "name": "Refresh project hub", "what": "the project hub", "schedule": "daily 03:17 UTC"},
    {"repo": "drsamonline", "file": "update-profile.yml", "name": "Update profile README", "what": "the profile README", "schedule": "daily 03:17 UTC"},
    {"repo": "dashboard", "file": "refresh.yml", "name": "Refresh dashboard data", "what": "this dashboard", "schedule": "daily 03:47 UTC"},
    {"repo": "drsamonline", "file": "metrics.yml", "name": "Metrics", "what": "the metric cards", "schedule": "daily 04:00 UTC"},
    {"repo": "Matneo", "file": "blog.yml", "name": "Refresh blog posts", "what": "the blog", "schedule": "daily 04:12 UTC"},
    {"repo": "Matneo", "file": "store.yml", "name": "Refresh store catalogue", "what": "the store", "schedule": "daily 04:22 UTC"},
    {"repo": "knowledge", "file": "refresh.yml", "name": "Refresh plan status", "what": "the plan", "schedule": "daily 04:32 UTC"},
    {"repo": "registry", "file": "refresh.yml", "name": "Refresh registry", "what": "the registry", "schedule": "daily 04:42 UTC"},
    {"repo": "app-builder", "file": "kit-tests.yml", "name": "All kit tests", "what": "every kit's tests", "schedule": "daily 05:00 UTC"},
    {"repo": "skills", "file": "validate.yml", "name": "validate skills", "what": "the skills catalogue", "schedule": "weekly (Mon)"},
    {"repo": "forge", "file": "heartbeat.yml", "name": "Heartbeat", "what": "the control plane", "schedule": "daily 06:00 UTC"},
]


def automation():
    """For each self-updating workflow: its schedule and its most recent run.

    Batched: ONE /actions/runs call per repo, then match each workflow by name -
    instead of one call per workflow.
    """
    repos_needed = sorted({a["repo"] for a in AUTOMATIONS})
    latest = {}
    unreadable = set()
    for repo in repos_needed:
        if repo in ("registry", "forge", "knowledge"):
            continue  # private: the dashboard token cannot read their runs
        try:
            d = _get("https://api.github.com/repos/%s/%s/actions/runs" % (OWNER, repo) + "?" + "per_page=40")
            for w in d.get("workflow_runs") or []:
                key = (repo, (w.get("name") or "").strip())
                if key not in latest:
                    latest[key] = w
        except Exception:
            # NOT "no runs yet" - we simply could not look. Saying "never ran"
            # about a workflow that runs daily is the same lie of omission the
            # console already had to correct once.
            unreadable.add(repo)
    out = []
    for a in AUTOMATIONS:
        rec = dict(a)
        rec["repo_url"] = "https://github.com/%s/%s" % (OWNER, a["repo"])
        rec["url"] = "%s/actions/workflows/%s" % (rec["repo_url"], a["file"])
        rec["last_run"] = None
        rec["conclusion"] = "no runs yet"
        if a["repo"] in ("registry", "forge", "knowledge"):
            # NOT "never ran". The workflow runs; the console simply cannot see it,
            # because its token reads public repos only. Saying "never" is a lie of
            # omission - the owner read it as a broken schedule.
            rec["conclusion"] = "not visible (private repo)"
            rec["note"] = ("This repository is private, so the console cannot read its run "
                           "history. That is NOT the same as 'never ran' - open the link to see it.")
        elif a["repo"] in unreadable:
            rec["conclusion"] = "not readable (fetch failed)"
            rec["note"] = ("The runs API refused this repository on the last refresh, so this "
                           "is UNKNOWN - not 'never ran'. It lights up again when the fetch does.")
        else:
            w = latest.get((a["repo"], a["name"]))
            if w:
                rec["last_run"] = w.get("updated_at") or w.get("created_at")
                rec["conclusion"] = w.get("conclusion") or w.get("status") or "?"
                rec["url"] = w.get("html_url") or rec["url"]
        out.append(rec)
    return out


def esc_xml(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def rss(items):
    """A tiny RSS feed of the recent-activity list (subscribable)."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<rss version="2.0"><channel>',
           '<title>drsamonline — what changed</title>',
           '<link>https://drsamonline.github.io/dashboard/</link>',
           '<description>Recent pushes, pull requests and releases across drsamonline.</description>',
           '<lastBuildDate>' + now + '</lastBuildDate>']
    for c in items or []:
        title = "%s — %s" % (c.get("repo", ""), c.get("text") or c.get("type", ""))
        out.append("<item><title>%s</title><description>%s</description><guid>%s</guid><pubDate>%s</pubDate></item>"
                   % (esc_xml(title), esc_xml(c.get("text", "")),
                      esc_xml(c.get("repo", "") + "-" + str(c.get("when", ""))), esc_xml(c.get("when") or now)))
    out.append("</channel></rss>")
    return "\n".join(out) + "\n"


def write(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(obj, str):
            f.write(obj)
        else:
            json.dump(obj, f, indent=2, ensure_ascii=False)
            f.write("\n")
    print("wrote", path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def publish_dashboard(data):
    """Write the dashboard outputs; return the list of things that could NOT be
    written truthfully (empty when everything was).

    The rule this exists for: a feed built on a FAILED fetch is not an empty
    feed. When the activity fetch fails, the feed already published is kept
    byte-for-byte, and the caller is told - so the run is visibly degraded
    instead of quietly publishing "nothing happened" over the real history.
    """
    degraded = []
    changes = data.get("changes")
    fetched = changes is not None   # did we actually LOOK this run?
    if changes is None:
        prev = _read_json("changes.json")
        if (isinstance(prev, dict) and isinstance(prev.get("changes"), list)
                and os.path.exists("feed.xml")):
            data["changes"] = prev["changes"]
            degraded.append("activity feed: the fetch failed, so the published feed was kept as it was")
        else:
            degraded.append("activity feed: the fetch failed and there is no published feed to keep")

    snap = {"date": data["generated"], "products": data["summary"]["products"],
            "kits": data["summary"]["kits"], "avg": data["summary"]["avg"],
            "pushes": data["summary"]["pushes"], "byrepo": data["summary"]["byrepo"],
            "stars": data["community"]["totals"]["stars"], "forks": data["community"]["totals"]["forks"],
            "watchers": data["community"]["totals"]["watchers"]}
    hist = update_history(snap)
    data["history"] = hist
    for row in data["repos"]:
        row["spark"] = [h.get("byrepo", {}).get(row["name"], 0) for h in hist]
    data["degraded"] = degraded
    write("data.json", data)
    write("forks.json", {"generated": data["generated"], "forks": data["community"]["forks"]})
    write("community.json", {"generated": data["generated"], **data["community"]})
    write("traffic.json", {"generated": data["generated"], **data["traffic"]})
    if fetched:
        # only a feed we actually looked at may be rewritten; a reused one stays
        # byte-for-byte as published
        write("changes.json", {"generated": data["generated"], "changes": data["changes"]})
        write("feed.xml", rss(data["changes"]))
    return degraded


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("dashboard", "store", "posts", "plan"):
        print("usage: drsoam.py <dashboard|store|posts|plan>", file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    if mode == "dashboard":
        data = dashboard()
        degraded = publish_dashboard(data)
        if degraded:
            for d in degraded:
                print("::warning::" + d)
            print("DEGRADED - nothing was invented; the published feed was left as it was",
                  file=sys.stderr)
            sys.exit(3)
    elif mode == "store":
        data = store()
        write("docs/data/products.json", data)
        write("data/products.json", data)
    elif mode == "posts":
        write("docs/data/posts.json", posts())
    elif mode == "plan":
        plan_status("docs/drsamonline_system_plan.md")


if __name__ == "__main__":
    main()
