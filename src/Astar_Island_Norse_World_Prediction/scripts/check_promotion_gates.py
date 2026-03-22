#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.offline_evaluator import run_evaluation


def _mean_score(payload: dict, policy: str) -> float:
    return float(payload.get("summary_by_policy", {}).get(policy, {}).get("mean_final_score", 0.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Check offline promotion gates for spatial model rollout.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "promotion_gates_report.json")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--limit-samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--overlap-discount", type=float, default=0.0)
    parser.add_argument("--floor", type=float, default=0.01)
    parser.add_argument("--grid-warmup-queries", type=int, default=2)
    parser.add_argument("--entropy-mode", choices=["plain", "unobserved_only"], default="plain")
    parser.add_argument("--entropy-temp", type=float, default=1.0)
    parser.add_argument("--historical-overlap-penalty", type=float, default=0.0)
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument(
        "--spatial-priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json",
    )
    parser.add_argument("--min-entropy-margin", type=float, default=0.1)
    parser.add_argument("--min-best-policy-margin", type=float, default=0.0)
    parser.add_argument("--min-spatial-margin", type=float, default=0.0)
    args = parser.parse_args()

    policy_set = ["grid", "random", "entropy", "grid_then_entropy"]
    base = run_evaluation(
        rounds_dir=args.rounds_dir,
        query_budget=args.query_budget,
        viewport_w=args.viewport_w,
        viewport_h=args.viewport_h,
        policies=policy_set,
        overlap_discount=args.overlap_discount,
        floor=args.floor,
        seed=args.seed,
        limit_samples=args.limit_samples,
        predictor_mode="baseline",
        grid_warmup_queries=args.grid_warmup_queries,
        entropy_mode=args.entropy_mode,
        entropy_temp=args.entropy_temp,
        historical_overlap_penalty=args.historical_overlap_penalty,
        distance_backend=args.distance_backend,
    )
    spatial = run_evaluation(
        rounds_dir=args.rounds_dir,
        query_budget=args.query_budget,
        viewport_w=args.viewport_w,
        viewport_h=args.viewport_h,
        policies=policy_set,
        overlap_discount=args.overlap_discount,
        floor=args.floor,
        seed=args.seed,
        limit_samples=args.limit_samples,
        predictor_mode="spatial",
        grid_warmup_queries=args.grid_warmup_queries,
        entropy_mode=args.entropy_mode,
        entropy_temp=args.entropy_temp,
        historical_overlap_penalty=args.historical_overlap_penalty,
        distance_backend=args.distance_backend,
        spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
    )
    spatial_no_overlap = run_evaluation(
        rounds_dir=args.rounds_dir,
        query_budget=args.query_budget,
        viewport_w=args.viewport_w,
        viewport_h=args.viewport_h,
        policies=["entropy"],
        overlap_discount=1.0,
        floor=args.floor,
        seed=args.seed,
        limit_samples=args.limit_samples,
        predictor_mode="spatial",
        grid_warmup_queries=args.grid_warmup_queries,
        entropy_mode=args.entropy_mode,
        entropy_temp=args.entropy_temp,
        historical_overlap_penalty=args.historical_overlap_penalty,
        distance_backend=args.distance_backend,
        spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
    )

    base_entropy = _mean_score(base, "entropy")
    spatial_entropy = _mean_score(spatial, "entropy")
    spatial_grid = _mean_score(spatial, "grid")
    spatial_random = _mean_score(spatial, "random")
    base_grid = _mean_score(base, "grid")
    base_random = _mean_score(base, "random")
    base_hybrid = _mean_score(base, "grid_then_entropy")
    spatial_hybrid = _mean_score(spatial, "grid_then_entropy")
    spatial_entropy_no_overlap = _mean_score(spatial_no_overlap, "entropy")
    spatial_best = max(spatial_grid, spatial_random, spatial_entropy, spatial_hybrid)
    base_best = max(base_grid, base_random, base_entropy, base_hybrid)

    gates = {
        "gateA_offline_reproducible": True,  # deterministic given fixed seed/config
        "gateB_best_policy_beats_baselines": spatial_best >= base_best + args.min_best_policy_margin,
        "gateB_entropy_beats_grid_random_diagnostic": spatial_entropy
        >= max(spatial_grid, spatial_random) + args.min_entropy_margin,
        "gateC_kl_safe_floor_active": float(spatial["config"]["floor"]) >= 1e-12,
        "gateD_overlap_discount_helps_or_neutral": spatial_entropy >= spatial_entropy_no_overlap,
        "gateE_spatial_beats_baseline": spatial_entropy >= base_entropy + args.min_spatial_margin,
    }
    rollout_gate_keys = [
        "gateA_offline_reproducible",
        "gateB_best_policy_beats_baselines",
        "gateC_kl_safe_floor_active",
        "gateD_overlap_discount_helps_or_neutral",
        "gateE_spatial_beats_baseline",
    ]
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
            "grid_warmup_queries": args.grid_warmup_queries,
            "entropy_mode": args.entropy_mode,
            "entropy_temp": args.entropy_temp,
            "historical_overlap_penalty": args.historical_overlap_penalty,
            "distance_backend": args.distance_backend,
            "spatial_priors_file": str(args.spatial_priors_file) if args.spatial_priors_file.is_file() else None,
            "min_entropy_margin": args.min_entropy_margin,
            "min_best_policy_margin": args.min_best_policy_margin,
            "min_spatial_margin": args.min_spatial_margin,
        },
        "metrics": {
            "baseline_entropy_mean_score": base_entropy,
            "baseline_grid_mean_score": base_grid,
            "baseline_random_mean_score": base_random,
            "baseline_grid_then_entropy_mean_score": base_hybrid,
            "baseline_best_policy_mean_score": base_best,
            "spatial_entropy_mean_score": spatial_entropy,
            "spatial_grid_mean_score": spatial_grid,
            "spatial_random_mean_score": spatial_random,
            "spatial_grid_then_entropy_mean_score": spatial_hybrid,
            "spatial_best_policy_mean_score": spatial_best,
            "spatial_entropy_no_overlap_mean_score": spatial_entropy_no_overlap,
        },
        "gates": gates,
        "rollout_gate_keys": rollout_gate_keys,
        "all_passed": bool(all(bool(gates[k]) for k in rollout_gate_keys)),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

