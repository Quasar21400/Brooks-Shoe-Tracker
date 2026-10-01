from __future__ import annotations

import math
from dataclasses import dataclass

from .http import Http


@dataclass
class Home:
    lat: float
    lng: float
    radius_miles: float
    label: str


def distance_miles(home: Home, lat: float, lng: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(home.lat), math.radians(lat)
    dp, dl = p2 - p1, math.radians(lng - home.lng)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_home(cfg: dict, http: Http) -> Home | None:
    """Home location from config: explicit lat/lng, or a US ZIP code."""
    radius = float(cfg.get("radius_miles") or 0)
    if cfg.get("lat") not in (None, "") and cfg.get("lng") not in (None, ""):
        return Home(float(cfg["lat"]), float(cfg["lng"]), radius, f"{cfg['lat']},{cfg['lng']}")
    zip_code = str(cfg.get("zip") or "").strip()
    if not zip_code:
        return None
    try:
        place = http.get_json(f"https://api.zippopotam.us/us/{zip_code}")["places"][0]
    except Exception as exc:
        print(f"  [location] couldn't look up ZIP {zip_code}: {exc}; showing stores everywhere")
        return None
    return Home(float(place["latitude"]), float(place["longitude"]), radius, zip_code)
