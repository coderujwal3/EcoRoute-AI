from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import httpx

NOMINATIM_URL = os.getenv("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
OSRM_BASE_URL = os.getenv("OSRM_BASE_URL", "https://router.project-osrm.org")
APP_USER_AGENT = os.getenv(
    "ECOROUTE_USER_AGENT",
    "EcoRouteAI/1.0 (educational sustainability prototype; set ECOROUTE_USER_AGENT to your contact URL/email)",
)
REQUEST_TIMEOUT = float(os.getenv("ROUTING_TIMEOUT_SECONDS", "15"))

_nominatim_lock = threading.Lock()
_last_nominatim_request = 0.0


@dataclass(frozen=True)
class Coordinates:
    lat: float
    lon: float
    display_name: str


@dataclass(frozen=True)
class RoutedOption:
    mode: str
    profile: str
    distance_km: float
    duration_min: int
    geometry: dict[str, Any] | None
    source: str


class RoutingError(RuntimeError):
    pass


# Local, deterministic demo places. The demo mode is deliberately self-contained so
# a classroom/demo run does not depend on internet connectivity.
DEMO_PLACES: dict[str, Coordinates] = {
    "mohansarai": Coordinates(25.2428, 82.9148, "Mohansarai, Varanasi (demo)"),
    "jagatpur": Coordinates(25.2508, 82.9254, "Jagatpur, Varanasi (demo)"),
    "rohania": Coordinates(25.2617, 82.9368, "Rohania, Varanasi (demo)"),
    "pac": Coordinates(25.2722, 82.9470, "PAC, Varanasi (demo)"),
    "maduadih": Coordinates(25.2943, 82.9850, "Maduadih, Varanasi (demo)"),
    "dlw chauraha": Coordinates(25.3005, 82.9819, "DLW Chauraha, Varanasi (demo)"),
    "sundarpur": Coordinates(25.2815, 82.9970, "Sundarpur, Varanasi (demo)"),
    "lanka": Coordinates(25.2665, 82.9908, "Lanka, Varanasi (demo)"),
    "kashi institute of technology": Coordinates(25.2849158, 82.7908485, "Kashi Institute of Technology, Varanasi (demo)"),
    "varanasi cantt": Coordinates(25.3275678, 82.986245, "Varanasi Cantt, Varanasi (demo)"),
}


def _normalize_demo_query(query: str) -> str:
    value = re.sub(r"\s+", " ", query.strip().lower())
    value = re.sub(r",\s*(varanasi|india)$", "", value)
    return value


def _haversine_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = __import__("math").radians(lat1), __import__("math").radians(lat2)
    dp = __import__("math").radians(lat2 - lat1)
    dl = __import__("math").radians(lon2 - lon1)
    x = __import__("math").sin(dp / 2) ** 2 + __import__("math").cos(p1) * __import__("math").cos(p2) * __import__("math").sin(dl / 2) ** 2
    return r * 2 * __import__("math").asin(__import__("math").sqrt(x))


def _demo_geocode(query: str) -> Coordinates:
    key = _normalize_demo_query(query)
    if key in DEMO_PLACES:
        return DEMO_PLACES[key]
    for candidate, coord in DEMO_PLACES.items():
        if candidate in key or key in candidate:
            return coord
    raise RoutingError(
        "Demo mode supports the bundled Varanasi places: Mohansarai, Jagatpur, Rohania, PAC, "
        "Maduadih, DLW Chauraha, Sundarpur, Lanka, Kashi Institute of Technology, and Varanasi Cantt."
    )


def _demo_route(profile: str, origin: Coordinates, destination: Coordinates) -> RoutedOption:
    # Deliberately approximate demo routes. They are not road-network navigation.
    direct_km = _haversine_between(origin.lat, origin.lon, destination.lat, destination.lon)
    detour_factor = {"foot": 1.18, "bike": 1.12, "car": 1.25}.get(profile, 1.2)
    speed_kmph = {"foot": 5.0, "bike": 16.0, "car": 28.0}.get(profile, 20.0)
    distance_km = max(0.1, direct_km * detour_factor)
    duration_min = max(1, round(distance_km / speed_kmph * 60))
    geometry = {"type": "LineString", "coordinates": [[origin.lon, origin.lat], [destination.lon, destination.lat]]}
    return RoutedOption(
        mode={"foot": "Walking", "bike": "Cycling", "car": "Car"}.get(profile, profile.title()),
        profile=profile,
        distance_km=round(distance_km, 2),
        duration_min=duration_min,
        geometry=geometry,
        source="EcoRoute local demo routing estimate",
    )


def _nominatim_get(params: dict[str, str | int]) -> list[dict[str, Any]]:
    global _last_nominatim_request
    with _nominatim_lock:
        wait = 1.0 - (time.monotonic() - _last_nominatim_request)
        if wait > 0:
            time.sleep(wait)
        try:
            headers = {"User-Agent": APP_USER_AGENT, "Accept": "application/json"}
            with httpx.Client(timeout=REQUEST_TIMEOUT, headers=headers, follow_redirects=True) as client:
                response = client.get(NOMINATIM_URL, params=params)
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise RoutingError(f"Geocoding service unavailable: {exc}") from exc
        _last_nominatim_request = time.monotonic()
    if not isinstance(data, list):
        raise RoutingError("Unexpected geocoding response.")
    return data


@lru_cache(maxsize=256)
def geocode(query: str, demo_mode: bool = False) -> Coordinates:
    if demo_mode:
        return _demo_geocode(query)
    results = _nominatim_get({"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "in"})
    if not results:
        results = _nominatim_get({"q": query, "format": "jsonv2", "limit": 1})
    if not results:
        raise RoutingError(f"Could not find a location for '{query}'. Try a more specific place/address.")
    item = results[0]
    try:
        return Coordinates(float(item["lat"]), float(item["lon"]), str(item.get("display_name", query)))
    except (KeyError, TypeError, ValueError) as exc:
        raise RoutingError(f"Invalid geocoding response for '{query}'.") from exc


def route(profile: str, origin: Coordinates, destination: Coordinates, demo_mode: bool = False) -> RoutedOption:
    if demo_mode:
        return _demo_route(profile, origin, destination)
    url = f"{OSRM_BASE_URL.rstrip('/')}/route/v1/{profile}/{origin.lon},{origin.lat};{destination.lon},{destination.lat}"
    params = {"overview": "full", "geometries": "geojson", "alternatives": "false", "steps": "false"}
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers={"User-Agent": APP_USER_AGENT}) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable for {profile}: {exc}") from exc
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No {profile} route was found between the selected locations.")
    selected = data["routes"][0]
    return RoutedOption(
        mode={"foot": "Walking", "bike": "Cycling", "car": "Car"}.get(profile, profile.title()),
        profile=profile,
        distance_km=round(float(selected["distance"]) / 1000, 2),
        duration_min=max(1, round(float(selected["duration"]) / 60)),
        geometry=selected.get("geometry") if isinstance(selected.get("geometry"), dict) else None,
        source="OpenStreetMap + OSRM",
    )


def get_real_routes(origin_text: str, destination_text: str, demo_mode: bool = False) -> tuple[Coordinates, Coordinates, list[RoutedOption]]:
    origin = geocode(origin_text.strip(), demo_mode=demo_mode)
    destination = geocode(destination_text.strip(), demo_mode=demo_mode)
    routes: list[RoutedOption] = []
    for profile in ("foot", "bike", "car"):
        try:
            routes.append(route(profile, origin, destination, demo_mode=demo_mode))
        except RoutingError:
            continue
    if not routes:
        raise RoutingError("No supported route mode could be calculated for these locations.")
    return origin, destination, routes
