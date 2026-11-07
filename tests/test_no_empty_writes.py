#!/usr/bin/env python3
"""The proof for the refresh guard: a FAILED fetch never publishes "nothing".

On 2026-10-25 every authenticated GitHub call was refused (core quota 0/60).
drsoam.py still wrote changes.json (49 bytes) and feed.xml (335 bytes) over the
live ones, so the published activity feed was DELETED and the run reported
success. An empty feed is a claim about the world ("nothing happened"); a failed
fetch is a claim about us ("we could not look"). They must never be confused.

    python3 -m unittest discover -s tests -v

MIT. (c) 2026 Dr Sohil Momin.
"""
import base64
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("drsoam", os.path.join(ROOT, "drsoam.py"))
drsoam = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drsoam)


def snapshot(changes):
    """The minimum a dashboard dict must carry for publish_dashboard()."""
    return {
        "generated": "2026-10-26",
        "summary": {"products": 53, "kits": 18, "avg": 4.9, "pushes": 78, "byrepo": {}},
        "community": {"totals": {"stars": 1, "forks": 0, "watchers": 1}, "forks": []},
        "traffic": {"available": False, "repos": {}},
        "repos": [],
        "changes": changes,
    }


class InTmp(unittest.TestCase):
    def setUp(self):
        self._old = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        # The manifest gate (added after these tests) refuses to answer outside a git
        # working tree - "not a git checkout — manifest.py requires a git working tree" -
        # so publish_dashboard() degraded on every path and four tests went red in a
        # plain temp dir while passing in CI. Make the temp dir what the gate needs.
        subprocess.run(["git", "init", "-q"], cwd=self.tmp, check=True)
        os.chdir(self.tmp)
        # DEGRADED and FAILED are MODULE globals, so one test's failed fetch was
        # still listed in the next test's data.json and made
        # "data.json must carry the reason" fail on a leftover, not on a bug.
        # A run is one process in production, so clearing per test is the truth.
        drsoam.DEGRADED[:] = []
        drsoam.FAILED.clear()
        drsoam.AUTOMATION_SOURCE = "unknown"
        drsoam.AUTOMATION_NOTE = ""

    def tearDown(self):
        os.chdir(self._old)


class TestFetchFailureIsNotEmptiness(unittest.TestCase):
    def test_changes_returns_None_when_the_fetch_fails(self):
        real = drsoam._get
        drsoam._get = lambda url: (_ for _ in ()).throw(drsoam.FetchError("403 rate limit"))
        try:
            got = drsoam.changes()
        finally:
            drsoam._get = real
        self.assertIsNone(got, "a failed fetch must be None (unknown), never [] (nothing happened)")

    def test_an_empty_result_is_still_an_empty_list(self):
        real = drsoam._get
        drsoam._get = lambda url: []
        try:
            got = drsoam.changes()
        finally:
            drsoam._get = real
        self.assertEqual(got, [], "a successful fetch with no events IS legitimately empty")

    def test_get_records_the_failure(self):
        real = drsoam._get
        drsoam.FAILED.clear()
        drsoam._get = real
        try:
            drsoam._get("https://api.github.com/definitely-not-a-real-endpoint-xyz")
            self.fail("expected FetchError")
        except drsoam.FetchError:
            pass
        self.assertIn("https://api.github.com/definitely-not-a-real-endpoint-xyz", drsoam.FAILED)


class TestAutomationTellsTheTruth(unittest.TestCase):
    """Two different unknowns, and they are not the same thing:

      * the fleet SCAN cannot be read  -> there is no list at all, so automation()
        answers [] and DEGRADED carries the reason (the console prints "?" and
        "the list is UNKNOWN this run, not empty").
      * the scan is readable but a repo's RUN HISTORY cannot be read -> the
        workflow exists and is scheduled, so saying "no runs yet" about it would
        be a lie of omission. It must say "not readable (fetch failed)".

    Both tests below used to mock every fetch at once, which turned the first
    case into the second and made the suite red for a design that was right.
    """

    INVENTORY = {"repos": [{"repo": "game-kit", "workflows": [
        {"file": "test.yml", "name": "Test", "triggers": {"crons": ["0 6 * * *"]}}]}]}

    def test_unreadable_runs_are_not_reported_as_never_ran(self):
        real = drsoam._get
        real_source = drsoam.AUTOMATION_SOURCE

        def fake(url):
            if url == drsoam.INVENTORY_URL % drsoam.OWNER:
                return {"content": base64.b64encode(json.dumps(self.INVENTORY).encode()).decode()}
            raise drsoam.FetchError("403")

        drsoam._get = fake
        try:
            autos = drsoam.automation()
        finally:
            drsoam._get = real
            drsoam.AUTOMATION_SOURCE = real_source
        self.assertTrue(autos, "the scan was readable, so there is a list to report on")
        for a in autos:
            self.assertEqual(a["conclusion"], "not readable (fetch failed)",
                             "%s claimed %r - a failed fetch is not 'no runs yet'" % (a["repo"], a["conclusion"]))
            self.assertNotIn("no runs yet", a["conclusion"])

    def test_an_unreadable_scan_is_empty_AND_says_why(self):
        # The empty list is only honest while the reason travels with it.
        real = drsoam._get
        drsoam._get = lambda url: (_ for _ in ()).throw(drsoam.FetchError("403"))
        drsoam.DEGRADED[:] = []
        try:
            autos = drsoam.automation()
        finally:
            drsoam._get = real
        self.assertEqual(autos, [])
        self.assertTrue([d for d in drsoam.DEGRADED if d.get("what") == "scheduled workflows"],
                        "an empty automation list with no reason is a claim that nothing is scheduled")


class TestPublishNeverDeletesTheLiveFeed(InTmp):
    def test_a_failed_fetch_keeps_the_published_feed(self):
        good_changes = {"generated": "2026-10-25", "changes": [{"type": "Push", "repo": "x"}]}
        good_feed = "<rss>the real feed</rss>"
        with open("changes.json", "w", encoding="utf-8") as f:
            json.dump(good_changes, f)
        with open("feed.xml", "w", encoding="utf-8") as f:
            f.write(good_feed)

        degraded = drsoam.publish_dashboard(snapshot(None))

        self.assertEqual(len(degraded), 1, "a degraded publish must say so")
        with open("feed.xml", encoding="utf-8") as f:
            self.assertEqual(f.read(), good_feed, "the published feed was OVERWRITTEN by a failed fetch")
        with open("changes.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["changes"], good_changes["changes"])
        with open("data.json", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["degraded"], degraded, "data.json must carry the reason")
        self.assertEqual(data["changes"], good_changes["changes"])

    def test_a_failed_fetch_with_no_previous_feed_writes_no_feed(self):
        degraded = drsoam.publish_dashboard(snapshot(None))
        self.assertEqual(len(degraded), 1)
        self.assertFalse(os.path.exists("changes.json"), "wrote an empty changes.json over nothing")
        self.assertFalse(os.path.exists("feed.xml"), "wrote an empty feed over nothing")
        self.assertTrue(os.path.exists("data.json"), "the rest of the dashboard is still useful")

    def test_a_good_fetch_writes_the_feed_and_reports_no_degradation(self):
        degraded = drsoam.publish_dashboard(snapshot([{"type": "Push", "repo": "y", "text": "hi"}]))
        self.assertEqual(degraded, [])
        self.assertTrue(os.path.exists("feed.xml"))
        with open("changes.json", encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["changes"]), 1)

    def test_a_legitimately_empty_feed_is_written_without_complaint(self):
        degraded = drsoam.publish_dashboard(snapshot([]))
        self.assertEqual(degraded, [], "an empty list is a fact, not a failure")
        self.assertTrue(os.path.exists("feed.xml"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
