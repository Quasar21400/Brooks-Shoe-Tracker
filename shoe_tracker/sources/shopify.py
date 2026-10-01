"""Independent running shops on Shopify.

Every Shopify store answers `/search/suggest.json` (product search) and
`/products/<handle>.js` (a product with its variants and an `available`
flag per variant), so one checker covers them all. Search runs every time,
so a new colourway or width page added by the shop is picked up.

`.js` lists at most 250 variants. Bigger products (Fit2Run puts every colour
and width on one page) are read through the tokenless Storefront GraphQL API,
which pages through all of them.
"""

from __future__ import annotations

import time
from urllib.parse import quote

from ..http import Http
from ..matching import Matcher
from ..models import Offer, SourceResult, Target

SHOPIFY_VARIANT_CAP = 250  # /products/<handle>.js lists at most this many variants
STOREFRONT_API = "https://{domain}/api/2025-07/graphql.json"
VARIANTS_QUERY = """
query($handle: String!, $after: String) {
  product(handle: $handle) {
    variants(first: 250, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { id title availableForSale sku barcode price { amount } selectedOptions { name value } }
    }
  }
}"""


def check(target: Target, store: dict, search: str, http: Http) -> SourceResult:
    name, domain = store["name"], store["domain"]
    result = SourceResult(name)
    matcher = Matcher(target)

    handles: list[str] = list(store.get("handles") or [])
    suggest = http.get_json(
        f"https://{domain}/search/suggest.json?q={quote(search)}"
        "&resources[type]=product&resources[limit]=10"
    )
    for product in suggest["resources"]["results"]["products"]:
        handle = product.get("handle", "")
        if handle not in handles and matcher.product_is_candidate(product.get("title", ""), handle):
            handles.append(handle)

    listed: list[tuple[dict, dict]] = []
    capped: list[str] = []
    for handle in handles:
        time.sleep(0.5)
        product = http.get_json(f"https://{domain}/products/{handle}.js")
        if len(product.get("variants") or []) >= SHOPIFY_VARIANT_CAP:
            try:
                product = {**product, **all_variants(domain, handle, http)}
            except Exception as exc:
                print(f"  [{domain}] full variant list unavailable: {exc}")
                capped.append(handle)
        listed += [(product, v) for v in product.get("variants") or [] if matcher.shopify_variant(product, v)]

    for product, variant in listed:
        if variant.get("available"):
            url = f"https://{domain}/products/{product['handle']}?variant={variant['id']}"
            price = f"${int(variant.get('price') or 0) / 100:.2f}" if variant.get("price") else ""
            result.offers.append(
                Offer(f"shopify:{domain}:{variant['id']}", name, "online", url, f"{price} {variant.get('title', '')}".strip())
            )

    if result.offers:
        result.status = f"IN STOCK ({len(result.offers)} listing(s))"
    elif listed:
        result.status = "listed but sold out"
    else:
        result.status = f"not listed ({len(handles)} matching product page(s) checked)"
    if capped and not result.offers:
        result.status += f"; {', '.join(capped)} has {SHOPIFY_VARIANT_CAP}+ variants, the rest aren't visible"
    return result


def all_variants(domain: str, handle: str, http: Http) -> dict:
    """Every variant of a product via the Storefront API, in `.js` shape."""
    variants, names, after = [], [], None
    for _ in range(20):
        data = http.post_json(STOREFRONT_API.format(domain=domain), {"query": VARIANTS_QUERY, "variables": {"handle": handle, "after": after}})
        if data.get("errors"):
            raise RuntimeError(str(data["errors"])[:200])
        page = data["data"]["product"]["variants"]
        for node in page["nodes"]:
            opts = node.get("selectedOptions") or []
            names = names or [o["name"] for o in opts]
            variant = {
                "id": node["id"].rsplit("/", 1)[-1],
                "title": node.get("title", ""),
                "available": bool(node.get("availableForSale")),
                "sku": node.get("sku") or "",
                "barcode": node.get("barcode") or "",
                "price": round(float((node.get("price") or {}).get("amount") or 0) * 100),
            }
            for i, opt in enumerate(opts[:3], start=1):
                variant[f"option{i}"] = opt["value"]
            variants.append(variant)
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return {"options": [{"name": n} for n in names], "variants": variants}
