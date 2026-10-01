import unittest

from shoe_tracker.matching import Matcher, color_regex, model_regex, parse_size, parse_width

from .fakes import TARGET, shopify_product


class ParseTests(unittest.TestCase):
    def test_sizes(self):
        for text, expected in [("12", 12.0), ("12.0", 12.0), ("Size 12", 12.0), ("12.5", 12.5), ("M 12", 12.0)]:
            self.assertEqual(parse_size(text), expected, text)
        for text in ("4E", "Black/Black/Ebony", "", None, "112"):
            self.assertIsNone(parse_size(text), text)

    def test_widths(self):
        cases = {
            "4E": "4E", "4E - Extra Wide": "4E", "Extra Wide (4E)": "4E", "X-Wide": "4E", "EEEE": "4E",
            "2E": "2E", "EE - Wide": "2E", "Wide 2E": "2E", "Wide": "2E", "X-Wide 2E": "2E",
            "D": "D", "1D": "D", "D - Medium": "D", "Medium D": "D", "Regular": "D", "Medium B": "B",
        }
        for text, expected in cases.items():
            self.assertEqual(parse_width(text), expected, text)
        for text in ("Black/Black/Ebony", "12", "Grey - Grey - Ebony", "Like New"):
            self.assertIsNone(parse_width(text), text)

    def test_color(self):
        rx = color_regex("Black/Black/Ebony")
        for text in ("Black/Black/Ebony", "Black - Black - Ebony", "BLACK / BLACK / EBONY",
                     "mens-brooks-ghost-max-4-black-black-ebony", "brooks-ghost-max-4-mens-black-ebony",
                     "brooks-blackblackebony-ghost-max-4-mens"):
            self.assertTrue(rx.search(text), text)
        for text in ("Grey/Grey/Ebony", "Black/Folkstone/Open Air", "Black - Graphite - Grey"):
            self.assertFalse(rx.search(text), text)

    def test_model(self):
        rx = model_regex("Ghost Max 4")
        self.assertTrue(rx.search("Men's Brooks Ghost Max 4"))
        self.assertTrue(rx.search("mens brooks ghost max 4 black"))
        self.assertFalse(rx.search("Brooks Ghost Max 3"))
        self.assertFalse(rx.search("ghost max 45"))


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(TARGET)

    def test_filters_search_results(self):
        self.assertTrue(self.m.product_is_candidate("Men's Brooks Ghost Max 4", "mens-brooks-ghost-max-4-black-black-ebony"))
        self.assertTrue(self.m.product_is_candidate("Brooks Ghost Max 4", "brooks-ghost-max-4-mens"))
        self.assertTrue(self.m.product_is_candidate("x", "mens-brooks-ghost-max-4-extra-wide-4e-110496-4e-020"))
        self.assertFalse(self.m.product_is_candidate("Women's Brooks Ghost Max 4", "womens-brooks-ghost-max-4"))
        self.assertFalse(self.m.product_is_candidate("Ghost Max 4", "w-ghost-max-4-b-black-black-ebony"))
        self.assertFalse(self.m.product_is_candidate("Brooks Ghost Max 3", "brooks-ghost-max-3"))
        # One-colourway pages for a different colour are skipped.
        self.assertFalse(self.m.product_is_candidate("Men's Brooks Ghost Max 4", "mens-brooks-ghost-max-4-110496-1d-015"))


class ShopifyVariantTests(unittest.TestCase):
    def setUp(self):
        self.m = Matcher(TARGET)

    def matches(self, product):
        return [v["title"] for v in product["variants"] if self.m.shopify_variant(product, v)]

    def test_fit2run_style(self):  # Color / width / Size options on one product
        p = shopify_product("brooks-ghost-max-4-mens", "Brooks Ghost Max 4", ["Color", "width", "Size"], [
            {"options": ["Black - Black - Ebony", "4E", "12"]},
            {"options": ["Black - Black - Ebony", "4E", "12.5"]},
            {"options": ["Black - Black - Ebony", "2E", "12"]},
            {"options": ["Grey - Grey - Ebony", "4E", "12"]},
        ])
        self.assertEqual(self.matches(p), ["Black - Black - Ebony / 4E / 12"])

    def test_pacers_style(self):  # Size / Color / Width, colour also in the handle
        p = shopify_product("mens-brooks-ghost-max-4-black-black-ebony", "Men's Brooks Ghost Max 4", ["Size", "Color", "Width"], [
            {"options": ["12", "Black/Black/Ebony", "D"]},
            {"options": ["12", "Black/Black/Ebony", "2E"]},
        ])
        self.assertEqual(self.matches(p), [])

    def test_runners_plus_style(self):  # "Shoe fit" with X-Wide
        p = shopify_product("mens-brooks-ghost-max-4", "Men's Brooks Ghost Max 4", ["Color", "Shoe fit", "Shoe size"], [
            {"options": ["Black/Black/Ebony", "X-Wide", "12"]},
            {"options": ["Black/Black/Ebony", "Wide", "12"]},
            {"options": ["Grey/Grey/Ebony", "X-Wide", "12"]},
        ])
        self.assertEqual(self.matches(p), ["Black/Black/Ebony / X-Wide / 12"])

    def test_holabird_style(self):  # colour only in the handle, width spelled out
        p = shopify_product("brooks-ghost-max-4-mens-black-ebony", "Brooks Ghost Max 4 Men's Black Ebony", ["Size", "Width"], [
            {"options": ["12", "4E - Extra Wide"]},
            {"options": ["12", "EE - Wide"]},
        ])
        self.assertEqual(self.matches(p), ["12 / 4E - Extra Wide"])

    def test_lukes_locker_short_colour_names(self):
        p = shopify_product("ghost-max-42", "Men's Ghost Max 4", ["Color", "Size", "Width"], [
            {"options": ["Black", "12", "4E"]},
            {"options": ["Black/Folkstone", "12", "4E"]},
        ])
        self.assertEqual(self.matches(p), ["Black / 12 / 4E"])

    def test_width_in_handle_only(self):  # Gazelle / Potomac: one page per width
        p = shopify_product("m-ghost-max-4-4e-black-black-ebony", "Ghost Max 4", ["Size"], [
            {"options": ["12"]}, {"options": ["12.5"]},
        ])
        self.assertEqual(self.matches(p), ["12"])
        p2 = shopify_product("m-ghost-max-4-2e-black-black-ebony", "Ghost Max 4", ["Size"], [{"options": ["12"]}])
        self.assertEqual(self.matches(p2), [])

    def test_upc_match_wins(self):
        p = shopify_product("anything", "Brooks shoe", ["Title"], [{"options": ["Default Title"], "barcode": "195394886047"}])
        self.assertEqual(self.matches(p), ["Default Title"])


if __name__ == "__main__":
    unittest.main()
