#!/usr/bin/env python3
from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.offline_evaluator import run_evaluation


def _category(name: str) -> str | None:
    if any(k in name for k in ("_dijkstra_influence_from_source", "_build_settlement_influence")):
        return "dijkstra_influence"
    if "_sample_realized_grid" in name:
        return "sampling"
    if any(k in name for k in ("_pick_next_viewport", "_integral_image", "_rect_sums_from_integral")):
        return "entropy_scoring"
    if any(k in name for k in ("build_prediction_tensor_spatial", "build_prediction_tensor")):
        return "prediction"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile offline_evaluator and summarize hotspots.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--policies", default="grid,entropy")
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--limit-samples", type=int, default=20)
    parser.add_argument("--predictor-mode", choices=["baseline", "spatial", "unet", "convlstm"], default="spatial")
    parser.add_argument("--out-json", type=Path, default=ROOT / "data" / "reports" / "offline_profile_report.json")
    parser.add_argument("--out-txt", type=Path, default=ROOT / "data" / "reports" / "offline_profile_top.txt")
    parser.add_argument("--top-n", type=int, default=40)
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    profiler = cProfile.Profile()
    profiler.enable()
    payload = run_evaluation(
        rounds_dir=args.rounds_dir,
        query_budget=args.query_budget,
        viewport_w=args.viewport_w,
        viewport_h=args.viewport_h,
        policies=policies,
        overlap_discount=0.0,
        floor=0.01,
        seed=args.seed,
        limit_samples=args.limit_samples,
        predictor_mode=args.predictor_mode,
    )
    profiler.disable()

    stats = pstats.Stats(profiler)
    total_tt = float(stats.total_tt) if stats.total_tt else 1e-12
    cat_totals = {
        "dijkstra_influence": 0.0,
        "sampling": 0.0,
        "entropy_scoring": 0.0,
        "prediction": 0.0,
    }
    for key, val in stats.stats.items():
        funcname = key[2]
        tt = float(val[2])  # internal time
        cat = _category(funcname)
        if cat is not None:
            cat_totals[cat] += tt

    cat_percent = {k: (100.0 * v / total_tt) for k, v in cat_totals.items()}

    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(args.top_n)
    text = stream.getvalue()
    args.out_txt.parent.mkdir(parents=True, exist_ok=True)
    args.out_txt.write_text(text, encoding="utf-8")

    report = {
        "config": {
            "rounds_dir": str(args.rounds_dir),
            "query_budget": args.query_budget,
            "viewport_w": args.viewport_w,
            "viewport_h": args.viewport_h,
            "policies": policies,
            "seed": args.seed,
            "limit_samples": args.limit_samples,
            "predictor_mode": args.predictor_mode,
            "top_n": args.top_n,
        },
        "total_internal_seconds": total_tt,
        "category_seconds": cat_totals,
        "category_percent_of_total": cat_percent,
        "summary_by_policy": payload.get("summary_by_policy", {}),
        "top_stats_text_file": str(args.out_txt),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

