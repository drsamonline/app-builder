#!/usr/bin/env python3
"""A narrow token must not publish a narrower estate.

WHAT WENT WRONG, exactly.

`repos()` has always done the right thing in the abstract: try /user/repos (which
sees private repositories), fall back to the public list, and say so in SCOPE. The
defect was what the callers did with the fallback - they PUBLISHED it.

`knowledge/refresh.yml` set `GH_TOKEN: ${{ secrets.FANOUT_TOKEN || github.token }}`.
That reads as defensive and is the opposite: when the secret was absent the
fallback authenticated as one repository, /user/repos returned that one repository,
repos() fell back to the public list, and the plan block counted **136 repos, 103
products, 14 kits** where the estate is **147, 111, 20**. The difference is exactly
the 11 private repositories. Nothing failed. The block was published as fact and
the estate under-counted itself for weeks; the refresh prompt in forge spent three
cycles describing it as an owner action ("supply a read token") when the module had
been handed a token it could not use.

So the guard is a MODE, not a default:

    DRSOAM_REQUIRE_FULL_SCOPE=1

set by the workflows that publish a number about the estate. In that mode a token
that answers but cannot see the private repositories is a credential DEFECT: the
run fails and nothing is written, instead of shipping a smaller number as if it
were the estate. With the flag unset (a local run, a caller that legitimately wants
the public list) the old behaviour is unchanged, which is why this test checks
BOTH - a guard that is always on would break the callers it is not about.

The second half is the diagnostic that cost three cycles: a REJECTED credential and
an EMPTY estate both arrive as an empty list. `_no_list_reason()` now says which
one it is, because "no repository list" was read as "nothing there" when the truth
was "401, the token is dead".

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import drsoam  # noqa: E402


OWNER_REPOS = "/users/%s/repos" % drsoam.OWNER


def _repo(name, private=False):
    return {"name": name, "full_name": "%s/%s" % (drsoam.OWNER, name),
            "private": private, "fork": False}


class _Fetcher:
    """Stands in for drsoam._get, so the test never touches the network."""

    def __init__(self, owned, public, reject=False):
        self.owned, self.public, self.reject = owned, public, reject
        self.seen = []

    def __call__(self, url):
        self.seen.append(url)
        if self.reject:
            drsoam.FAILED[url] = "HTTPError: 401 Client Error: Unauthorized"
            raise drsoam.FetchError(drsoam.FAILED[url])
        if "/user/repos" in url:
            return list(self.owned)
        if OWNER_REPOS in url:
            return list(self.public)
        return []


class FullScopeTest(unittest.TestCase):
    def setUp(self):
        self._get, self._env = drsoam._get, dict(os.environ)
        drsoam.FAILED.clear()
        drsoam._CACHE.clear()
        drsoam.SCOPE = "unknown"
        drsoam.SCOPE_NOTE = ""
        os.environ["GH_TOKEN"] = "a-token"

    def tearDown(self):
        drsoam._get = self._get
        drsoam.FAILED.clear()
        drsoam._CACHE.clear()
        os.environ.clear()
        os.environ.update(self._env)

    # ---- the guard is OFF by default ------------------------------------
    def test_a_scoped_token_still_falls_back_when_the_mode_is_off(self):
        os.environ.pop("DRSOAM_REQUIRE_FULL_SCOPE", None)
        drsoam._get = _Fetcher([_repo("the-one-repo")], [_repo("a"), _repo("b")])
        got = drsoam.repos()
        self.assertEqual([r["name"] for r in got], ["a", "b"])
        self.assertEqual(drsoam.SCOPE, "public-only")

    def test_a_full_token_returns_everything_in_either_mode(self):
        os.environ["DRSOAM_REQUIRE_FULL_SCOPE"] = "1"
        drsoam._get = _Fetcher([_repo("a"), _repo("b"), _repo("secret", True)],
                               [_repo("a"), _repo("b")])
        got = drsoam.repos()
        self.assertEqual(len(got), 3)
        self.assertEqual(drsoam.SCOPE, "all")

    # ---- the guard BITES when the workflow asks for it ------------------
    def test_a_narrow_token_fails_the_run_in_full_scope_mode(self):
        os.environ["DRSOAM_REQUIRE_FULL_SCOPE"] = "1"
        drsoam._get = _Fetcher([_repo("the-one-repo")], [_repo("a"), _repo("b")])
        with self.assertRaises(drsoam.FetchError) as cm:
            drsoam.repos()
        msg = str(cm.exception)
        # the message has to say what to DO, not just that something is wrong
        self.assertIn("FANOUT_TOKEN", msg)
        self.assertIn("2 PUBLIC", msg)
        self.assertEqual(drsoam.SCOPE, "failed")
        self.assertEqual(drsoam.SCOPE_NOTE, "the token saw only the public repositories, "
                                          "and this run requires all of them")

    def test_an_anonymous_run_is_not_a_defect(self):
        """No credential at all: public-only is the honest answer, not a failure."""
        os.environ["DRSOAM_REQUIRE_FULL_SCOPE"] = "1"
        os.environ.pop("GH_TOKEN", None)
        os.environ.pop("GITHUB_TOKEN", None)
        drsoam._get = _Fetcher([], [_repo("a"), _repo("b")])
        got = drsoam.repos()
        self.assertEqual(len(got), 2)
        self.assertEqual(drsoam.SCOPE, "public-only")

    # ---- and a dead credential says so ----------------------------------
    def test_a_rejected_credential_names_the_credential(self):
        drsoam._get = _Fetcher([], [], reject=True)
        with self.assertRaises(drsoam.FetchError) as cm:
            drsoam.repos()
        msg = str(cm.exception)
        self.assertIn("401", msg)
        self.assertIn("REJECTED", msg)
        self.assertIn("/user/repos", msg)

    def test_no_endpoint_at_all_is_not_dressed_up_as_a_rejection(self):
        drsoam._get = _Fetcher([], [])
        with self.assertRaises(drsoam.FetchError) as cm:
            drsoam.repos()
        self.assertNotIn("REJECTED", str(cm.exception))
        self.assertIn("no repository list", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
