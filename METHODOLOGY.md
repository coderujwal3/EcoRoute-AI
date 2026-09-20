# EcoRoute AI Methodology — v1.0.0

## Primary sustainability metric

Estimated CO2e per passenger trip.

## Environmental proxy

- Bus/public transit: 97 gCO2e/passenger-km (India-context proxy used for illustration).
- Car: 170 gCO2e/passenger-km (India-context proxy used for illustration).
- Walking/cycling: 0 operational tailpipe emissions in this simplified model.

These are proxy estimates, not measured trip emissions. Actual impact depends on vehicle technology, fuel, occupancy, operating conditions and lifecycle boundaries.

## Cost methodology

- Car: configurable distance-based estimate via `ECOROUTE_CAR_COST_PER_KM_INR` and `ECOROUTE_CAR_BASE_COST_INR`.
- Walking/cycling: ₹0 operational trip cost in this simplified prototype.
- Public transit: GTFS fare when supplied; the bundled Varanasi feed uses a demonstration fare and is labelled accordingly.

## Transit methodology

1. Identify nearby origin and destination stops within the configured walking radius.
2. Find GTFS trips that serve the origin stop before the destination stop.
3. Calculate first-mile and last-mile walking connectors.
4. Reject itineraries that arrive after the requested arrival time.
5. Return up to three direct-transit candidates.
6. Represent multimodal journeys as access walking + transit + egress walking.

The current prototype does not model multi-transfer transit journeys.

## Decision scoring

The ranking combines normalized cost, travel time, estimated environmental impact and a small convenience component. Product-design weights vary by user preference (`sustainability`, `cost`, `speed`, `balanced`). Hard constraints are applied first. The weights are not presented as universal scientific constants.

## Demo mode

The UI defaults to an offline deterministic demo. It uses bundled coordinates, approximate straight-line geometries and the local demonstration GTFS feed. Demo route geometry is not road-network navigation and must not be presented as live navigation.

## Live mode

When offline demo mode is disabled, geocoding and walking/cycling/car routing can use Nominatim and OSRM. The app identifies itself using `ECOROUTE_USER_AGENT` and the implementation throttles Nominatim requests.

## AI explanation

The optional LLM receives structured route results only. Its system prompt prohibits inventing routes, fares, distances, times, emissions or safety facts. When no LLM endpoint is configured, a deterministic explanation is returned so the project remains fully runnable.

## Responsible-use boundary

- The application supports decisions; it does not claim a universally best mode.
- Proxy emissions and estimated costs are labelled as estimates.
- Demo GTFS schedules and fares are explicitly not authoritative live transit data.
- No personal or sensitive data is required for the core workflow.
