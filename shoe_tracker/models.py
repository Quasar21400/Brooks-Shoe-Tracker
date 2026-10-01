from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    """The exact shoe we are hunting for."""

    label: str
    model: str
    style: str
    color_code: str
    color_name: str
    size: str
    width: str
    upc: str = ""

    @property
    def size_value(self) -> float:
        return float(self.size)


@dataclass
class Offer:
    """One place the shoe can be bought right now."""

    key: str  # stable id, used to tell new stock from stock we already reported
    retailer: str
    where: str  # "online", "in store: Durham, NC (8 mi)", ...
    url: str
    note: str = ""

    def line(self) -> str:
        parts = [f"{self.retailer} ({self.where})"]
        if self.note:
            parts.append(self.note)
        return " - ".join(parts) + f"\n  {self.url}"


@dataclass
class SourceResult:
    name: str
    status: str = ""
    offers: list[Offer] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None
