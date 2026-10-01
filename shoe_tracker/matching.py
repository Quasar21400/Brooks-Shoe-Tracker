"""Recognising the target shoe in retailers' free-form variant data.

Every shop spells things differently: "4E", "4E - Extra Wide", "X-Wide",
"Black - Black - Ebony", "black-ebony", "Size 12", "12.0" ... These helpers
turn those spellings into comparable values.
"""

from __future__ import annotations

import re

from .models import Target

_SIZE = re.compile(r"^\s*(?:size|us|men'?s|m)?\s*(\d{1,2}(?:\.\d)?)\s*(?:us|m)?\s*$", re.I)

# Explicit width codes win over descriptive words: women's "X-Wide 2E" is a 2E.
_WIDTH_CODES = [
    (re.compile(r"\b(?:4E|EEEE|XW|XWIDE)\b"), "4E"),
    (re.compile(r"\b(?:2E|EE)\b"), "2E"),
    (re.compile(r"\b1?D\b"), "D"),
    (re.compile(r"\b(?:2A|1?B)\b"), "B"),
]
_WIDTH_WORDS = [
    (re.compile(r"\b(?:EXTRA|X)[\s-]*WIDE\b"), "4E"),
    (re.compile(r"\bWIDE\b"), "2E"),
    (re.compile(r"\b(?:MEDIUM|REGULAR|STANDARD)\b"), "D"),
]
_WOMENS = re.compile(r"women|wmns|ladies|(?:^|[\s/-])w-", re.I)


def parse_size(value: str | None) -> float | None:
    """'12', '12.0', 'Size 12', 'M 12' -> 12.0. Anything else -> None."""
    m = _SIZE.match(value or "")
    return float(m.group(1)) if m else None


def parse_width(value: str | None) -> str | None:
    """Normalise a width spelling to 'D', '2E', '4E' or 'B'."""
    text = re.sub(r"[_]+", " ", (value or "")).upper()
    for pattern, width in _WIDTH_CODES + _WIDTH_WORDS:
        if pattern.search(text):
            return width
    return None


def slug_width(handle: str) -> str | None:
    """Width spelled out in a URL handle such as 'mens-ghost-max-4-wide-2e-110496-2e-020'."""
    return parse_width(handle.replace("-", " "))


def is_womens(text: str) -> bool:
    return bool(_WOMENS.search(text or ""))


def model_regex(model: str) -> re.Pattern:
    """'Ghost Max 4' matches 'ghost-max-4' and 'GHOST MAX 4' but not 'Ghost Max 45'."""
    words = re.findall(r"[a-z0-9]+", model.lower())
    return re.compile(r"\b" + r"\W*".join(map(re.escape, words)) + r"(?![0-9])", re.I)


def color_regex(color_name: str) -> re.Pattern:
    """'Black/Black/Ebony' matches 'Black - Black - Ebony', 'black-black-ebony'
    and the de-duplicated 'Black/Ebony' some shops use."""
    words = re.findall(r"[a-z]+", color_name.lower())
    parts: list[str] = []
    for i, word in enumerate(words):
        piece = re.escape(word)
        if i and word == words[i - 1]:
            parts.append(rf"(?:\W*{piece})?")
        else:
            parts.append((r"\W*" if parts else "") + piece)
    return re.compile(r"\b" + "".join(parts) + r"\b", re.I)


def style_color_regex(target: Target) -> re.Pattern:
    """Brooks style + color code inside a SKU or handle: '110496-020-12-4E',
    '1104960204E', '110496-4E-020', 'ghost-max-4-110496-4e-020'."""
    return re.compile(rf"{target.style}\W*(?:(?:1D|2E|4E)\W*)?{target.color_code}", re.I)


class Matcher:
    """Decides whether a retailer's product/variant is the target shoe."""

    def __init__(self, target: Target):
        self.target = target
        self.model = model_regex(target.model)
        self.color = color_regex(target.color_name)
        self.style_color = style_color_regex(target)
        self.first_color_word = re.findall(r"[a-z]+", target.color_name.lower())[0]
        self.style_codes = re.compile(rf"{target.style}\W*(?:(?:1D|2E|4E)\W*)?(\d{{3}})", re.I)

    def product_is_candidate(self, title: str, handle: str) -> bool:
        """Cheap filter on search results before fetching a product's variants."""
        if is_womens(f"{title} {handle}"):
            return False
        if not self.model.search(title) and not self.model.search(handle.replace("-", " ")):
            return False
        # Handles such as 'mens-brooks-ghost-max-4-110496-1d-015' name one colourway.
        codes = set(self.style_codes.findall(handle))
        return not codes or self.target.color_code in codes

    def color_value_matches(self, value: str) -> bool:
        """A colour option value. A bare 'Black' counts: shops that shorten
        colour names use it for Black/Black/Ebony."""
        value = (value or "").strip()
        return bool(self.color.search(value)) or value.lower() == self.first_color_word

    def text_mentions_color(self, text: str) -> bool:
        return bool(self.color.search(text or "") or self.style_color.search(text or ""))

    def shopify_variant(self, product: dict, variant: dict) -> bool:
        """True when a Shopify variant is the target size, width and colour."""
        t = self.target
        if t.upc and str(variant.get("barcode") or "") == t.upc:
            return True

        names = [o["name"] if isinstance(o, dict) else str(o) for o in product.get("options", [])]
        values = [variant.get(f"option{i}") for i in (1, 2, 3)]
        options = {n.lower(): v for n, v in zip(names, values) if v}
        tokens = [tok.strip() for tok in str(variant.get("title") or "").split(" / ")]
        handle = product.get("handle", "")
        title = product.get("title", "")
        sku = str(variant.get("sku") or "")

        size_value = _pick(options, "size")
        size_texts = [size_value] if size_value is not None else tokens
        size_ok = any(t.size_value in _sizes_in(text) for text in size_texts)

        width_value = _pick(options, "width") or _pick(options, "fit")
        width = parse_width(width_value) if width_value else None
        if width is None:
            width = next((w for w in map(parse_width, tokens) if w), None)
        if width is None:
            width = slug_width(handle) or parse_width(title)
        width_ok = width == t.width

        color_value = _pick(options, "colo")
        if color_value is not None:
            color_ok = self.color_value_matches(color_value) or bool(self.style_color.search(sku))
        else:
            color_ok = self.text_mentions_color(f"{title} {handle} {variant.get('title', '')} {sku}")

        return size_ok and width_ok and color_ok


def _sizes_in(text: str) -> set[float]:
    """Sizes in '12', 'Size 12' or a combined value like '12 4E'."""
    found = {parse_size(text)} | {parse_size(part) for part in re.split(r"[\s/]+", text or "")}
    found.discard(None)
    return found


def _pick(options: dict, fragment: str):
    return next((v for name, v in options.items() if fragment in name), None)
