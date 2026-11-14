#!/usr/bin/env python3
"""The proof for the catalogue: every product the shop sells comes from FOR_SALE.

WHAT WENT WRONG, exactly.

`store()` builds the catalogue from `FOR_SALE` and nothing else - which is the
right design (one source, no drift) right up until somebody adds a product to the
OUTPUT instead of the list. That is what happened on 2026-11-12: the NTET 2026
course was written straight into Matneo's `docs/data/products.json` (5e20cd4,
8b57a18) and never into `FOR_SALE`.

Nothing failed loudly, because the manifest gate did its job: `docs/data/
products.json` no longer matched the hash recorded for it, so every `store` run
since has refused to write it ("committed-drift") and the catalogue has been
frozen at whatever was committed. Had the gate been re-baselined - the obvious
"fix" - the next run would have overwritten the file with the three licences and
silently deleted a ₹999 product from the shop.

So this test asserts the invariant that broke: a product the shop sells is a
product in FOR_SALE, with the fields the store page and the blog need.

    python3 -m unittest discover -s tests -v
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import drsoam  # noqa: E402

REQUIRED = ("id", "title", "category", "type", "price")


class TheCatalogue(unittest.TestCase):
    def test_every_product_carries_the_fields_the_pages_need(self):
        for p in drsoam.store():
            for field in REQUIRED:
                self.assertTrue(p.get(field), "%s is missing %r" % (p.get("id"), field))

    def test_ids_are_unique(self):
        ids = [p["id"] for p in drsoam.store()]
        self.assertEqual(len(ids), len(set(ids)), ids)

    def test_the_ntet_course_is_a_product_of_this_module(self):
        """The regression: it lived only in Matneo's committed JSON for 2 days."""
        p = next((x for x in drsoam.store() if x["id"] == "ntet-homoeopathy-course"), None)
        self.assertIsNotNone(p, "the NTET 2026 course is not in FOR_SALE - a store run "
                                "would delete it from the catalogue")
        self.assertEqual(p["price"], "₹999")
        self.assertEqual(p["link"], "https://drsamonline.github.io/Matneo/ntet/")
        self.assertEqual(p["type"], "paid")

    def test_the_blog_is_derived_from_the_catalogue(self):
        """No product post may exist that the shop does not sell, and none may be missing."""
        posts = drsoam.posts()["posts"]
        self.assertEqual({x["repo"] for x in posts}, {p["id"] for p in drsoam.store()})

    def test_no_buy_link_is_invented(self):
        """PROMPTS/refresh.md: buyLinks stays [] unless the owner supplies one."""
        for p in drsoam.store():
            self.assertEqual(p.get("buyLinks") or [], [], "%s has an invented buy link" % p["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
