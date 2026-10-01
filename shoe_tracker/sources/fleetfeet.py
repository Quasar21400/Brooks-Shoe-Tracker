"""Fleet Feet: 250+ US stores, per-store stock published on the product page.

The product page embeds `window.productData`, one entry per colour/width SKU
(e.g. '110496-2E-020'), each with sizes and a `stock` list of store ids
("rics"). `window.ff_location_data`, loaded from a separate script, maps
those ids to store names, addresses and coordinates.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from .. import geo
from ..http import Http
from ..matching import Matcher, parse_width
from ..models import Offer, SourceResult, Target

NAME = "Fleet Feet"
LIST_LIMIT = 8


def check(target: Target, cfg: dict, http: Http, home: geo.Home | None = None) -> SourceResult:
    result = SourceResult(NAME)
    page_url = cfg["product_url"]
    page = http.get(page_url).text
    products = extract_js_value(page, "window.productData")
    if not isinstance(products, list) or not products:
        raise RuntimeError("window.productData missing from the Fleet Feet page (layout changed?)")

    entry = find_sku(products, target)
    if entry is None:
        carried = sorted({p.get("width") or "?" for p in products if Matcher(target).text_mentions_color(p.get("name", ""))})
        result.status = (
            f"doesn't list {target.style}-{target.width}-{target.color_code} "
            f"(carries this colour in widths: {', '.join(carried) or 'none'})"
        )
        return result

    size = next((v for v in entry.get("variations", []) if _size(v.get("size")) == target.size_value), None)
    stock_ids = [str(s) for s in (size or {}).get("stock") or []]
    if not stock_ids:
        result.status = f"lists {entry['sku']} but size {target.size} is out of stock at every store"
        return result

    locations = load_locations(page, page_url, http)
    stores = []
    for rics in stock_ids:
        loc = locations.get(rics)
        miles = geo.distance_miles(home, loc["lat"], loc["lng"]) if (home and loc and loc.get("lat") is not None) else None
        stores.append((rics, loc, miles))
    stores.sort(key=lambda s: (s[2] if s[2] is not None else 1e9, _store_name(s[0], s[1])))

    radius = home.radius_miles if home else 0
    nearby = [s for s in stores if home and radius and s[2] is not None and s[2] <= radius]
    for rics, loc, miles in nearby:
        result.offers.append(
            Offer(f"fleetfeet:{rics}", f"Fleet Feet {_store_name(rics, loc)}", _where(loc, miles), page_url, _phone(loc))
        )
    others = [s for s in stores if s not in nearby]
    if others:
        listing = "; ".join(_short(r, l, m) for r, l, m in others[:LIST_LIMIT])
        if len(others) > LIST_LIMIT:
            listing += f"; +{len(others) - LIST_LIMIT} more"
        label = "other Fleet Feet stores" if nearby else "Fleet Feet stores"
        result.offers.append(
            Offer(
                "fleetfeet:elsewhere" if home and radius else "fleetfeet:any",
                NAME,
                f"{len(others)} {label}",
                page_url,
                f"call a store or order online. {listing}",
            )
        )
    result.status = f"IN STOCK at {len(stores)} store(s)" + (f", {len(nearby)} within {radius:g} mi" if nearby else "")
    return result


def find_sku(products: list[dict], target: Target) -> dict | None:
    wanted = f"{target.style}-{'1D' if target.width == 'D' else target.width}-{target.color_code}".upper()
    for p in products:
        if str(p.get("sku", "")).upper() == wanted:
            return p
    matcher = Matcher(target)
    for p in products:
        if parse_width(p.get("width")) == target.width and matcher.text_mentions_color(p.get("name", "")):
            return p
    return None


def load_locations(page: str, page_url: str, http: Http) -> dict[str, dict]:
    m = re.search(r'src="([^"]*location-data[^"]*)"', page)
    if not m:
        return {}
    try:
        script = http.get(urljoin(page_url, m.group(1))).text
        data = extract_js_value(script, "window.ff_location_data") or []
    except Exception as exc:
        print(f"  [fleetfeet] store list unavailable: {exc}")
        return {}
    return {str(loc.get("rics")): loc for loc in data if loc.get("rics")}


def extract_js_value(text: str, name: str):
    """Parse the JSON literal assigned to `name` in inline JavaScript."""
    m = re.search(re.escape(name) + r"\s*=\s*", text)
    if not m:
        return None
    try:
        value, _ = json.JSONDecoder().raw_decode(text, m.end())
    except json.JSONDecodeError:
        return None
    return value


def _size(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _store_name(rics: str, loc: dict | None) -> str:
    if not loc:
        return f"location #{rics}"
    return loc.get("title") or loc.get("label") or rics


def _where(loc: dict | None, miles: float | None) -> str:
    if not loc:
        return "in store"
    place = ", ".join(x for x in (loc.get("city"), loc.get("state")) if x)
    dist = f", {miles:.0f} mi" if miles is not None else ""
    return f"in store: {place}{dist}"


def _short(rics: str, loc: dict | None, miles: float | None) -> str:
    """'Durham (Durham, NC, 12 mi)' for the one-line list of far-away stores."""
    details = [", ".join(x for x in ((loc or {}).get("city"), (loc or {}).get("state")) if x)]
    if miles is not None:
        details.append(f"{miles:.0f} mi")
    details = [d for d in details if d]
    return _store_name(rics, loc) + (f" ({', '.join(details)})" if details else "")


def _phone(loc: dict | None) -> str:
    return f"call {loc['phone']}" if loc and loc.get("phone") else ""
