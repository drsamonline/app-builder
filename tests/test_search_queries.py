#!/usr/bin/env python3
"""The proof for the search guard: every issue search names its kind.

GitHub's issue search refuses a query that carries neither `is:issue` nor
`is:pull-request` - HTTP 422, "Query must include 'is:issue' or 'is:pull-request'".
The module asked `is:open user:<owner>` in two places, so from the day GitHub
started enforcing it:

  * the dashboard's community panel published `external: unknown` and went DEGRADED
    on every refresh (it at least said so), and
  * the approvals inbox returned [] - a SILENT zero, reading as "nothing needs you"
    when the truth was "the search was refused".

    python3 -m unittest discover -s tests -v

MIT. (c) 2026 Dr Sohil Momin.
"""
import importlib.util
import os
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("drsoam", os.path.join(ROOT, "drsoam.py"))
drsoam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drsoam)


def query_of(url):
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("q", [""])[0]


class Recording:
    """Stands in for _get: records every URL, answers the search with two items."""

    def __init__(self):
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if "search/issues" in url:
            q = query_of(url)
            if "is:issue" in q:
                return {"items": [{"title": "an issue", "repository_url": "https://api.github.com/repos/o/r",
                                   "html_url": "u1", "user": {"login": "someone"}}]}
            if "is:pull-request" in q:
                return {"items": [{"title": "a pr", "repository_url": "https://api.github.com/repos/o/r",
                                   "html_url": "u2", "user": {"login": "someone"},
                                   "pull_request": {"url": "p"}}]}
            raise drsoam.FetchError("gh: Query must include 'is:issue' or 'is:pull-request' (HTTP 422)")
        return []


class SearchQueryGuard(unittest.TestCase):
    def setUp(self):
        self.rec = Recording()
        self.orig_get, drsoam._get = drsoam._get, self.rec
        drsoam.DEGRADED.clear()
        drsoam.FAILED.clear()
        # community() falls back to the live repo list when given none; these tests
        # are about the search, so hand it an empty estate instead of a network call.
        self.orig_repos, drsoam.repos = drsoam.repos, lambda: []

    def tearDown(self):
        drsoam._get = self.orig_get
        drsoam.repos = self.orig_repos

    def test_every_search_url_names_its_kind(self):
        drsoam._search_open()
        searches = [u for u in self.rec.urls if "search/issues" in u]
        self.assertTrue(searches, "the helper must actually call the search endpoint")
        for url in searches:
            q = query_of(url)
            self.assertTrue("is:issue" in q or "is:pull-request" in q,
                            "GitHub refuses this query with 422: %r" % q)

    def test_community_counts_both_kinds_and_is_not_degraded(self):
        out = drsoam.community(rs=[])
        ext = out["external"]
        self.assertNotIn("unknown", ext)
        self.assertEqual((ext["issues"], ext["prs"]), (1, 1))
        self.assertEqual(drsoam.DEGRADED, [])

    def test_the_approvals_inbox_is_not_silently_empty(self):
        items = drsoam.attention()
        self.assertEqual([i["kind"] for i in items], ["issue", "PR"])


if __name__ == "__main__":
    unittest.main()
