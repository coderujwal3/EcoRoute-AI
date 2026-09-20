from __future__ import annotations

import os

# Educational prototype defaults. These are deliberately configurable and are
# presented as estimates, not observed fares or total cost of ownership.
CAR_COST_PER_KM_INR = float(os.getenv("ECOROUTE_CAR_COST_PER_KM_INR", "12"))
CAR_BASE_COST_INR = float(os.getenv("ECOROUTE_CAR_BASE_COST_INR", "0"))
BIKE_COST_PER_KM_INR = float(os.getenv("ECOROUTE_BIKE_COST_PER_KM_INR", "0"))
WALK_COST_PER_KM_INR = float(os.getenv("ECOROUTE_WALK_COST_PER_KM_INR", "0"))


def estimate_trip_cost(mode: str, distance_km: float) -> tuple[float, str]:
    mode_key = mode.lower()
    if mode_key == "car":
        cost = CAR_BASE_COST_INR + distance_km * CAR_COST_PER_KM_INR
        return round(cost, 2), (
            f"Estimated car travel cost using ₹{CAR_COST_PER_KM_INR:g}/km"
            + (f" + ₹{CAR_BASE_COST_INR:g} base cost." if CAR_BASE_COST_INR else ".")
        )
    if mode_key == "cycling":
        return round(distance_km * BIKE_COST_PER_KM_INR, 2), "Operational trip cost assumed ₹0 for cycling in this prototype."
    return round(distance_km * WALK_COST_PER_KM_INR, 2), "Operational trip cost assumed ₹0 for walking in this prototype."
