from __future__ import annotations

import argparse
import os
from typing import Any

from dotenv import load_dotenv

from visor_agentico.sdk import VisorClient

WEATHER_DATA = {
    ("madrid", "friday"): {
        "forecast": "light rain in the afternoon",
        "temperature_c": 19,
        "rain_chance": 68,
        "outdoor_score": 4,
    },
    ("madrid", "saturday"): {
        "forecast": "clear and dry",
        "temperature_c": 24,
        "rain_chance": 10,
        "outdoor_score": 9,
    },
    ("barcelona", "friday"): {
        "forecast": "warm with scattered clouds",
        "temperature_c": 23,
        "rain_chance": 18,
        "outdoor_score": 8,
    },
}

VENUE_DATA = {
    "madrid": [
        {
            "name": "El Invernadero Hub",
            "type": "indoor",
            "capacity": 14,
            "per_person_eur": 32,
            "district": "Atocha",
            "notes": "Quiet indoor space with projector and good food nearby.",
        },
        {
            "name": "Lago de Casa de Campo Terrace",
            "type": "outdoor",
            "capacity": 18,
            "per_person_eur": 26,
            "district": "Casa de Campo",
            "notes": "Good for casual meetups when the weather is stable.",
        },
        {
            "name": "La Quinta Studio",
            "type": "mixed",
            "capacity": 10,
            "per_person_eur": 29,
            "district": "Chueca",
            "notes": "Has indoor seating plus a small terrace.",
        },
    ],
    "barcelona": [
        {
            "name": "Poblenou Workshop Loft",
            "type": "indoor",
            "capacity": 16,
            "per_person_eur": 34,
            "district": "Poblenou",
            "notes": "Best for focused sessions and demos.",
        },
        {
            "name": "Barceloneta Patio",
            "type": "outdoor",
            "capacity": 12,
            "per_person_eur": 27,
            "district": "Barceloneta",
            "notes": "Nice when the group wants a more informal meetup.",
        },
    ],
}

TRAVEL_DATA = {
    ("atocha", "atocha"): {"metro": 8, "taxi": 6},
    ("atocha", "casa de campo"): {"metro": 31, "taxi": 20},
    ("atocha", "chueca"): {"metro": 18, "taxi": 14},
    ("nuevos ministerios", "atocha"): {"metro": 22, "taxi": 16},
    ("nuevos ministerios", "casa de campo"): {"metro": 28, "taxi": 21},
    ("nuevos ministerios", "chueca"): {"metro": 14, "taxi": 11},
    ("sants", "poblenou"): {"metro": 24, "taxi": 16},
    ("sants", "barceloneta"): {"metro": 21, "taxi": 14},
}

SCENARIOS = {
    "meetup_plan": {
        "goal": "Plan a realistic team meetup with several constraints and only the tools that are actually needed.",
        "prompt": (
            "Plan a meetup in Madrid for 8 people next Friday. "
            "Prefer outdoor only if the weather is strong enough. "
            "Keep venue spend under 320 EUR total and avoid options that take more than 35 minutes from Atocha by metro. "
            "Recommend one venue and one backup, with a short reasoned comparison."
        ),
    },
    "weather_gate": {
        "goal": "Decide if an outdoor meetup is viable without doing unnecessary venue or budget work.",
        "prompt": (
            "I only need to know whether an outdoor meetup in Madrid next Friday is a good idea. "
            "If not, say what would change your recommendation."
        ),
    },
    "budget_only": {
        "goal": "Check a selected venue against budget constraints and avoid unrelated tool calls.",
        "prompt": (
            "We already picked El Invernadero Hub in Madrid for 8 people. "
            "Check whether it fits a normal team meetup budget and tell me if I should keep it."
        ),
    },
    "barcelona_shortlist": {
        "goal": "Build a shortlist using logistics and venue tools without weather being central to the decision.",
        "prompt": (
            "I need two meetup options in Barcelona for 6 people. "
            "Prioritize focused discussion, keep travel reasonable from Sants, and stay within a normal meetup budget."
        ),
    },
}


def normalize(value: str) -> str:
    return value.strip().lower()


def canonical_day(value: str) -> str:
    normalized = normalize(value)
    if "friday" in normalized:
        return "friday"
    if "saturday" in normalized:
        return "saturday"
    return normalized


def to_int(value: Any, default: int) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = "".join(char for char in value if char.isdigit())
        if digits:
            return int(digits)
    return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return normalize(value) in {"true", "1", "yes", "y"}
    return bool(value)


def resolve_destination(value: str) -> str:
    normalized = normalize(value)
    for venues in VENUE_DATA.values():
        for venue in venues:
            if normalize(venue["name"]) == normalized:
                return normalize(venue["district"])
    return normalized


def extract_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return " ".join(part for part in parts if part).strip()
    return str(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a richer LM Studio planning agent example.")
    parser.add_argument(
        "--scenario",
        default=os.getenv("VISOR_COMPLEX_SCENARIO", "meetup_plan"),
        choices=sorted(SCENARIOS.keys()),
        help="Built-in scenario to run.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Override the scenario prompt with a custom user request.",
    )
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()

    proxy_url = os.getenv("VISOR_PROXY_URL", "http://127.0.0.1:8000")
    model_name = os.getenv("VISOR_TEST_MODEL", "local-model")
    timeout = float(os.getenv("VISOR_PROXY_TIMEOUT", "120"))
    scenario = SCENARIOS[args.scenario]
    user_prompt = args.prompt or scenario["prompt"]

    client = VisorClient(base_url=proxy_url, timeout=timeout)
    run = client.start_run(
        agent_name="lmstudio-planner-agent",
        goal=scenario["goal"],
        metadata={"environment": "lm-studio-demo", "scenario": args.scenario},
    )

    @run.tool(name="get_weather", description="Return a compact forecast and outdoor suitability score for a city and day.")
    def get_weather(city: str, day: str) -> dict[str, Any]:
        data = WEATHER_DATA.get((normalize(city), canonical_day(day)))
        if data is None:
            return {
                "city": city,
                "day": day,
                "forecast": "unknown",
                "temperature_c": None,
                "rain_chance": None,
                "outdoor_score": None,
                "notes": "No local forecast was configured for this city/day pair.",
            }
        return {"city": city, "day": day, **data}

    @run.tool(name="get_budget_policy", description="Return simple internal budget limits for a meetup or offsite.")
    def get_budget_policy(team_size: int, event_type: str = "team_meetup") -> dict[str, Any]:
        parsed_team_size = to_int(team_size, 6)
        if event_type == "offsite":
            per_person = 52
        else:
            per_person = 38
        return {
            "team_size": parsed_team_size,
            "event_type": event_type,
            "per_person_cap_eur": per_person,
            "max_total_eur": parsed_team_size * per_person,
        }

    @run.tool(name="list_venues", description="Return candidate venues in a city. Set indoor_only when weather or brief requires it.")
    def list_venues(city: str, team_size: int, indoor_only: bool = False) -> dict[str, Any]:
        parsed_team_size = to_int(team_size, 6)
        parsed_indoor_only = to_bool(indoor_only)
        venues = VENUE_DATA.get(normalize(city), [])
        filtered = [
            venue
            for venue in venues
            if venue["capacity"] >= parsed_team_size and (not parsed_indoor_only or venue["type"] in {"indoor", "mixed"})
        ]
        return {"city": city, "team_size": parsed_team_size, "indoor_only": parsed_indoor_only, "venues": filtered}

    @run.tool(name="estimate_travel", description="Estimate travel time from an origin to a district using metro or taxi.")
    def estimate_travel(origin: str, destination: str, mode: str = "metro") -> dict[str, Any]:
        resolved_destination = resolve_destination(destination)
        key = (normalize(origin), resolved_destination)
        data = TRAVEL_DATA.get(key)
        if data is None:
            return {
                "origin": origin,
                "destination": destination,
                "mode": mode,
                "minutes": None,
                "notes": "No cached route was configured for this pair.",
            }
        return {
            "origin": origin,
            "destination": destination,
            "resolved_destination": resolved_destination,
            "mode": mode,
            "minutes": data.get(normalize(mode)),
        }

    @run.tool(name="estimate_venue_cost", description="Estimate total spend for a venue, group size and optional extras.")
    def estimate_venue_cost(venue_name: str, attendees: int, extras: str = "none") -> dict[str, Any]:
        parsed_attendees = to_int(attendees, 6)
        venue = None
        for venues in VENUE_DATA.values():
            venue = next((item for item in venues if normalize(item["name"]) == normalize(venue_name)), None)
            if venue:
                break
        if venue is None:
            return {
                "venue_name": venue_name,
                "attendees": parsed_attendees,
                "estimated_total_eur": None,
                "notes": "Venue was not found in the local dataset.",
            }

        extra_cost = {"none": 0, "snacks": 24, "av": 35, "snacks_and_av": 52}.get(normalize(extras), 18)
        base_total = venue["per_person_eur"] * parsed_attendees
        return {
            "venue_name": venue_name,
            "attendees": parsed_attendees,
            "extras": extras,
            "estimated_total_eur": base_total + extra_cost,
            "base_total_eur": base_total,
            "extra_cost_eur": extra_cost,
        }

    messages = [
        {
            "role": "system",
            "content": (
                "You are a planning agent working with a small local toolset. "
                "Use only the tools you actually need. "
                "Do not call every tool by default. "
                "If the user already supplied enough information, answer with minimal extra work. "
                "When recommending an option, make the tradeoffs explicit."
            ),
        },
        {"role": "user", "content": user_prompt},
    ]

    result = run.create_model_turn(messages, model=model_name)
    final_text = extract_text(result.assistant_message)
    run.finish(
        result.assistant_message,
        artifacts=[
            {
                "kind": "plan_summary",
                "label": f"{args.scenario}-final-answer",
                "summary": final_text[:300] if final_text else "No final text was returned.",
                "metadata": {"scenario": args.scenario, "tool_count": len(result.executed_tools)},
            }
        ],
    )
    print(f"Scenario: {args.scenario}")
    print(f"Tools executed: {len(result.executed_tools)}")
    print(final_text)


if __name__ == "__main__":
    main()
