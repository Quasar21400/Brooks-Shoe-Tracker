"""Zappos.

The product page is a Next.js app. Its data arrives in `self.__next_f.push`
script chunks; joined together they contain `allColorVariants`, one entry
per colour with every size/width as a stock item (`isOutOfStock`, `onHand`).
Sold-out sizes are still listed, so "listed but out of stock" is visible.
"""

from __future__ import annotations

import json
import re

from ..http import Http
from ..matching import Matcher, parse_width
from ..models import Offer, SourceResult, Target

NAME = "Zappos"
_PUSH = re.compile(r"self\.__next_f\.push\((\[.*?\])\)</script>", re.S)


def check(target: Target, cfg: dict, http: Http) -> SourceResult:
    result = SourceResult(NAME)
    variants = color_variants(http.get(cfg["product_url"]).text)
    if not variants:
        raise RuntimeError("no stock data on the Zappos page (layout changed or bot check)")

    matcher = Matcher(target)
    color = next((v for v in variants.values() if matcher.color_value_matches(str(v.get("colorName", "")))), None)
    if color is None:
        result.status = f"doesn't sell {target.color_name}"
        return result

    items = [
        item
        for item in color.get("allStockItems") or []
        if isinstance(item, dict)
        and parse_width(str(item.get("width") or "")) == target.width
        and _number(item.get("size")) == target.size_value
    ]
    if not items:
        result.status = f"doesn't list {target.color_name} in {target.width} size {target.size}"
        return result

    url = "https://www.zappos.com" + str(color.get("productUrl") or "")
    in_stock = [i for i in items if not i.get("isOutOfStock") and (_number(i.get("onHand")) or 0) > 0]
    if not in_stock:
        result.status = "listed but out of stock"
        return result
    item = in_stock[0]
    left = int(_number(item.get("onHand")) or 0)
    price = str(item.get("price") or "").replace("$$", "$")
    result.offers.append(
        Offer(f"zappos:{item.get('stockId')}", NAME, "online", url, f"{price} ({left} left)".strip())
    )
    result.status = f"IN STOCK online ({left} left)"
    return result


def color_variants(page: str) -> dict:
    """The `allColorVariants` object from the page's streamed data."""
    chunks = []
    for m in _PUSH.finditer(page):
        try:
            arr = json.loads(m.group(1))
        except json.JSONDecodeError:
            continue
        if len(arr) > 1 and isinstance(arr[1], str):
            chunks.append(arr[1])
    text = "".join(chunks)
    i = text.find('"allColorVariants":')
    if i < 0:
        return {}
    try:
        value, _ = json.JSONDecoder().raw_decode(text, text.index("{", i))
    except (ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
