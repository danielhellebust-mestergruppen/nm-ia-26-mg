#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file
from src.offline_harness import evaluate_against_analysis, load_json, save_json
from src.scoring import round_score
from src.types import NUM_SEEDS
from src.visualize import save_error_visuals, save_prediction_visuals


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Evaluate predictions against analysis endpoint.")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=ROOT / "data",
    )
    parser.add_argument("--save-visuals", action="store_true")
    args = parser.parse_args()
    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    if not token:
        raise RuntimeError(
            "Missing bearer token. Set AINM_BEARER_TOKEN in shell or astar_island/.env or pass --token."
        )

    client = AstarApiClient(bearer_token=token, base_url=base_url)
    per_seed_scores: list[float] = []
    report: dict[str, object] = {"round_id": args.round_id, "seeds": []}

    for seed_index in range(NUM_SEEDS):
        pred_path = args.workspace / "predictions" / f"{args.round_id}_seed{seed_index}.json"
        if not pred_path.is_file():
            report["seeds"].append({"seed_index": seed_index, "error": "missing_prediction"})
            per_seed_scores.append(0.0)
            continue

        pred = np.asarray(load_json(pred_path), dtype=np.float64)
        analysis = client.analysis(args.round_id, seed_index)
        seed_metrics = evaluate_against_analysis(pred, analysis)
        report["seeds"].append({"seed_index": seed_index, **seed_metrics})
        per_seed_scores.append(seed_metrics["local_score"])

        if args.save_visuals:
            gt = np.asarray(analysis["ground_truth"], dtype=np.float64)
            save_prediction_visuals(pred, args.workspace / "reports", f"{args.round_id}_seed{seed_index}_pred")
            save_error_visuals(pred, gt, args.workspace / "reports", f"{args.round_id}_seed{seed_index}")

    report["local_round_score"] = round_score(per_seed_scores)
    out_path = args.workspace / "reports" / f"{args.round_id}_eval.json"
    save_json(out_path, report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

