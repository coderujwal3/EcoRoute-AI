from __future__ import annotations

import json
import os

import httpx

from models import OptionResult, RouteRequest

SYSTEM_PROMPT = """You are EcoRoute AI, the explanation layer for a sustainability decision-support prototype.
Use only the structured facts supplied in JSON. Never invent route availability, distance, price, travel time,
emissions, or safety information. Treat CO2e values as estimates and explicitly call them estimates.
Explain the recommendation and the most important trade-off in plain language. If the decision engine marks
an option as infeasible, do not imply that it satisfies the user's constraints.
"""


def generate_explanation(
    request: RouteRequest,
    recommended: OptionResult,
    alternatives: list[OptionResult],
    fallback: str,
) -> str:
    url = os.getenv("LLM_API_URL")
    key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")

    if not (url and key and model):
        return fallback

    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "request": request.model_dump(),
                        "recommended": recommended.model_dump(),
                        "alternatives": [a.model_dump() for a in alternatives],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    try:
        headers = {"Authorization": f"Bearer {key}"}
        with httpx.Client(timeout=15) as client:
            response = client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
            return content or fallback
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return fallback
