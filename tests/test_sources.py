import unittest
from unittest import mock

from shoe_tracker import geo
from shoe_tracker.sources import brooks, fleetfeet, shopify, zappos

from .fakes import (
    FLEET_LOCATIONS,
    TARGET,
    FakeHttp,
    brooks_page,
    brooks_variation,
    fleet_entry,
    fleet_page,
    pickup_section,
    shopify_product,
    shopify_suggest,
    zappos_page,
)

BROOKS_CFG = {"product_url": "https://www.brooksrunning.com/en_us/mens/shoes/road-running-shoes/ghost-max-4/110496.html"}
FLEET_CFG = {"product_url": "https://www.fleetfeet.com/products/mens-brooks-ghost-max-4"}


class BrooksTests(unittest.TestCase):
    def run_check(self, page, variation):
        http = FakeHttp({"Product-Variation": variation, "110496.html": page})
        return brooks.check(TARGET, BROOKS_CFG, http), http

    def test_sold_out(self):
        result, http = self.run_check(brooks_page(size_12_sold_out=True), brooks_variation(False, False))
        self.assertEqual(result.offers, [])
        self.assertIn("sold out", result.status)
        self.assertIn("dwvar_110496_size_Shoe=12.0", http.calls[1])
        self.assertNotIn("&amp;", http.calls[1])

    def test_in_stock(self):
        result, _ = self.run_check(brooks_page(size_12_sold_out=False), brooks_variation(True, True))
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].where, "online")
        self.assertIn("$165.00", result.offers[0].note)

    def test_page_and_json_disagree_means_not_in_stock(self):
        result, _ = self.run_check(brooks_page(size_12_sold_out=True), brooks_variation(True, True))
        self.assertEqual(result.offers, [])

    def test_falls_back_to_page_when_json_fails(self):
        result, _ = self.run_check(brooks_page(size_12_sold_out=False), RuntimeError("410"))
        self.assertEqual(len(result.offers), 1)

    def test_width_not_offered(self):
        result, _ = self.run_check(brooks_page(True, widths=("1D", "2E")), brooks_variation(False, False))
        self.assertIn("doesn't offer width 4E", result.status)

    def test_blocked_page_raises(self):
        with self.assertRaises(RuntimeError):
            self.run_check("<html>Access Denied</html>", {})


class FleetFeetTests(unittest.TestCase):
    ENTRIES_NO_4E = [
        fleet_entry("110496-1D-020", "D", "BLACK / BLACK / EBONY", ["100"]),
        fleet_entry("110496-2E-020", "2E", "WIDE -- BLACK / BLACK / EBONY", ["100"]),
    ]

    def check(self, entries, home=None):
        http = FakeHttp({"location-data": FLEET_LOCATIONS, "fleetfeet.com/products": fleet_page(entries)})
        return fleetfeet.check(TARGET, FLEET_CFG, http, home)

    def test_not_listed(self):
        result = self.check(self.ENTRIES_NO_4E)
        self.assertEqual(result.offers, [])
        self.assertIn("110496-4E-020", result.status)
        self.assertIn("2E, D", result.status)

    def test_listed_but_no_stock(self):
        result = self.check(self.ENTRIES_NO_4E + [fleet_entry("110496-4E-020", "4E", "XWIDE -- BLACK / BLACK / EBONY", [])])
        self.assertEqual(result.offers, [])
        self.assertIn("out of stock", result.status)

    def test_in_stock_without_home(self):
        result = self.check(self.ENTRIES_NO_4E + [fleet_entry("110496-4E-020", "4E", "X", ["100", "200"])])
        self.assertEqual([o.key for o in result.offers], ["fleetfeet:any"])
        self.assertIn("Durham", result.offers[0].note)
        self.assertIn("Manhattan", result.offers[0].note)

    def test_in_stock_near_home(self):
        home = geo.Home(35.91, -79.05, 50, "27510")  # Chapel Hill: Durham is ~10 mi, NYC ~430 mi
        result = self.check(self.ENTRIES_NO_4E + [fleet_entry("110496-4E-020", "4E", "X", ["200", "100", "555"])], home)
        keys = [o.key for o in result.offers]
        self.assertEqual(keys, ["fleetfeet:100"])  # stores outside the radius never alert
        self.assertIn("Durham, NC", result.offers[0].where)
        self.assertIn("919-555-0100", result.offers[0].note)
        self.assertIn("2 farther away", result.status)
        self.assertIn("Manhattan", result.status)

    def test_missing_product_data_raises(self):
        with self.assertRaises(RuntimeError):
            self.check([])


class ShopifyTests(unittest.TestCase):
    STORE = {"name": "Some Shop", "domain": "shop.example"}

    def check(self, available):
        product = shopify_product("brooks-ghost-max-4-mens", "Brooks Ghost Max 4", ["Color", "width", "Size"], [
            {"options": ["Black - Black - Ebony", "4E", "12"], "available": available},
            {"options": ["Black - Black - Ebony", "D", "12"], "available": True},
        ])
        http = FakeHttp({
            "suggest.json": shopify_suggest(("brooks-ghost-max-4-mens", "Brooks Ghost Max 4"),
                                             ("brooks-ghost-max-4-womens", "Women's Brooks Ghost Max 4")),
            "/products/brooks-ghost-max-4-mens.js": product,
        })
        with mock.patch.object(shopify.time, "sleep"):
            return shopify.check(TARGET, self.STORE, "ghost max 4", http), http

    def test_in_stock(self):
        result, http = self.check(True)
        self.assertEqual(len(result.offers), 1)
        self.assertIn("?variant=1000", result.offers[0].url)
        self.assertFalse(any("womens" in c for c in http.calls))

    def test_listed_but_sold_out(self):
        result, _ = self.check(False)
        self.assertEqual(result.offers, [])
        self.assertEqual(result.status, "listed but sold out")

    def test_products_over_250_variants_use_storefront_api(self):
        filler = [{"options": ["Grey - Grey - Ebony", "D", str(i)]} for i in range(250)]
        product = shopify_product("brooks-ghost-max-4-mens", "Brooks Ghost Max 4", ["Color", "width", "Size"], filler)
        node = {
            "id": "gid://shopify/ProductVariant/777", "title": "Black - Black - Ebony / 4E / 12",
            "availableForSale": True, "sku": "110496020124E", "barcode": "", "price": {"amount": "164.95"},
            "selectedOptions": [{"name": "Color", "value": "Black - Black - Ebony"}, {"name": "width", "value": "4E"}, {"name": "Size", "value": "12"}],
        }
        graphql = {"data": {"product": {"variants": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [node]}}}}
        http = FakeHttp({
            "suggest.json": shopify_suggest(("brooks-ghost-max-4-mens", "Brooks Ghost Max 4")),
            "/products/brooks-ghost-max-4-mens.js": product,
            "/api/": graphql,
        })
        with mock.patch.object(shopify.time, "sleep"):
            result = shopify.check(TARGET, self.STORE, "ghost max 4", http)
        self.assertEqual([o.key for o in result.offers], ["shopify:shop.example:777"])
        self.assertIn("$164.95", result.offers[0].note)


class ZapposTests(unittest.TestCase):
    CFG = {"product_url": "https://www.zappos.com/p/brooks-ghost-max-4/product/10048552"}

    def test_listed_but_out_of_stock(self):
        result = zappos.check(TARGET, self.CFG, FakeHttp({"zappos.com": zappos_page(0)}))
        self.assertEqual(result.offers, [])
        self.assertEqual(result.status, "listed but out of stock")

    def test_in_stock(self):
        result = zappos.check(TARGET, self.CFG, FakeHttp({"zappos.com": zappos_page(4)}))
        self.assertEqual(len(result.offers), 1)
        self.assertEqual(result.offers[0].url, "https://www.zappos.com/product/10048552/color/683936")
        self.assertIn("$164.95 (4 left)", result.offers[0].note)

    def test_page_without_stock_data_raises(self):
        with self.assertRaises(RuntimeError):
            zappos.check(TARGET, self.CFG, FakeHttp({"zappos.com": "<html>blocked</html>"}))


class PickupTests(unittest.TestCase):
    SECTION = pickup_section([
        ("Fit2Run Tampa International", True, ["2223 N West Shr Blvd", "Unit B230", "Tampa FL 33607"]),
        ("Fit2Run Aventura", True, ["19505 Biscayne Blvd", "Ste 3260", "Aventura FL 33180"]),
        ("Fit2Run Coconut Creek", False, ["4443 Lyons Rd", "Coconut Creek FL 33073"]),
    ])

    def test_parse(self):
        stores = shopify.parse_pickup(self.SECTION)
        self.assertEqual([s["name"] for s in stores], ["Fit2Run Tampa International", "Fit2Run Aventura", "Fit2Run Coconut Creek"])
        self.assertEqual([s["available"] for s in stores], [True, True, False])
        self.assertEqual([s["zip"] for s in stores], ["33607", "33180", "33073"])  # not the 5-digit street number

    def test_only_nearby_stores_with_stock_alert(self):
        geo._ZIP_CACHE.clear()
        http = FakeHttp({
            "pickup-availability": self.SECTION,
            "zippopotam.us/us/33607": {"places": [{"latitude": "27.96", "longitude": "-82.52"}]},
            "zippopotam.us/us/33180": {"places": [{"latitude": "25.96", "longitude": "-80.14"}]},
        })
        home = geo.Home(25.9974, -80.3248, 40, "33027")
        offers = shopify.nearby_pickup("www.fit2run.com", "Fit2Run (FL)", 77, "https://x", http, home)
        self.assertEqual([o.retailer for o in offers], ["Fit2Run (FL): Fit2Run Aventura"])
        self.assertEqual(offers[0].where, "in store, 12 mi")
        self.assertFalse(any("33073" in c for c in http.calls))  # sold-out stores aren't looked up


if __name__ == "__main__":
    unittest.main()
