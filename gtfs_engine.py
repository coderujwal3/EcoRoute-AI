from __future__ import annotations

import csv
import math
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from routing import Coordinates, RoutedOption, RoutingError, route

DEFAULT_GTFS_PATH = os.getenv("GTFS_PATH", str(Path(__file__).parent / "data" / "gtfs_demo_varanasi.zip"))
DEFAULT_ACCESS_WALK_KM = float(os.getenv("GTFS_ACCESS_WALK_KM", "1.5"))
DEFAULT_STOP_CANDIDATES = int(os.getenv("GTFS_STOP_CANDIDATES", "4"))
WALKING_SPEED_KMPH = 5.0


@dataclass(frozen=True)
class GTFSStop:
    stop_id: str
    name: str
    lat: float
    lon: float


@dataclass(frozen=True)
class GTFSRoute:
    route_id: str
    short_name: str
    long_name: str


@dataclass(frozen=True)
class GTFSTrip:
    trip_id: str
    route_id: str
    service_id: str
    stop_times: list[tuple[str, int, int, int]]  # stop_id, arrival_sec, departure_sec, sequence


@dataclass(frozen=True)
class GTFSFeed:
    agency_name: str
    stops: dict[str, GTFSStop]
    routes: dict[str, GTFSRoute]
    trips: list[GTFSTrip]
    fares_inr: dict[str, float]
    source_label: str
    demo_only: bool


class GTFSUnavailable(RuntimeError):
    pass


def _read_csv(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        with zf.open(name) as fh:
            text = (line.decode("utf-8-sig") for line in fh)
            return list(csv.DictReader(text))
    except KeyError as exc:
        raise GTFSUnavailable(f"GTFS feed is missing required file: {name}") from exc


def _parse_gtfs_time(value: str) -> int:
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid GTFS time: {value}")
    h, m, s = map(int, parts)
    if h < 0 or m < 0 or s < 0 or m >= 60 or s >= 60:
        raise ValueError(f"Invalid GTFS time: {value}")
    return h * 3600 + m * 60 + s


def _haversine_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(x))


def _haversine_km(a: Coordinates, b: GTFSStop) -> float:
    return _haversine_between(a.lat, a.lon, b.lat, b.lon)


def _nearest_stop_candidates(coord: Coordinates, stops: Iterable[GTFSStop], max_km: float, limit: int) -> list[tuple[GTFSStop, float]]:
    options = sorted((( _haversine_km(coord, stop), stop) for stop in stops), key=lambda item: item[0])
    filtered = [(stop, distance) for distance, stop in options if distance <= max_km]
    return filtered[: max(1, limit)]


def load_gtfs(path: str = DEFAULT_GTFS_PATH) -> GTFSFeed:
    if not Path(path).exists():
        raise GTFSUnavailable(f"GTFS feed not found: {path}")
    try:
        with zipfile.ZipFile(path) as zf:
            agency_rows = _read_csv(zf, "agency.txt")
            stop_rows = _read_csv(zf, "stops.txt")
            route_rows = _read_csv(zf, "routes.txt")
            trip_rows = _read_csv(zf, "trips.txt")
            stop_time_rows = _read_csv(zf, "stop_times.txt")
            fare_rows = _read_csv(zf, "fare_attributes.txt") if "fare_attributes.txt" in zf.namelist() else []
            feed_rows = _read_csv(zf, "feed_info.txt") if "feed_info.txt" in zf.namelist() else []
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise GTFSUnavailable(f"Could not read GTFS feed: {exc}") from exc

    stops: dict[str, GTFSStop] = {}
    for row in stop_rows:
        try:
            stops[row["stop_id"]] = GTFSStop(
                row["stop_id"], row["stop_name"], float(row["stop_lat"]), float(row["stop_lon"])
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GTFSUnavailable("Invalid stops.txt row in GTFS feed.") from exc

    routes = {
        row["route_id"]: GTFSRoute(row["route_id"], row.get("route_short_name", ""), row.get("route_long_name", ""))
        for row in route_rows
    }

    grouped: dict[str, list[tuple[str, int, int, int]]] = {}
    trip_meta: dict[str, tuple[str, str]] = {}
    for row in trip_rows:
        trip_meta[row["trip_id"]] = (row["route_id"], row["service_id"])
    for row in stop_time_rows:
        try:
            trip_id = row["trip_id"]
            grouped.setdefault(trip_id, []).append(
                (
                    row["stop_id"],
                    _parse_gtfs_time(row["arrival_time"]),
                    _parse_gtfs_time(row["departure_time"]),
                    int(row["stop_sequence"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GTFSUnavailable("Invalid stop_times.txt row in GTFS feed.") from exc

    trips = [
        GTFSTrip(trip_id, trip_meta[trip_id][0], trip_meta[trip_id][1], sorted(times, key=lambda x: x[3]))
        for trip_id, times in grouped.items()
        if trip_id in trip_meta
    ]

    fares: dict[str, float] = {}
    for row in fare_rows:
        try:
            fares[row["fare_id"]] = float(row["price"])
        except (KeyError, TypeError, ValueError):
            continue

    agency_name = agency_rows[0].get("agency_name", "GTFS transit agency") if agency_rows else "GTFS transit agency"
    feed_id = feed_rows[0].get("feed_id", "") if feed_rows else ""
    demo_only = feed_id.lower().startswith("demo") or "demo" in feed_id.lower()
    publisher = feed_rows[0].get("feed_publisher_name", "") if feed_rows else ""
    source_label = " / ".join(filter(None, [agency_name, publisher])) or agency_name
    return GTFSFeed(agency_name, stops, routes, trips, fares, source_label, demo_only)


def _format_sec(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h:02d}:{m:02d}"


def _route_distance(feed: GTFSFeed, trip: GTFSTrip, start_idx: int, end_idx: int) -> float:
    total = 0.0
    for i in range(start_idx, end_idx):
        a = feed.stops.get(trip.stop_times[i][0])
        b = feed.stops.get(trip.stop_times[i + 1][0])
        if a and b:
            total += _haversine_between(a.lat, a.lon, b.lat, b.lon)
    return total


def _line_geometry(feed: GTFSFeed, trip: GTFSTrip, start_idx: int, end_idx: int) -> dict[str, Any]:
    coords = []
    for stop_id, *_ in trip.stop_times[start_idx : end_idx + 1]:
        stop = feed.stops.get(stop_id)
        if stop:
            coords.append([stop.lon, stop.lat])
    return {"type": "LineString", "coordinates": coords}


def _connector_fallback(origin: Coordinates, stop: GTFSStop) -> RoutedOption:
    distance = _haversine_between(origin.lat, origin.lon, stop.lat, stop.lon)
    duration = max(1, round(distance / WALKING_SPEED_KMPH * 60))
    geometry = {"type": "LineString", "coordinates": [[origin.lon, origin.lat], [stop.lon, stop.lat]]}
    return RoutedOption(
        mode="Walking",
        profile="foot",
        distance_km=round(distance, 2),
        duration_min=duration,
        geometry=geometry,
        source="Haversine walking estimate (routing fallback)",
    )


def _get_walking_connector(
    a: Coordinates,
    b: Coordinates,
    fallback_allowed: bool = True,
) -> RoutedOption:
    try:
        return route("foot", a, b)
    except RoutingError:
        if not fallback_allowed:
            raise
        pseudo_stop = GTFSStop("connector", b.display_name, b.lat, b.lon)
        return _connector_fallback(a, pseudo_stop)


def _route_with_origin_stop(origin: Coordinates, stop: GTFSStop, fallback_allowed: bool) -> RoutedOption:
    return _get_walking_connector(origin, Coordinates(stop.lat, stop.lon, stop.name), fallback_allowed=fallback_allowed)


def _route_with_destination_stop(stop: GTFSStop, destination: Coordinates, fallback_allowed: bool) -> RoutedOption:
    return _get_walking_connector(Coordinates(stop.lat, stop.lon, stop.name), destination, fallback_allowed=fallback_allowed)


def _transit_itinerary_candidates(
    feed: GTFSFeed,
    origin_stop_candidates: list[tuple[GTFSStop, float]],
    destination_stop_candidates: list[tuple[GTFSStop, float]],
    arrival_time: str,
    origin: Coordinates,
    destination: Coordinates,
    walking_connector: Callable[[Coordinates, Coordinates], RoutedOption] | None,
    fallback_allowed: bool,
) -> list[dict[str, Any]]:
    target_sec = _parse_gtfs_time(f"{arrival_time}:00")
    candidates: list[dict[str, Any]] = []
    connector_cache: dict[tuple[str, str], tuple[RoutedOption, RoutedOption]] = {}
    for origin_stop, _ in origin_stop_candidates:
        for destination_stop, _ in destination_stop_candidates:
            key = (origin_stop.stop_id, destination_stop.stop_id)
            if key not in connector_cache:
                if walking_connector:
                    first_leg = walking_connector(origin, Coordinates(origin_stop.lat, origin_stop.lon, origin_stop.name))
                    last_leg = walking_connector(Coordinates(destination_stop.lat, destination_stop.lon, destination_stop.name), destination)
                else:
                    first_leg = _route_with_origin_stop(origin, origin_stop, fallback_allowed)
                    last_leg = _route_with_destination_stop(destination_stop, destination, fallback_allowed)
                connector_cache[key] = (first_leg, last_leg)
            first_leg, last_leg = connector_cache[key]
            for trip in feed.trips:
                route_info = feed.routes.get(trip.route_id)
                if not route_info:
                    continue
                start_idx = next((i for i, item in enumerate(trip.stop_times) if item[0] == origin_stop.stop_id), None)
                end_idx = next((i for i, item in enumerate(trip.stop_times) if item[0] == destination_stop.stop_id), None)
                if start_idx is None or end_idx is None or end_idx <= start_idx:
                    continue
                dep = trip.stop_times[start_idx][2]
                arr = trip.stop_times[end_idx][1]
                final_arrival = arr + last_leg.duration_min * 60
                if final_arrival > target_sec:
                    continue
                transit_distance = _route_distance(feed, trip, start_idx, end_idx)
                transit_duration = max(1, round((arr - dep) / 60))
                total_duration = first_leg.duration_min + transit_duration + last_leg.duration_min
                total_distance = first_leg.distance_km + transit_distance + last_leg.distance_km
                fare = next(iter(feed.fares_inr.values()), 20.0)
                schedule_slack_min = max(0, round((target_sec - final_arrival) / 60))
                candidates.append(
                    {
                        "duration_min": total_duration,
                        "distance_km": round(total_distance, 2),
                        "transit_distance_km": round(transit_distance, 2),
                        "access_walk_km": round(first_leg.distance_km, 2),
                        "egress_walk_km": round(last_leg.distance_km, 2),
                        "access_walk_min": first_leg.duration_min,
                        "egress_walk_min": last_leg.duration_min,
                        "schedule_slack_min": schedule_slack_min,
                        "route_short_name": route_info.short_name,
                        "route_long_name": route_info.long_name,
                        "trip_id": trip.trip_id,
                        "from_stop": origin_stop.name,
                        "to_stop": destination_stop.name,
                        "departure_time": _format_sec(dep),
                        "arrival_time": _format_sec(arr),
                        "final_arrival_time": _format_sec(final_arrival),
                        "fare_inr": float(fare),
                        "fare_is_estimated": feed.demo_only or not bool(feed.fares_inr),
                        "source": feed.source_label,
                        "demo_only": feed.demo_only,
                        "transit_geometry": _line_geometry(feed, trip, start_idx, end_idx),
                        "access_geometry": first_leg.geometry,
                        "egress_geometry": last_leg.geometry,
                        "access_source": first_leg.source,
                        "egress_source": last_leg.source,
                    }
                )
    candidates.sort(key=lambda x: (x["schedule_slack_min"], x["duration_min"], x["transit_distance_km"]))
    unique: list[dict[str, Any]] = []
    seen = set()
    for item in candidates:
        signature = (item["trip_id"], item["from_stop"], item["to_stop"])
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(item)
    return unique


def find_multimodal_itineraries(
    origin: Coordinates,
    destination: Coordinates,
    arrival_time: str,
    path: str = DEFAULT_GTFS_PATH,
    max_access_km: float = DEFAULT_ACCESS_WALK_KM,
    limit: int = 3,
    walking_connector: Callable[[Coordinates, Coordinates], RoutedOption] | None = None,
    fallback_allowed: bool = True,
) -> list[dict[str, Any]]:
    feed = load_gtfs(path)
    origin_candidates = _nearest_stop_candidates(origin, feed.stops.values(), max_access_km, DEFAULT_STOP_CANDIDATES)
    destination_candidates = _nearest_stop_candidates(destination, feed.stops.values(), max_access_km, DEFAULT_STOP_CANDIDATES)
    if not origin_candidates or not destination_candidates:
        return []
    options = _transit_itinerary_candidates(
        feed,
        origin_candidates,
        destination_candidates,
        arrival_time,
        origin,
        destination,
        walking_connector,
        fallback_allowed,
    )
    return options[: max(1, limit)]


def find_direct_itinerary(
    origin: Coordinates,
    destination: Coordinates,
    arrival_time: str,
    path: str = DEFAULT_GTFS_PATH,
) -> dict[str, Any] | None:
    """Backward-compatible wrapper returning the best v0.6 multimodal itinerary."""
    options = find_multimodal_itineraries(origin, destination, arrival_time, path=path, limit=1)
    return options[0] if options else None
