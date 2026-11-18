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
        """PROMPTS/refresh.md: a buy link exists only when the OWNER supplied one.

        This used to assert `buyLinks == []` for every product, which was the right
        rule written in the only way it could be checked while nothing was for sale:
        absence. The six books broke that shape without breaking the rule - their
        links are the owner's own Amazon listings (added 2026-11-15 in bc3db23,
        fbe2725, 1b637e3, each with the ASIN the owner published) - so the assertion
        now states the rule instead of the absence.

        What is checkable: a link must be the canonical Amazon listing OF THIS
        PRODUCT'S OWN ASIN. A fabricated URL does not match the ASIN on the entry,
        and a URL pointing at somebody else's book is not this product's link. The
        ASIN itself is the owner's claim and cannot be checked from here - which is
        the honest limit, and why the field is asserted to exist rather than trusted.
        """
        for p in drsoam.store():
            links = p.get("buyLinks") or []
            if not links:
                continue
            asin = p.get("asin")
            self.assertTrue(asin, "%s has a buy link but no asin to check it against"
                            % p["id"])
            for link in links:
                self.assertTrue(link.get("url"), "%s: buyLink without url" % p["id"])
                self.assertEqual(
                    link["url"], "https://www.amazon.com/dp/%s" % asin,
                    "%s: buy link is not the listing of its own asin (%s)"
                    % (p["id"], asin))

    def test_the_six_books_are_products_of_this_module(self):
        """The second regression, and the same failure as NTET one level down.

        The books were written into Matneo's docs/data/products.json by hand on
        2026-11-15 (bc3db23, fbe2725, 1b637e3) and were deleted from the live
        catalogue four hours later by the next `store` run (b381218), which is
        exactly what FOR_SALE-only generation does to anything that is not in
        FOR_SALE. Their ids are pinned here so the deletion cannot recur quietly.
        """
        books = {p["id"]: p for p in drsoam.store() if p.get("type") == "book"}
        self.assertEqual(
            set(books),
            {"book-open-materia-medica", "book-open-materia-medica-paperback",
             "book-clinical-governance-manual", "book-the-unbroken",
             "book-whispers-in-the-rain", "book-9-shorts"})
        for pid, b in books.items():
            self.assertEqual(b["type"], "book", pid)
            self.assertIn(b.get("format"), ("ebook", "paperback"), pid)
            self.assertTrue(b.get("asin"), "%s needs the asin it is sold under" % pid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
