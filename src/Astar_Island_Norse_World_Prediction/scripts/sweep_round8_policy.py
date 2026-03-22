#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import itertools
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_str_list(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def _best_policy(summary_by_policy: dict[str, Any]) -> tuple[str, float, float]:
    best_name = "grid"
    best_score = -1.0
    best_std = 1e9
    for p in ("grid", "random", "entropy", "grid_then_entropy"):
        row = summary_by_policy.get(p, {})
        if not isinstance(row, dict):
            continue
        score = float(row.get("mean_final_score", -1.0))
        std = float(row.get("std_final_score", 1e9))
        if score > best_score or (abs(score - best_score) <= 1e-12 and std < best_std):
            best_name = p
            best_score = score
            best_std = std
    return best_name, best_score, best_std


def _load_control_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _submission_command(best: dict[str, Any]) -> str:
    policy = str(best["best_policy"])
    parts = [
        "python scripts/run_active_round.py",
        "--queries-per-seed 8",
        "--predictor-mode spatial",
        f"--query-policy {policy}",
        "--predict-time-guard-ms 300",
        "--submit",
        "--save-visuals",
    ]
    if policy == "grid_then_entropy":
        parts.append(f"--grid-warmup-queries {best['grid_warmup_queries']}")
    parts.append(f"--overlap-discount {best['overlap_discount']}")
    parts.append(f"--entropy-mode {best['entropy_mode']}")
    parts.append(f"--entropy-temp {best['entropy_temp']}")
    parts.append(f"--historical-overlap-penalty {best['historical_overlap_penalty']}")
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Narrow policy sweep and ranked recommendation for next round.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "round8_policy_sweep.json")
    parser.add_argument(
        "--control-config",
        type=Path,
        default=ROOT / "data" / "reports" / "best_known_deploy_config.json",
        help="Control config to compare against (optional)",
    )
    parser.add_argument("--limit-samples", type=int, default=30)
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument("--spatial-priors-file", type=Path, default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json")
    parser.add_argument("--overlap-grid", default="0.4,0.5,0.6")
    parser.add_argument("--entropy-temp-grid", default="0.95,1.0,1.05")
    parser.add_argument("--historical-penalty-grid", default="0.0,0.002,0.005")
    parser.add_argument("--entropy-mode-grid", default="plain,unobserved_only")
    parser.add_argument("--grid-warmup-grid", default="1,2,3")
    parser.add_argument(
        "--fast-mode",
        action="store_true",
        help=(
            "Speed up sweep by computing grid/random once and sweeping only "
            "entropy/grid_then_entropy per combo."
        ),
    )
    args = parser.parse_args()
    from scripts.offline_evaluator import run_evaluation

    overlap_grid = _parse_float_list(args.overlap_grid)
    entropy_temp_grid = _parse_float_list(args.entropy_temp_grid)
    historical_penalty_grid = _parse_float_list(args.historical_penalty_grid)
    entropy_mode_grid = _parse_str_list(args.entropy_mode_grid)
    grid_warmup_grid = [int(x) for x in _parse_float_list(args.grid_warmup_grid)]

    control = _load_control_config(args.control_config)
    control_score = None
    if control:
        c = run_evaluation(
            rounds_dir=args.rounds_dir,
            query_budget=args.query_budget,
            viewport_w=15,
            viewport_h=15,
            policies=["grid", "random", "entropy", "grid_then_entropy"],
            overlap_discount=float(control.get("overlap_discount", 0.5)),
            floor=0.01,
            seed=args.seed,
            limit_samples=args.limit_samples,
            predictor_mode="spatial",
            grid_warmup_queries=int(control.get("grid_warmup_queries", 2)),
            entropy_mode=str(control.get("entropy_mode", "plain")),
            entropy_temp=float(control.get("entropy_temp", 1.0)),
            historical_overlap_penalty=float(control.get("historical_overlap_penalty", 0.0)),
            distance_backend=args.distance_backend,
            spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
        )
        _, control_score, _ = _best_policy(c.get("summary_by_policy", {}))

    rows: list[dict[str, Any]] = []
    combos = list(
        itertools.product(
        overlap_grid,
        entropy_temp_grid,
        historical_penalty_grid,
        entropy_mode_grid,
        grid_warmup_grid,
    )
    )
    print(f"policy_sweep combos={len(combos)} fast_mode={bool(args.fast_mode)}")

    fixed_grid_random: dict[str, Any] = {}
    if args.fast_mode:
        fixed = run_evaluation(
            rounds_dir=args.rounds_dir,
            query_budget=args.query_budget,
            viewport_w=15,
            viewport_h=15,
            policies=["grid", "random"],
            overlap_discount=0.5,
            floor=0.01,
            seed=args.seed,
            limit_samples=args.limit_samples,
            predictor_mode="spatial",
            grid_warmup_queries=2,
            entropy_mode="plain",
            entropy_temp=1.0,
            historical_overlap_penalty=0.0,
            distance_backend=args.distance_backend,
            spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
        )
        fixed_grid_random = dict(fixed.get("summary_by_policy", {}))

    for i, (overlap_discount, entropy_temp, historical_overlap_penalty, entropy_mode, grid_warmup_queries) in enumerate(
        combos, start=1
    ):
        policies = ["entropy", "grid_then_entropy"] if args.fast_mode else ["grid", "random", "entropy", "grid_then_entropy"]
        payload = run_evaluation(
            rounds_dir=args.rounds_dir,
            query_budget=args.query_budget,
            viewport_w=15,
            viewport_h=15,
            policies=policies,
            overlap_discount=overlap_discount,
            floor=0.01,
            seed=args.seed,
            limit_samples=args.limit_samples,
            predictor_mode="spatial",
            grid_warmup_queries=grid_warmup_queries,
            entropy_mode=entropy_mode,
            entropy_temp=entropy_temp,
            historical_overlap_penalty=historical_overlap_penalty,
            distance_backend=args.distance_backend,
            spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
        )
        if args.fast_mode:
            merged_summary = dict(fixed_grid_random)
            merged_summary.update(payload.get("summary_by_policy", {}))
            payload["summary_by_policy"] = merged_summary
        best_name, best_score, best_std = _best_policy(payload["summary_by_policy"])
        rows.append(
            {
                "overlap_discount": overlap_discount,
                "entropy_temp": entropy_temp,
                "historical_overlap_penalty": historical_overlap_penalty,
                "entropy_mode": entropy_mode,
                "grid_warmup_queries": grid_warmup_queries,
                "best_policy": best_name,
                "best_mean_score": best_score,
                "best_std_score": best_std,
                "summary_by_policy": payload["summary_by_policy"],
                "beats_control": (best_score > control_score) if control_score is not None else None,
                "margin_vs_control": (best_score - control_score) if control_score is not None else None,
            }
        )
        if i % 5 == 0 or i == len(combos):
            print(f"progress {i}/{len(combos)} best_so_far={max(r['best_mean_score'] for r in rows):.4f}")

    ranked = sorted(rows, key=lambda r: (r["best_mean_score"], -r["best_std_score"]), reverse=True)
    top = ranked[:10]
    best = ranked[0] if ranked else {}

    result = {
        "config": {
            "rounds_dir": str(args.rounds_dir),
            "limit_samples": args.limit_samples,
            "query_budget": args.query_budget,
            "seed": args.seed,
            "distance_backend": args.distance_backend,
            "spatial_priors_file": str(args.spatial_priors_file) if args.spatial_priors_file.is_file() else None,
            "control_config": str(args.control_config) if args.control_config.is_file() else None,
            "control_best_score": control_score,
        },
        "top_ranked": top,
        "best": best,
        "recommended_submission_command": _submission_command(best) if best else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["best"], indent=2))
    print("recommended_command:")
    print(result["recommended_submission_command"])
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

