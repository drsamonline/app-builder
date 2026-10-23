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

MIT License. (c) 2026 Dr Sohil Momin.
"""
import json, os, re, sys, urllib.request, urllib.parse, datetime
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


def _get(url):
    # in-process memo: one fetch per URL per run (fewer API calls, faster)
    if url in _CACHE:
        return _CACHE[url]
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "drsoam"})
    tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
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
    """The product repos: live, not meta, not a kit."""
    kits = _kits()
    return [r for r in (rs or repos()) if r["name"] not in META and r["name"] not in kits]


def kit_list():
    """The kits, from the registry's deps.json (the source of truth)."""
    try:
        d = _get("https://raw.githubusercontent.com/%s/registry/main/deps.json" % OWNER)
        return [k for k in d.get("kits", []) if k.get("status") == "live"]
    except Exception:
        return [{"id": k} for k in sorted(KITS)]


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
ROADMAP = [
    {"what": "Retrofit — adopt the kits into the apps that duplicate them", "state": "in progress",
     "link": "https://github.com/drsamonline/forge"},
    {"what": "Kits queued — audio, date, convert, image, chart, form, qr, markdown, pdf, table, template, cli, json",
     "state": "queued", "link": "https://github.com/drsamonline/knowledge"},
    {"what": "Apps queued — Carrier/Beam (optical), Chalk, Canteen", "state": "queued",
     "link": "https://github.com/drsamonline/registry"},
    {"what": "Forge as a licensed product — the commercial pack", "state": "planned",
     "link": "https://github.com/drsamonline/forge"},
]


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


def quota():
    """Actions budget. Public repos are free; the private repos draw on 2,000 min/month."""
    out = {"available": False, "included_minutes": 2000,
           "note": "Actions minutes are free on public repos; the private repos draw on the free 2,000 min/month."}
    try:
        d = _get("https://api.github.com/users/%s/settings/billing/actions" % OWNER)
        out["available"] = True
        out["used_minutes"] = d.get("total_minutes_used")
        out["included_minutes"] = d.get("included_minutes") or 2000
    except Exception:
        out["note"] += " (needs a billing-scoped token to read the live number.)"
    try:
        runs = 0
        for repo in ("forge", "registry", "knowledge"):
            d = _get("https://api.github.com/repos/%s/%s/actions/runs" % (OWNER, repo) + "?" + "per_page=1")
            runs += int(d.get("total_count") or 0)
        out["private_runs"] = runs
    except Exception:
        out["private_runs"] = None
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
                    text = "%d commit(s) to %s" % (p.get("size") or 0, br)
            elif t == "PullRequestEvent":
                text = (p.get("action", "") + ": " + ((p.get("pull_request") or {}).get("title") or ""))[:110]
            elif t == "IssuesEvent":
                text = (p.get("action", "") + ": " + ((p.get("issue") or {}).get("title") or ""))[:110]
            out.append({"type": t.replace("Event", ""), "repo": repo,
                        "when": e.get("created_at"), "text": text})
        return out[:20]
    except Exception:
        return []


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


def dashboard():
    rs = repos()
    prods = products(rs)
    kits = kit_list()
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

    return {
        "generated": today.isoformat(),
        "generated_at": datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "reckoning": "%d products · %d kits · avg conformance %s/5 · updated automatically."
                     % (total, len(kits), avg),
        "health": "bad" if bad else "ok",
        "cards": [
            {"title": "Products", "value": str(total), "tone": ""},
            {"title": "Kits", "value": str(len(kits)), "tone": "ok"},
            {"title": "Avg conformance", "value": "%s/5" % avg, "tone": "ok" if avg >= 4 else "warn"},
            {"title": "Automations", "value": str(len(autos)), "tone": "ok"},
        ],
        "summary": {"products": total, "kits": len(kits), "avg": avg,
                    "pushes": sum(a["count"] for a in activity), "byrepo": pushed_today},
        "stats": {"conformance": conf, "categories": cats},
        "activity": activity,
        "attention": attention(),
        "controls": controls(),
        "quota": quota(),
        "changes": changes(),
        "automation": autos,
        "roadmap": ROADMAP,
        "repos": rows,
        "links": {"store": "https://drsamonline.github.io/Matneo/",
                  "hub": "https://drsamonline.github.io/",
                  "forge": "https://github.com/%s/forge" % OWNER,
                  "registry": "https://github.com/%s/registry" % OWNER,
                  "knowledge": "https://github.com/%s/knowledge" % OWNER,
                  "actions": "https://github.com/%s?tab=repositories" % OWNER},
    }


def store():
    cat = []
    for r in products():
        n = r["name"]
        lic = (r.get("license") or {}).get("spdx_id") if r.get("license") else "MIT"
        desc = r.get("description") or ""
        cat.append({"id": n.lower(), "title": n, "category": category(n), "type": "open-source",
                    "price": "Free", "link": home(r), "landingPage": home(r), "image": shot(n),
                    "sourceRepo": "%s/%s" % (OWNER, n), "license": lic or "MIT",
                    "tagline": first_sentence(desc), "description": desc,
                    "tags": (r.get("topics") or [])[:4] or [category(n)],
                    "buyLinks": [], "rating": {"avg": 0, "count": 0},
                    "featured": n in FEATURED})
    # a couple of hand-made apps that live outside the raw list
    for extra in (("today-card", "HTML Apps", "One card for the day: your date, one intention, one task, and a streak."),
                  ("seance", "HTML Apps", "Sealed notes, opened once — Strongbox's sealed-note app.")):
        if not any(p["id"] == extra[0] for p in cat):
            cat.append({"id": extra[0], "title": extra[0], "category": extra[1], "type": "open-source",
                        "price": "Free", "link": pages_url(extra[0]), "landingPage": pages_url(extra[0]),
                        "image": shot(extra[0]), "sourceRepo": "%s/%s" % (OWNER, extra[0]), "license": "MIT",
                        "tagline": extra[2], "description": extra[2], "tags": [extra[1]],
                        "buyLinks": [], "rating": {"avg": 0, "count": 0},
                        "featured": extra[0] in FEATURED})
    ids = [p["id"] for p in cat]
    assert len(ids) == len(set(ids)), "duplicate id in catalogue"
    cat.sort(key=lambda p: (not p.get("featured"), p["title"].lower()))
    return cat


def posts():
    out = []
    for r in products():
        n = r["name"]
        desc = (r.get("description") or "").strip()
        out.append({"title": first_sentence(desc) or n, "repo": n, "category": "App update",
                    "date": (r.get("pushed_at") or "")[:10], "summary": desc,
                    "url": home(r), "source": r.get("html_url"), "image": shot(n), "kind": "update"})
    out.sort(key=lambda p: p["date"], reverse=True)
    return {"generated": datetime.date.today().isoformat(), "posts": out[:24]}


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
    {"repo": "skills", "file": "refresh.yml", "name": "refresh", "what": "the skills catalogue", "schedule": "weekly (Mon)"},
    {"repo": "forge", "file": "heartbeat.yml", "name": "Heartbeat", "what": "the control plane", "schedule": "daily 06:00 UTC"},
]


def automation():
    """For each self-updating workflow: its schedule and its most recent run.

    Batched: ONE /actions/runs call per repo, then match each workflow by name -
    instead of one call per workflow.
    """
    repos_needed = sorted({a["repo"] for a in AUTOMATIONS})
    latest = {}
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
            pass
    out = []
    for a in AUTOMATIONS:
        rec = dict(a)
        rec["repo_url"] = "https://github.com/%s/%s" % (OWNER, a["repo"])
        rec["url"] = "%s/actions/workflows/%s" % (rec["repo_url"], a["file"])
        rec["last_run"] = None
        rec["conclusion"] = "no runs yet"
        if a["repo"] in ("registry", "forge", "knowledge"):
            rec["conclusion"] = "scheduled (private repo)"
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


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("dashboard", "store", "posts", "plan"):
        print("usage: drsoam.py <dashboard|store|posts|plan>", file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    if mode == "dashboard":
        data = dashboard()
        snap = {"date": data["generated"], "products": data["summary"]["products"],
                "kits": data["summary"]["kits"], "avg": data["summary"]["avg"],
                "pushes": data["summary"]["pushes"], "byrepo": data["summary"]["byrepo"]}
        hist = update_history(snap)
        data["history"] = hist
        for row in data["repos"]:
            row["spark"] = [h.get("byrepo", {}).get(row["name"], 0) for h in hist]
        write("data.json", data)
        write("changes.json", {"generated": data["generated"], "changes": data["changes"]})
        write("feed.xml", rss(data["changes"]))
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
