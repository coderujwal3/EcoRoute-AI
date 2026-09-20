from __future__ import annotations

import os
from typing import Any

from gtfs_engine import GTFSUnavailable, find_multimodal_itineraries
from routing import Coordinates, RoutingError

TRANSIT_MODE = os.getenv("TRANSIT_MODE", "gtfs")
GTFS_PATH = os.getenv("GTFS_PATH", os.path.join(os.path.dirname(__file__), "data", "gtfs_demo_varanasi.zip"))
GTFS_ACCESS_WALK_KM = float(os.getenv("GTFS_ACCESS_WALK_KM", "1.5"))


class TransitUnavailable(RoutingError):
    pass


def find_transit_options(origin: Coordinates, destination: Coordinates, arrival_time: str, limit: int = 3, walking_connector=None) -> list[dict[str, Any]]:
    if TRANSIT_MODE.lower() in {"off", "none", "disabled"}:
        return []
    try:
        return find_multimodal_itineraries(
            origin,
            destination,
            arrival_time,
            path=GTFS_PATH,
            max_access_km=GTFS_ACCESS_WALK_KM,
            limit=limit,
            walking_connector=walking_connector,
        )
    except GTFSUnavailable as exc:
        raise TransitUnavailable(f"GTFS transit service unavailable: {exc}") from exc


def find_transit_option(origin: Coordinates, destination: Coordinates, arrival_time: str) -> dict[str, Any] | None:
    options = find_transit_options(origin, destination, arrival_time, limit=1)
    return options[0] if options else None
