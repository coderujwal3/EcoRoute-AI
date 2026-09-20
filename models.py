from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

Priority = Literal["sustainability", "cost", "speed", "balanced"]
DataStatus = Literal[
    "real-route",
    "demo-route",
    "estimated-cost",
    "transit-gtfs",
    "multimodal-gtfs",
    "unavailable",
]


class RouteRequest(BaseModel):
    origin: str = Field(min_length=1, max_length=200)
    destination: str = Field(min_length=1, max_length=200)
    arrival_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    demo_mode: bool = True
    budget_inr: float = Field(default=100, ge=0, le=100000)
    max_duration_min: int | None = Field(default=None, ge=1, le=1440)
    priority: Priority = "sustainability"


class JourneyLeg(BaseModel):
    mode: str
    duration_min: int
    distance_km: float
    from_name: str
    to_name: str
    departure_time: str | None = None
    arrival_time: str | None = None
    fare_inr: float | None = None
    source: str
    geometry: dict[str, Any] | None = None


class OptionResult(BaseModel):
    mode: str
    duration_min: int
    cost_inr: float
    distance_km: float
    emission_factor_gco2e_pkm: float
    estimated_co2e_g: float
    estimated_co2e_kg: float
    impact_label: str
    convenience_score: int
    score: float
    feasible: bool
    reasons: list[str]
    methodology_note: str
    route_source: str
    geometry: dict[str, Any] | None = None
    data_status: DataStatus = "real-route"
    fare_basis: str | None = None
    transit_details: dict[str, Any] | None = None
    legs: list[JourneyLeg] = Field(default_factory=list)


class Methodology(BaseModel):
    metric: str
    source_name: str
    source_url: str
    source_year: int
    geographic_context: str
    caveat: str


class Location(BaseModel):
    query: str
    display_name: str
    lat: float
    lon: float


class RouteResponse(BaseModel):
    origin: Location
    destination: Location
    priority: Priority
    recommended: OptionResult
    alternatives: list[OptionResult]
    explanation: str
    methodology: Methodology
    routing_attribution: str
    transit_status: str
