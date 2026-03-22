#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze best-known deploy config from tuning/ablation reports.")
    parser.add_argument(
        "--tuning-report",
        type=Path,
        default=Path(ROOT / "data/reports/spatial_tuning_expanded_coarse.json"),
    )
    parser.add_argument(
        "--ablation-report",
        type=Path,
        default=Path(ROOT / "data/reports/offline_evaluator_report.json"),
    )
    parser.add_argument(
        "--eval-report",
        type=Path,
        default=Path(ROOT / "data/reports/offline_evaluator_report.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(ROOT / "data/reports/best_known_deploy_config.json"),
    )
    args = parser.parse_args()

    tuning = _load(args.tuning_report)
    ablation = _load(args.ablation_report)
    eval_report = _load(args.eval_report)

    best_tune = tuning.get("best", {})
    spatial_priors = {
        "influence_tau": float(best_tune.get("tau", 4.5)),
        "smoothing_weight": float(best_tune.get("smoothing_weight", 0.12)),
        "smoothing_passes": int(best_tune.get("smoothing_passes", 1)),
        "local_count_threshold": int(best_tune.get("local_count_threshold", 5)),
        "local_blend_max": float(best_tune.get("local_blend_max", 0.22)),
        "alpha_count_weight": float(best_tune.get("alpha_count_weight", 0.22)),
        "alpha_entropy_weight": float(best_tune.get("alpha_entropy_weight", 0.10)),
        "alpha_distance_weight": float(best_tune.get("alpha_distance_weight", 0.12)),
        "influence_settlement_weight": float(best_tune.get("influence_settlement_weight", 0.55)),
        "influence_port_weight": float(best_tune.get("influence_port_weight", 0.45)),
        "influence_ruin_weight": float(best_tune.get("influence_ruin_weight", 0.20)),
        "influence_forest_weight": float(best_tune.get("influence_forest_weight", 0.18)),
        "distance_backend": "python",
    }

    best_ablation = ablation.get("best_experiment", {})
    if best_ablation.get("experiment") == "no_neighbor_smoothing":
        spatial_priors["smoothing_weight"] = 0.0
        spatial_priors["smoothing_passes"] = 0

    summary = eval_report.get("summary_by_policy", {})
    best_policy = "grid"
    best_score = -1.0
    for p in ("grid", "random", "entropy", "grid_then_entropy"):
        sc = float(summary.get(p, {}).get("mean_final_score", -1.0))
        if sc > best_score:
            best_score = sc
            best_policy = p

    deploy = {
        "predictor_mode": "time_socio_unet",
        "query_policy": best_policy,
        "grid_warmup_queries": 2,
        "overlap_discount": 0.5,
        "entropy_mode": "plain",
        "entropy_temp": 1.0,
        "historical_overlap_penalty": 0.0,
        "predict_time_guard_ms": 300.0,
        "spatial_priors": spatial_priors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(deploy, indent=2) + "\n", encoding="utf-8")
    # Also mirror priors to default spatial priors file for runner convenience.
    mirror = args.out.with_name("spatial_priors_from_replay.json")
    mirror.write_text(json.dumps(spatial_priors, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(deploy, indent=2))


if __name__ == "__main__":
    main()

