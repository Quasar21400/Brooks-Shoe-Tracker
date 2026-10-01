"""Canned responses shaped like the real ones captured from each retailer."""

from __future__ import annotations

import json

from shoe_tracker.http import Response
from shoe_tracker.models import Target

TARGET = Target(
    label="Ghost Max 4 12 4E Black",
    model="Ghost Max 4",
    style="110496",
    color_code="020",
    color_name="Black/Black/Ebony",
    size="12",
    width="4E",
    upc="195394886047",
)


class FakeHttp:
    """Answers GETs from a {url-substring: body} map, first match wins."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url, headers=None, ok_statuses=(200,)):
        self.calls.append(url)
        for fragment, body in self.routes.items():
            if fragment in url:
                if isinstance(body, Exception):
                    raise body
                text = body if isinstance(body, str) else json.dumps(body)
                return Response(url, 200, text)
        raise AssertionError(f"unexpected URL {url}")

    def get_json(self, url, headers=None):
        return self.get(url, headers).json()

    def post_json(self, url, payload, headers=None):
        return self.get(url, headers).json()


# -- brooksrunning.com --------------------------------------------------------

def brooks_item(kind: str, value: str, sold_out: bool, label: str | None = None) -> str:
    cls = "m-buy-box-grid__btn" + (" m-buy-box-grid__btn--sold-out" if sold_out else "")
    url = (
        "https://www.brooksrunning.com/on/demandware.store/Sites-BrooksRunning-Site/en_US/Product-Variation"
        f"?dwvar_110496_color=020&amp;dwvar_110496_size_Shoe={value}&amp;dwvar_110496_width=4E&amp;pid=110496&amp;quantity=1"
    )
    return f"""
    <li class="m-buy-box-grid__item js-product-change-item "
        data-event-label="{label or value}" data-variation-type="{kind}">
        <button class="{cls} " aria-current="false"
            data-url='{url}' data-attr="{kind}" data-attr-value="{value}">
            {'<span class="sr-only">SOLD OUT</span>' if sold_out else ''}
        </button>
    </li>"""


def brooks_page(size_12_sold_out: bool, widths=("1D", "2E", "4E")) -> str:
    sizes = "".join(brooks_item("size", s, s == "12.0" and size_12_sold_out) for s in ("11.5", "12.0", "12.5"))
    ws = "".join(brooks_item("width", w, False, f"Width {w}") for w in widths)
    return f"<html><ul>{sizes}</ul><ul>{ws}</ul></html>"


def brooks_variation(selectable: bool, ready: bool) -> dict:
    return {
        "action": "Product-Variation",
        "product": {
            "id": "110496",
            "readyToOrder": ready,
            "available": True,
            "availability": {"messages": ["In Stock"] if ready else []},
            "price": {"sales": {"formatted": "$165.00"}},
            "variationAttributes": [
                {"attributeId": "color", "values": [{"value": "020", "selectable": True, "selected": True}]},
                {"attributeId": "size_Shoe", "values": [
                    {"value": "11.5", "selectable": False},
                    {"value": "12.0", "selectable": selectable, "selected": True},
                ]},
                {"attributeId": "width", "values": [{"value": "4E", "selectable": selectable, "selected": True}]},
            ],
        },
    }


# -- fleetfeet.com --------------------------------------------------------------

def fleet_page(entries: list[dict]) -> str:
    return (
        '<script async src="https://d29g5yx5nppkhx.cloudfront.net/location-data?v=1"></script>\n'
        "<script>\n window.defaultSku = \"110496-1D-004\";\n"
        f" window.productData = {json.dumps(entries)};\n window.productCTA = {{}};\n</script>"
    )


def fleet_entry(sku: str, width: str, name: str, stock_12: list[str]) -> dict:
    return {
        "sku": sku,
        "width": width,
        "name": name,
        "variations": [
            {"upc": "1", "size": "11.5", "stock": ["999"]},
            {"upc": "2", "size": "12", "stock": stock_12},
        ],
    }


FLEET_LOCATIONS = (
    "window.ff_location_data = ["
    '{"id":"1","rics":"100","lat":35.99,"lng":-78.9,"title":"Durham","city":"Durham","state":"NC","phone":"919-555-0100"},'
    '{"id":"2","rics":"200","lat":40.71,"lng":-74.0,"title":"Manhattan","city":"New York","state":"NY","phone":""}'
    "];\nff.trigger('location_data::ready');"
)


# -- Shopify ------------------------------------------------------------------

def shopify_suggest(*products: tuple[str, str]) -> dict:
    return {"resources": {"results": {"products": [{"handle": h, "title": t} for h, t in products]}}}


def shopify_product(handle: str, title: str, option_names: list[str], variants: list[dict]) -> dict:
    out = []
    for i, v in enumerate(variants):
        opts = v["options"]
        out.append({
            "id": 1000 + i,
            "title": " / ".join(opts),
            "option1": opts[0] if len(opts) > 0 else None,
            "option2": opts[1] if len(opts) > 1 else None,
            "option3": opts[2] if len(opts) > 2 else None,
            "available": v.get("available", False),
            "sku": v.get("sku", ""),
            "barcode": v.get("barcode", ""),
            "price": 16495,
        })
    return {"handle": handle, "title": title, "options": [{"name": n} for n in option_names], "variants": out}
