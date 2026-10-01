"""brooksrunning.com (Salesforce Commerce Cloud).

The product page lists every colour/width/size as a button and marks the
sold-out ones with an `m-buy-box-grid__btn--sold-out` class. Each button
carries a `data-url` for the site's Product-Variation endpoint, which
returns JSON describing the selected variant, including a `selectable`
flag per size that is false when that size can't be ordered.
"""

from __future__ import annotations

import html as htmlmod
import re
from urllib.parse import urljoin

from ..http import Http
from ..models import Offer, SourceResult, Target

NAME = "Brooks Running"


def check(target: Target, cfg: dict, http: Http) -> SourceResult:
    result = SourceResult(NAME)
    style, color = target.style, target.color_code
    width = {"D": "1D", "B": "1B"}.get(target.width, target.width)  # Brooks spells regular widths '1D'/'1B'
    size = f"{target.size_value:.1f}"  # Brooks spells sizes '12.0'
    page_url = f"{cfg['product_url']}?dwvar_{style}_color={color}&dwvar_{style}_width={width}"

    page = http.get(page_url).text
    buttons = parse_buttons(page)
    if not any(b["type"] == "size" for b in buttons):
        raise RuntimeError("no size buttons on the Brooks product page (layout changed or bot check)")
    if not any(b["type"] == "width" and b["value"] == width for b in buttons):
        result.status = f"Brooks doesn't offer width {width} for this colour"
        return result
    size_button = next((b for b in buttons if b["type"] == "size" and b["value"] == size), None)
    if size_button is None:
        result.status = f"size {size} isn't offered in {width}"
        return result

    variant = None
    if size_button["url"]:
        try:
            variant = http.get_json(
                urljoin(page_url, size_button["url"]),
                {"X-Requested-With": "XMLHttpRequest", "Referer": page_url},
            )
        except Exception as exc:  # the page alone is enough to decide
            print(f"  [brooks] variation lookup failed, using page only: {exc}")

    in_stock, detail = decide(size_button, variant, size)
    buy_url = f"{page_url}&dwvar_{style}_size_Shoe={size}"
    if in_stock:
        result.offers.append(Offer(f"brooks:{style}-{width}-{color}-{size}", NAME, "online", buy_url, detail))
        result.status = f"IN STOCK online ({detail})"
    else:
        result.status = f"sold out online ({detail})"
    return result


def decide(size_button: dict, variant: dict | None, size: str) -> tuple[bool, str]:
    """Combine the page's sold-out marker with the variation JSON."""
    page_says_sold_out = size_button["sold_out"]
    if not variant or "product" not in variant:
        return (not page_says_sold_out, "page: " + ("sold out" if page_says_sold_out else "available"))

    product = variant["product"]
    selectable = None
    for attr in product.get("variationAttributes") or []:
        if str(attr.get("attributeId") or attr.get("id") or "").lower().startswith("size"):
            for value in attr.get("values") or []:
                if str(value.get("value") or value.get("id")) == size:
                    selectable = bool(value.get("selectable"))
    ready = bool(product.get("readyToOrder"))
    messages = ", ".join((product.get("availability") or {}).get("messages") or [])
    price = ((product.get("price") or {}).get("sales") or {}).get("formatted") or ""
    preorder = bool(product.get("isPreorder"))

    in_stock = bool(selectable) and ready and not page_says_sold_out
    bits = [b for b in (price, messages, "pre-order" if preorder else "") if b]
    if not in_stock:
        bits.append(f"selectable={selectable}, readyToOrder={ready}, page sold-out={page_says_sold_out}")
    return in_stock, "; ".join(bits)


_ITEM = re.compile(r'<li class="m-buy-box-grid__item[^"]*"(.*?)</li>', re.S)


def parse_buttons(page: str) -> list[dict]:
    """Size/width/colour buttons from the product page buy box."""
    buttons = []
    for m in _ITEM.finditer(page):
        item = m.group(1)
        kind = _attr(item, "data-variation-type") or _attr(item, "data-attr")
        value = _attr(item, "data-attr-value")
        btn_class = re.search(r'<button class="([^"]*)"', item)
        url = re.search(r"data-url='([^']*)'", item) or re.search(r'data-url="([^"]*)"', item)
        buttons.append(
            {
                "type": kind,
                "value": value,
                "label": _attr(item, "data-event-label"),
                "sold_out": bool(btn_class and "--sold-out" in btn_class.group(1)),
                "url": htmlmod.unescape(url.group(1)) if url else "",
            }
        )
    return buttons


def _attr(chunk: str, name: str) -> str:
    m = re.search(rf'{name}="([^"]*)"', chunk)
    return htmlmod.unescape(m.group(1)) if m else ""
