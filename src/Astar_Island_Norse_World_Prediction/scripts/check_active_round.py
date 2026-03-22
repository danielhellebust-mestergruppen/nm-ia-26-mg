#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file


def _pick_active_round(rounds: list[dict]) -> dict | None:
    active = [r for r in rounds if r.get("status") == "active"]
    if not active:
        return None
    return sorted(active, key=lambda x: x.get("round_number", 0))[-1]


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Sanity-check auth and active round state.")
    parser.add_argument("--token", default="")
    parser.add_argument(
        "--base-url",
        default="",
    )
    args = parser.parse_args()
    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")

    if not token:
        raise RuntimeError("Missing token. Set AINM_BEARER_TOKEN or pass --token.")

    client = AstarApiClient(bearer_token=token, base_url=base_url)
    rounds = client.list_rounds()
    active = _pick_active_round(rounds)
    budget = client.get_budget()

    payload = {
        "active_round": active,
        "budget": budget,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

