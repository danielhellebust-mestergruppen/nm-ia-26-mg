#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.offline_evaluator import run_evaluation


def _metric(payload: dict) -> float:
    by = payload.get("summary_by_policy", {})
    vals = []
    for k in ("grid", "random", "entropy", "grid_then_entropy"):
        v = by.get(k, {})
        if isinstance(v, dict):
            vals.append(float(v.get("mean_final_score", 0.0)))
    return max(vals) if vals else 0.0


def _parse_list(raw: str, cast) -> list:
    return [cast(x.strip()) for x in raw.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune spatial predictor params using offline replay.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "spatial_tuning.json")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--limit-samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--overlap-discount", type=float, default=0.0)
    parser.add_argument("--floor", type=float, default=0.01)
    parser.add_argument("--tau-grid", default="6.0,7.5,9.0")
    parser.add_argument("--smoothing-weight-grid", default="0.12,0.22,0.32")
    parser.add_argument("--smoothing-passes-grid", default="1,2")
    parser.add_argument("--local-count-threshold-grid", default="3,5,7")
    parser.add_argument("--local-blend-max-grid", default="0.12,0.22,0.32")
    parser.add_argument("--alpha-count-weight-grid", default="0.12,0.22,0.32")
    parser.add_argument("--alpha-entropy-weight-grid", default="0.05,0.10,0.15")
    parser.add_argument("--alpha-distance-weight-grid", default="0.08,0.12,0.18")
    parser.add_argument("--influence-settlement-weight-grid", default="0.35,0.55,0.75")
    parser.add_argument("--influence-port-weight-grid", default="0.25,0.45,0.65")
    parser.add_argument("--influence-ruin-weight-grid", default="0.10,0.20,0.30")
    parser.add_argument("--influence-forest-weight-grid", default="0.10,0.18,0.26")
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument("--coarse-only", action="store_true", help="Use paired-index coarse search instead of full cartesian product")
    args = parser.parse_args()

    tau_grid = _parse_list(args.tau_grid, float)
    smooth_weight_grid = _parse_list(args.smoothing_weight_grid, float)
    smooth_passes_grid = _parse_list(args.smoothing_passes_grid, int)
    local_count_threshold_grid = _parse_list(args.local_count_threshold_grid, int)
    local_blend_max_grid = _parse_list(args.local_blend_max_grid, float)
    alpha_count_weight_grid = _parse_list(args.alpha_count_weight_grid, float)
    alpha_entropy_weight_grid = _parse_list(args.alpha_entropy_weight_grid, float)
    alpha_distance_weight_grid = _parse_list(args.alpha_distance_weight_grid, float)
    influence_settlement_weight_grid = _parse_list(args.influence_settlement_weight_grid, float)
    influence_port_weight_grid = _parse_list(args.influence_port_weight_grid, float)
    influence_ruin_weight_grid = _parse_list(args.influence_ruin_weight_grid, float)
    influence_forest_weight_grid = _parse_list(args.influence_forest_weight_grid, float)

    if args.coarse_only:
        n = max(
            len(tau_grid),
            len(smooth_weight_grid),
            len(smooth_passes_grid),
            len(local_count_threshold_grid),
            len(local_blend_max_grid),
            len(alpha_count_weight_grid),
            len(alpha_entropy_weight_grid),
            len(alpha_distance_weight_grid),
            len(influence_settlement_weight_grid),
            len(influence_port_weight_grid),
            len(influence_ruin_weight_grid),
            len(influence_forest_weight_grid),
        )
        combos = []
        for i in range(n):
            combos.append(
                (
                    tau_grid[i % len(tau_grid)],
                    smooth_weight_grid[i % len(smooth_weight_grid)],
                    smooth_passes_grid[i % len(smooth_passes_grid)],
                    local_count_threshold_grid[i % len(local_count_threshold_grid)],
                    local_blend_max_grid[i % len(local_blend_max_grid)],
                    alpha_count_weight_grid[i % len(alpha_count_weight_grid)],
                    alpha_entropy_weight_grid[i % len(alpha_entropy_weight_grid)],
                    alpha_distance_weight_grid[i % len(alpha_distance_weight_grid)],
                    influence_settlement_weight_grid[i % len(influence_settlement_weight_grid)],
                    influence_port_weight_grid[i % len(influence_port_weight_grid)],
                    influence_ruin_weight_grid[i % len(influence_ruin_weight_grid)],
                    influence_forest_weight_grid[i % len(influence_forest_weight_grid)],
                )
            )
    else:
        combos = list(
            itertools.product(
                tau_grid,
                smooth_weight_grid,
                smooth_passes_grid,
                local_count_threshold_grid,
                local_blend_max_grid,
                alpha_count_weight_grid,
                alpha_entropy_weight_grid,
                alpha_distance_weight_grid,
                influence_settlement_weight_grid,
                influence_port_weight_grid,
                influence_ruin_weight_grid,
                influence_forest_weight_grid,
            )
        )
    trials = []
    for (
        tau,
        smoothing_weight,
        smoothing_passes,
        local_count_threshold,
        local_blend_max,
        alpha_count_weight,
        alpha_entropy_weight,
        alpha_distance_weight,
        influence_settlement_weight,
        influence_port_weight,
        influence_ruin_weight,
        influence_forest_weight,
    ) in combos:
        payload = run_evaluation(
            rounds_dir=args.rounds_dir,
            query_budget=args.query_budget,
            viewport_w=args.viewport_w,
            viewport_h=args.viewport_h,
            policies=["grid", "random", "entropy", "grid_then_entropy"],
            overlap_discount=args.overlap_discount,
            floor=args.floor,
            seed=args.seed,
            limit_samples=args.limit_samples,
            predictor_mode="spatial",
            tau=tau,
            smoothing_weight=smoothing_weight,
            smoothing_passes=smoothing_passes,
            local_count_threshold=local_count_threshold,
            local_blend_max=local_blend_max,
            alpha_count_weight=alpha_count_weight,
            alpha_entropy_weight=alpha_entropy_weight,
            alpha_distance_weight=alpha_distance_weight,
            influence_settlement_weight=influence_settlement_weight,
            influence_port_weight=influence_port_weight,
            influence_ruin_weight=influence_ruin_weight,
            influence_forest_weight=influence_forest_weight,
            distance_backend=args.distance_backend,
        )
        score = _metric(payload)
        trials.append(
            {
                "tau": tau,
                "smoothing_weight": smoothing_weight,
                "smoothing_passes": smoothing_passes,
                "local_count_threshold": local_count_threshold,
                "local_blend_max": local_blend_max,
                "alpha_count_weight": alpha_count_weight,
                "alpha_entropy_weight": alpha_entropy_weight,
                "alpha_distance_weight": alpha_distance_weight,
                "influence_settlement_weight": influence_settlement_weight,
                "influence_port_weight": influence_port_weight,
                "influence_ruin_weight": influence_ruin_weight,
                "influence_forest_weight": influence_forest_weight,
                "best_policy_mean_final_score": score,
                "summary_by_policy": payload.get("summary_by_policy", {}),
            }
        )
    best = max(trials, key=lambda x: x["best_policy_mean_final_score"]) if trials else None
    report = {
        "config": {
            "rounds_dir": str(args.rounds_dir),
            "query_budget": args.query_budget,
            "viewport_w": args.viewport_w,
            "viewport_h": args.viewport_h,
            "limit_samples": args.limit_samples,
            "seed": args.seed,
            "overlap_discount": args.overlap_discount,
            "floor": args.floor,
        },
        "trials": trials,
        "best": best,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"best": best}, indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

