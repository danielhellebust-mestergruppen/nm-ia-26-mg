#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file
from src.offline_harness import save_json
from src.types import NUM_SEEDS


def _is_round_completed(round_obj: dict[str, Any]) -> bool:
    return round_obj.get("status") in {"completed", "scoring"}


def _safe_replay(client: AstarApiClient, round_id: str, seed_index: int) -> dict[str, Any] | None:
    try:
        return client.replay(round_id, seed_index)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: failed replay({round_id}, seed={seed_index}): {exc}")
        return None


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Backfill replay payloads for completed rounds.")
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--workspace", type=Path, default=ROOT / "data")
    parser.add_argument("--limit-rounds", type=int, default=0, help="0 means all completed rounds")
    parser.add_argument("--only-round-id", default="", help="If set, only fetch this round id")
    args = parser.parse_args()

    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    if not token:
        raise RuntimeError(
            "Missing bearer token. Set AINM_BEARER_TOKEN in shell or astar_island/.env or pass --token."
        )
    client = AstarApiClient(bearer_token=token, base_url=base_url)

    rounds: list[dict[str, Any]]
    if args.only_round_id:
        rounds = [{"id": args.only_round_id, "status": "completed", "round_number": 0}]
    else:
        mine = client.my_rounds()
        rounds = sorted([r for r in mine if _is_round_completed(r)], key=lambda x: x.get("round_number", 0))
        if args.limit_rounds > 0:
            rounds = rounds[-args.limit_rounds :]

    replays_saved = 0
    replays_missing = 0
    for r in rounds:
        round_id = str(r["id"])
        for seed_index in range(NUM_SEEDS):
            payload = _safe_replay(client, round_id, seed_index)
            if payload is None:
                replays_missing += 1
                continue
            out = args.workspace / "replays" / f"{round_id}_seed{seed_index}.json"
            save_json(out, payload)
            replays_saved += 1

    report = {
        "completed_rounds_considered": len(rounds),
        "replays_saved": replays_saved,
        "replays_failed": replays_missing,
        "workspace": str(args.workspace),
    }
    save_json(args.workspace / "reports" / "replay_backfill_report.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

