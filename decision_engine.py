from __future__ import annotations

from cost_model import estimate_trip_cost
from models import JourneyLeg, Methodology, OptionResult, RouteRequest

METHODOLOGY = Methodology(
    metric="Estimated CO2e per passenger trip",
    source_name="World Resources Institute India, Pathways to Decarbonize India's Transport Sector",
    source_url="https://india.wri.org/sites/default/files/Pathways-to-decarbonize-India-s-transport-sector.pdf",
    source_year=2025,
    geographic_context="India-context proxy values",
    caveat=(
        "Bus/public-transit and car factors are published India-context averages used as illustrative proxies. "
        "Route-specific emissions vary with vehicle technology, fuel, congestion and occupancy. "
        "Walking/cycling are represented as zero operational tailpipe emissions in this simplified model, "
        "not zero lifecycle emissions."
    ),
)

MODE_CONFIG = {
    "Walking": {"factor": 0.0, "convenience": 5},
    "Cycling": {"factor": 0.0, "convenience": 7},
    "Car": {"factor": 170.0, "convenience": 9},
}

PRIORITY_WEIGHTS = {
    "sustainability": (0.10, 0.10, 0.75, 0.05),
    "cost": (0.80, 0.05, 0.10, 0.05),
    "speed": (0.05, 0.85, 0.05, 0.05),
    "balanced": (0.25, 0.25, 0.35, 0.15),
}


def _normalized(value: float, low: float, high: float) -> float:
    if high == low:
        return 1.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _impact_label(co2e_g: float) -> str:
    if co2e_g == 0:
        return "Lowest operational impact"
    if co2e_g <= 100:
        return "Lower"
    if co2e_g <= 250:
        return "Moderate"
    if co2e_g <= 500:
        return "Higher"
    return "High"


def _base_score(cost: float, duration_min: int, co2e_g: float, convenience: int, request: RouteRequest,
                max_cost: float, max_duration: int, max_impact: float) -> float:
    cw, tw, iw, convw = PRIORITY_WEIGHTS[request.priority]
    cost_n = _normalized(cost, 0, max_cost)
    time_n = _normalized(duration_min, 0, max_duration)
    impact_n = _normalized(co2e_g, 0, max(1.0, max_impact))
    convenience_n = convenience / 10
    return round((((1 - cost_n) * cw) + ((1 - time_n) * tw) + ((1 - impact_n) * iw) + (convenience_n * convw)) * 100, 2)


def build_options(request: RouteRequest, routes) -> list[OptionResult]:
    max_duration = max(r.duration_min for r in routes)
    impacts = [r.distance_km * float(MODE_CONFIG[r.mode]["factor"]) for r in routes]
    max_impact = max(1.0, max(impacts, default=0.0))
    cost_values: dict[str, float] = {}
    cost_notes: dict[str, str] = {}
    for r in routes:
        cost_values[r.mode], cost_notes[r.mode] = estimate_trip_cost(r.mode, r.distance_km)
    max_cost = max(1.0, max(cost_values.values(), default=0.0))

    results: list[OptionResult] = []
    for r in routes:
        cfg = MODE_CONFIG[r.mode]
        cost = cost_values[r.mode]
        co2e_g = r.distance_km * float(cfg["factor"])
        within_budget = cost <= request.budget_inr
        within_time = request.max_duration_min is None or r.duration_min <= request.max_duration_min
        feasible = within_budget and within_time
        score = _base_score(cost, r.duration_min, co2e_g, int(cfg["convenience"]), request, max_cost, max_duration, max_impact)
        reasons = ["within budget" if within_budget else "over budget", "within time limit" if within_time else "over time limit"]
        reasons.append(cost_notes[r.mode])
        if r.mode in {"Walking", "Cycling"}:
            reasons.append("zero operational tailpipe emissions in this simplified model")
        else:
            reasons.append("estimated using an India-context car proxy factor")
        results.append(
            OptionResult(
                mode=r.mode,
                duration_min=r.duration_min,
                cost_inr=round(cost, 2),
                distance_km=r.distance_km,
                emission_factor_gco2e_pkm=float(cfg["factor"]),
                estimated_co2e_g=round(co2e_g, 1),
                estimated_co2e_kg=round(co2e_g / 1000, 3),
                impact_label=_impact_label(co2e_g),
                convenience_score=int(cfg["convenience"]),
                score=score,
                feasible=feasible,
                reasons=reasons,
                methodology_note=(f"Estimated using {cfg['factor']:g} gCO2e/passenger-km × {r.distance_km:g} km. "
                                  "This is a proxy estimate, not a measured trip emission."),
                route_source=r.source,
                geometry=r.geometry,
                data_status=("demo-route" if r.source.startswith("EcoRoute local demo") else "real-route"),
                fare_basis=cost_notes[r.mode],
                legs=[
                    JourneyLeg(
                        mode=r.mode,
                        duration_min=r.duration_min,
                        distance_km=r.distance_km,
                        from_name="Origin",
                        to_name="Destination",
                        source=r.source,
                        geometry=r.geometry,
                    )
                ],
            )
        )
    return results


def _geojson_feature(geometry: dict | None) -> dict | None:
    if not geometry:
        return None
    if geometry.get("type") == "Feature":
        return geometry
    return {"type": "Feature", "properties": {}, "geometry": geometry}


def add_transit_option(results: list[OptionResult], request: RouteRequest, transit: dict) -> None:
    transit_distance = float(transit.get("transit_distance_km", transit["distance_km"]))
    total_distance = float(transit["distance_km"])
    co2e_g = transit_distance * 97.0
    cost = float(transit.get("fare_inr", 0.0))
    within_budget = cost <= request.budget_inr
    within_time = request.max_duration_min is None or int(transit["duration_min"]) <= request.max_duration_min
    feasible = within_budget and within_time
    transit_label = transit.get("route_short_name") or "GTFS"
    reasons = ["multimodal itinerary: walking access + public transit + walking egress"]
    reasons.append("within budget" if within_budget else "over budget")
    reasons.append("within time limit" if within_time else "over time limit")
    if transit.get("fare_is_estimated"):
        reasons.append("fare is a demonstration/configured estimate, not a verified live fare")
    else:
        reasons.append("fare came from GTFS fare data")
    reasons.append("environmental impact applies the bus proxy to the in-vehicle transit distance only")

    legs: list[JourneyLeg] = []
    access_geom = transit.get("access_geometry")
    egress_geom = transit.get("egress_geometry")
    transit_geom = transit.get("transit_geometry")
    legs.append(JourneyLeg(
        mode="Walking (access)",
        duration_min=int(transit["access_walk_min"]),
        distance_km=float(transit["access_walk_km"]),
        from_name="Origin",
        to_name=transit["from_stop"],
        source=transit.get("access_source", "Walking connector"),
        geometry=_geojson_feature(access_geom),
    ))
    legs.append(JourneyLeg(
        mode=f"Public Transit ({transit_label})",
        duration_min=max(1, int(round((int(_sec(transit["arrival_time"])) - int(_sec(transit["departure_time"]))) / 60))),
        distance_km=transit_distance,
        from_name=transit["from_stop"],
        to_name=transit["to_stop"],
        departure_time=transit["departure_time"],
        arrival_time=transit["arrival_time"],
        fare_inr=cost,
        source=f"GTFS: {transit.get('source', 'configured feed')}",
        geometry=_geojson_feature(transit_geom),
    ))
    legs.append(JourneyLeg(
        mode="Walking (egress)",
        duration_min=int(transit["egress_walk_min"]),
        distance_km=float(transit["egress_walk_km"]),
        from_name=transit["to_stop"],
        to_name="Destination",
        source=transit.get("egress_source", "Walking connector"),
        geometry=_geojson_feature(egress_geom),
    ))

    feature_geometries = [g for g in (access_geom, transit_geom, egress_geom) if g]
    geometry = {"type": "FeatureCollection", "features": [_geojson_feature(g) for g in feature_geometries]}
    result = OptionResult(
        mode=f"Public Transit ({transit_label})",
        duration_min=int(transit["duration_min"]),
        cost_inr=round(cost, 2),
        distance_km=round(total_distance, 2),
        emission_factor_gco2e_pkm=97.0,
        estimated_co2e_g=round(co2e_g, 1),
        estimated_co2e_kg=round(co2e_g / 1000, 3),
        impact_label=_impact_label(co2e_g),
        convenience_score=7,
        score=0.0,
        feasible=feasible,
        reasons=reasons,
        methodology_note=(
            "Multimodal GTFS itinerary with first/last-mile walking. "
            "Environmental impact uses 97 gCO2e/passenger-km × in-vehicle transit distance; "
            "walking legs are treated as zero operational tailpipe emissions. "
            + ("Demo feed/fare: verify before real-world use." if transit.get("demo_only") else "Fare is taken from GTFS data.")
        ),
        route_source=f"GTFS: {transit.get('source', 'configured feed')}",
        geometry=geometry,
        data_status="multimodal-gtfs",
        fare_basis=("Demonstration GTFS fare; not a verified live fare." if transit.get("fare_is_estimated") else "GTFS fare data."),
        transit_details=transit,
        legs=legs,
    )
    results.append(result)


def _sec(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":")[:2])
    return h * 3600 + m * 60


def _rescore(results: list[OptionResult], request: RouteRequest) -> list[OptionResult]:
    max_duration = max((r.duration_min for r in results), default=1)
    max_impact = max((r.estimated_co2e_g for r in results), default=1.0)
    max_cost = max((r.cost_inr for r in results), default=1.0)
    for r in results:
        r.score = _base_score(
            r.cost_inr,
            r.duration_min,
            r.estimated_co2e_g,
            r.convenience_score,
            request,
            max_cost,
            max_duration,
            max_impact,
        )
    return results


def recommend(request: RouteRequest, routes, transit: dict | list[dict] | None = None) -> tuple[OptionResult, list[OptionResult]]:
    results = build_options(request, routes)
    if transit:
        transit_options = transit if isinstance(transit, list) else [transit]
        for option in transit_options:
            add_transit_option(results, request, option)
    _rescore(results, request)
    feasible = sorted((r for r in results if r.feasible), key=lambda x: x.score, reverse=True)
    pool = feasible if feasible else sorted(results, key=lambda x: x.score, reverse=True)
    if not pool:
        raise ValueError("No route options available.")
    return pool[0], pool[1:4]


def fallback_explanation(request: RouteRequest, recommended: OptionResult, alternatives: list[OptionResult]) -> str:
    priority_text = {
        "sustainability": "sustainability",
        "cost": "cost",
        "speed": "travel speed",
        "balanced": "a balance of cost, time, sustainability, and convenience",
    }[request.priority]
    constraint_note = " It satisfies the supplied constraints." if recommended.feasible else " No option satisfied every supplied hard constraint, so this is the highest-ranked fallback."
    alt_text = "; ".join(
        f"{a.mode} ({a.duration_min} min, ₹{a.cost_inr:g}, ~{a.estimated_co2e_kg:g} kg CO2e)" for a in alternatives
    ) or "No additional alternatives"
    return (
        f"Recommended: {recommended.mode}. The ranking prioritizes {priority_text}.{constraint_note} "
        f"It takes about {recommended.duration_min} minutes over {recommended.distance_km:g} km and has an estimated "
        f"{recommended.estimated_co2e_kg:g} kg CO2e trip impact. Cost shown: ₹{recommended.cost_inr:g}. "
        f"Alternatives: {alt_text}."
    )
