# EcoRoute AI v1.0.0

AI-assisted sustainable transportation decision-support prototype for the **1M1B – IBM SkillsBuild AI + Sustainability Virtual Internship (July–September 2026)**.

## What the final version demonstrates

- SDG 11 focus: Sustainable Cities and Communities.
- Offline, deterministic demo mode for presentations: no paid API and no transit API key required.
- Optional live mode using OpenStreetMap Nominatim + OSRM for geocoding and route calculation.
- Local/static GTFS public-transit planner with first-mile and last-mile walking connectors.
- Time, cost and estimated CO2e comparison.
- Hard constraint filtering (budget and maximum travel time) before ranking.
- Preference-aware decision support: sustainability, cost, speed or balanced.
- Transparent explanation layer with optional OpenAI-compatible LLM endpoint.
- Responsible-AI notes, data provenance labels, methodology disclosure and test suite.
- Demo mode supports the bundled Varanasi places: Mohansarai, Jagatpur, Rohania, PAC, Maduadih, DLW Chauraha, Sundarpur, Lanka, Kashi Institute of Technology, and Varanasi Cantt.


## Architecture

```text
User request
   |
   +--> Demo geocoder/routing OR Nominatim + OSRM
   |
   +--> Static GTFS transit engine
   |   +--> nearby origin stop
   |   +--> scheduled transit trip
   |   +--> nearby destination stop
   |   +--> walking access + egress
   |
   v
Sustainability + cost estimation
   |
   v
Hard constraints
   |
   v
Preference-aware scoring
   |
   v
Structured recommendation
   |
   v
AI explanation layer (optional)
   |
   v
Recommendation + trade-offs + map + provenance
```

## Run locally

```bash
python -m venv .venv
# Windows PowerShell
.venv\\Scripts\\Activate.ps1
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app:app --reload
```

Open `http://127.0.0.1:8000`. For the fastest run after installing dependencies, you can also use `python start.py`

### Recommended demo
The UI starts with **Offline demo mode** enabled. Click **Load demo scenario** and then **Find sustainable routes**.

Suggested scenario:

- Origin: `Mohansarai`
- Destination: `Lanka`
- Arrival time: `09:10`
- Budget: `50`
- Maximum duration: `90`
- Priority: `Lowest environmental impact`

The bundled GTFS feed is intentionally labelled **demo-only**. It is a teaching/demo dataset, not authoritative live transit information.

## Optional live mode

Uncheck **Offline demo mode**. Then set a contact-identifying user agent before using public OpenStreetMap services:

```text
ECOROUTE_USER_AGENT=EcoRouteAI/1.0 (your-contact-email-or-project-url)
```

Other configuration:

```text
NOMINATIM_URL=https://nominatim.openstreetmap.org/search
OSRM_BASE_URL=https://router.project-osrm.org
ROUTING_TIMEOUT_SECONDS=15
ECOROUTE_CAR_COST_PER_KM_INR=12
ECOROUTE_CAR_BASE_COST_INR=0
GTFS_PATH=./data/gtfs_demo_varanasi.zip
GTFS_ACCESS_WALK_KM=1.5
GTFS_STOP_CANDIDATES=4
```

## Optional AI explanation

EcoRoute can call any OpenAI-compatible chat endpoint when all three variables are configured:

```text
LLM_API_URL=<chat-completions-endpoint>
LLM_API_KEY=<token>
LLM_MODEL=<model-name>
```

The AI receives structured route results and is instructed not to invent route, time, fare, distance or emissions facts. Without an LLM, the deterministic explanation keeps the demo fully functional.

## Sustainability methodology

Primary metric: **estimated CO2e per passenger trip**.

Current educational proxy values in `decision_engine.py`:

- Bus/public transit: 97 gCO2e/passenger-km.
- Car: 170 gCO2e/passenger-km.
- Walking/cycling: 0 operational tailpipe emissions in the simplified model.

These are proxy values, not measured trip emissions. Real impact depends on vehicle technology, fuel, occupancy, operating conditions and lifecycle boundaries.

## Responsible AI

The final prototype addresses the internship's mandatory areas:

- **Fairness:** users choose their own constraints and priorities; no assumption is made that every user can use every mode.
- **Transparency:** scores, constraints, estimates and data-status labels are exposed.
- **Ethics:** the UI avoids claiming proxy estimates are measurements or live facts.
- **Privacy:** no personal or sensitive data is required for the core workflow.

## External references used by the implementation

- GTFS Overview: https://gtfs.org/documentation/overview/
- GTFS Schedule Reference: https://gtfs.org/documentation/schedule/reference/
- OpenStreetMap Nominatim Search API: https://nominatim.org/release-docs/develop/api/Search/
- Nominatim usage policy: https://operations.osmfoundation.org/policies/nominatim/
- OSRM HTTP API: https://project-osrm.org/docs/v26.4.0/http
- World Resources Institute India, *Pathways to Decarbonize India's Transport Sector*: https://india.wri.org/sites/default/files/Pathways-to-decarbonize-India-s-transport-sector.pdf
