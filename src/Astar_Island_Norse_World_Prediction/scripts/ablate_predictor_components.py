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


def _entropy_score(payload: dict) -> float:
    by_policy = payload.get("summary_by_policy", {})
    ent = by_policy.get("entropy")
    if not isinstance(ent, dict):
        return 0.0
    return float(ent.get("mean_final_score", 0.0))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ablate spatial predictor components offline.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "ablation_report.json")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--policies", default="grid,entropy")
    parser.add_argument("--limit-samples", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--overlap-discount", type=float, default=0.0)
    parser.add_argument("--floor", type=float, default=0.01)
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    shared = {
        "rounds_dir": args.rounds_dir,
        "query_budget": args.query_budget,
        "viewport_w": args.viewport_w,
        "viewport_h": args.viewport_h,
        "policies": policies,
        "overlap_discount": args.overlap_discount,
        "floor": args.floor,
        "seed": args.seed,
        "limit_samples": args.limit_samples,
        "predictor_mode": "spatial",
    }
    experiments = [
        ("full_spatial", {}),
        ("no_local_evidence", {"disable_local_evidence": True}),
        ("no_neighbor_smoothing", {"disable_neighbor_smoothing": True}),
        ("no_settlement_influence", {"disable_settlement_influence": True}),
        ("no_dynamic_alpha", {"disable_dynamic_alpha": True}),
        ("baseline_predictor", {"predictor_mode": "baseline"}),
    ]
    rows = []
    for name, overrides in experiments:
        cfg = dict(shared)
        cfg.update(overrides)
        payload = run_evaluation(**cfg)
        rows.append(
            {
                "experiment": name,
                "config": payload.get("config", {}),
                "summary_by_policy": payload.get("summary_by_policy", {}),
                "entropy_mean_final_score": _entropy_score(payload),
            }
        )

    best = max(rows, key=lambda r: r["entropy_mean_final_score"]) if rows else None
    report = {"experiments": rows, "best_experiment": best}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"best_experiment": best}, indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

