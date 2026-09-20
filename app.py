from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ai_explainer import generate_explanation
from decision_engine import METHODOLOGY, fallback_explanation, recommend
from models import Location, RouteRequest, RouteResponse
from routing import RoutingError, get_real_routes, route
from transit import GTFS_PATH, TransitUnavailable, find_transit_options

app = FastAPI(title="EcoRoute AI", version="1.0.0")
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": app.version,
        "routing": "nominatim + osrm",
        "transit_mode": os.getenv("TRANSIT_MODE", "gtfs"),
        "gtfs_path": GTFS_PATH,
        "features": ["demo-mode", "direct-routing", "multimodal-gtfs", "first-mile-walking", "last-mile-walking", "transparent-scoring"],
    }


@app.post("/api/recommend", response_model=RouteResponse)
def api_recommend(payload: RouteRequest):
    try:
        origin, destination, routes = get_real_routes(payload.origin, payload.destination, demo_mode=payload.demo_mode)
        transit_options = []
        transit_status = "GTFS multimodal public transit integration enabled using the configured local/static feed."
        try:
            connector = (lambda a, b: route("foot", a, b, demo_mode=True)) if payload.demo_mode else None
            transit_options = find_transit_options(origin, destination, payload.arrival_time, limit=3, walking_connector=connector)
            if transit_options:
                demo_suffix = " This is a demonstration feed; verify before real-world use." if transit_options[0].get("demo_only") else ""
                transit_status = (
                    f"Found {len(transit_options)} multimodal public-transit itinerary option(s) "
                    "using walking access + GTFS transit + walking egress." + demo_suffix
                )
            else:
                transit_status = "No direct GTFS public-transit itinerary with first/last-mile walking was found for this request."
        except TransitUnavailable as exc:
            transit_status = str(exc)

        recommended, alternatives = recommend(payload, routes, transit=transit_options)
    except RoutingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    fallback = fallback_explanation(payload, recommended, alternatives)
    explanation = generate_explanation(payload, recommended, alternatives, fallback)
    return RouteResponse(
        origin=Location(query=payload.origin, display_name=origin.display_name, lat=origin.lat, lon=origin.lon),
        destination=Location(query=payload.destination, display_name=destination.display_name, lat=destination.lat, lon=destination.lon),
        priority=payload.priority,
        recommended=recommended,
        alternatives=alternatives,
        explanation=explanation,
        methodology=METHODOLOGY,
        routing_attribution=("Demo mode: bundled/local demonstration data; no external geocoding/routing was used." if payload.demo_mode else "Geocoding/routing: © OpenStreetMap contributors; routing service: OSRM."),
        transit_status=transit_status,
    )
