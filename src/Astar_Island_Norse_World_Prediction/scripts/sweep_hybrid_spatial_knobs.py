#!/usr/bin/env python3
from __future__ import annotations

import argparse
import itertools
import json
import os
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))


def _parse_float_list(raw: str) -> list[float]:
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _scan_round_files(rounds_dir: Path) -> list[tuple[Path, int]]:
    rows: list[tuple[Path, int]] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        try:
            payload = json.loads(fp.read_text(encoding="utf-8"))
            rn = int(payload.get("round_number", -1))
            if rn > 0:
                rows.append((fp, rn))
        except Exception:
            continue
    return rows


def _make_temp_dir(files: list[Path]) -> Path:
    out = ROOT / "data" / "reports" / f"_hybrid_sweep_tmp_{uuid.uuid4().hex[:10]}"
    out.mkdir(parents=True, exist_ok=True)
    for fp in files:
        target = out / fp.name
        try:
            os.symlink(fp, target)
        except Exception:
            shutil.copy2(fp, target)
    return out


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Sweep own-code hybrid/spatial knobs on strict holdout rounds: "
            "hybrid_unet_weight, coast_port_weight, coast_tau."
        )
    )
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument(
        "--holdout-rounds",
        default="",
        help="Comma-separated holdout rounds. Empty means latest completed round.",
    )
    parser.add_argument("--policy", choices=["grid", "random", "entropy", "grid_then_entropy"], default="entropy")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--overlap-discount", type=float, default=0.5)
    parser.add_argument("--floor", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--limit-samples", type=int, default=0)
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument("--hybrid-weight-grid", default="0.2,0.3,0.4")
    parser.add_argument("--coast-port-weight-grid", default="0.0,0.1,0.2")
    parser.add_argument("--coast-tau-grid", default="4.0,6.0,8.0")
    parser.add_argument(
        "--base-spatial-priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json",
    )
    parser.add_argument(
        "--unet-model-path",
        type=Path,
        default=ROOT / "data" / "reports" / "unet_predictor.pth",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="Print combo count and exit.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "reports" / "hybrid_spatial_knob_sweep.json",
    )
    args = parser.parse_args()

    scanned = _scan_round_files(args.rounds_dir)
    if not scanned:
        raise RuntimeError(f"No valid *_analysis.json files in {args.rounds_dir}")
    all_rounds = sorted({rn for _, rn in scanned})
    holdout_rounds = _parse_int_list(args.holdout_rounds) if args.holdout_rounds.strip() else [all_rounds[-1]]
    holdout_files = [fp for fp, rn in scanned if rn in set(holdout_rounds)]
    if not holdout_files:
        raise RuntimeError(f"No holdout files found for rounds={holdout_rounds}")

    hybrid_grid = _parse_float_list(args.hybrid_weight_grid)
    coast_w_grid = _parse_float_list(args.coast_port_weight_grid)
    coast_tau_grid = _parse_float_list(args.coast_tau_grid)
    combos = list(itertools.product(hybrid_grid, coast_w_grid, coast_tau_grid))

    if args.dry_run:
        payload = {
            "holdout_rounds": holdout_rounds,
            "holdout_sample_count": len(holdout_files),
            "combo_count": len(combos),
            "grids": {
                "hybrid_weight_grid": hybrid_grid,
                "coast_port_weight_grid": coast_w_grid,
                "coast_tau_grid": coast_tau_grid,
            },
        }
        print(json.dumps(payload, indent=2))
        return

    from scripts.offline_evaluator import run_evaluation

    base_priors = _load_json(args.base_spatial_priors_file)
    holdout_dir = _make_temp_dir(holdout_files)
    rows: list[dict[str, Any]] = []
    try:
        for i, (hybrid_w, coast_w, coast_tau) in enumerate(combos, start=1):
            priors = dict(base_priors)
            priors["coast_port_weight"] = float(coast_w)
            priors["coast_tau"] = float(coast_tau)
            priors_fp = holdout_dir / f"_priors_{i}.json"
            priors_fp.write_text(json.dumps(priors, indent=2) + "\n", encoding="utf-8")

            payload = run_evaluation(
                rounds_dir=holdout_dir,
                query_budget=args.query_budget,
                viewport_w=args.viewport_w,
                viewport_h=args.viewport_h,
                policies=[args.policy],
                overlap_discount=args.overlap_discount,
                floor=args.floor,
                seed=args.seed,
                limit_samples=args.limit_samples,
                predictor_mode="spatial_unet",
                distance_backend=args.distance_backend,
                spatial_priors_file=priors_fp,
                hybrid_unet_weight=float(hybrid_w),
                unet_model_path=args.unet_model_path if args.unet_model_path.is_file() else None,
            )
            row = payload.get("summary_by_policy", {}).get(args.policy, {})
            rows.append(
                {
                    "hybrid_unet_weight": float(hybrid_w),
                    "coast_port_weight": float(coast_w),
                    "coast_tau": float(coast_tau),
                    "mean_final_score": float(row.get("mean_final_score", 0.0)),
                    "std_final_score": float(row.get("std_final_score", 0.0)),
                    "mean_final_weighted_kl": float(row.get("mean_final_weighted_kl", 0.0)),
                }
            )
            if i % 5 == 0 or i == len(combos):
                best_so_far = max(r["mean_final_score"] for r in rows) if rows else 0.0
                print(f"progress {i}/{len(combos)} best_mean_final_score={best_so_far:.4f}")

        ranked = sorted(
            rows,
            key=lambda r: (float(r["mean_final_score"]), -float(r["std_final_score"])),
            reverse=True,
        )
        best = ranked[0] if ranked else None

        # Compare best hybrid candidate against spatial-only on same coast knobs.
        compare_spatial = None
        if best is not None:
            best_priors = dict(base_priors)
            best_priors["coast_port_weight"] = float(best["coast_port_weight"])
            best_priors["coast_tau"] = float(best["coast_tau"])
            best_priors_fp = holdout_dir / "_priors_best_spatial.json"
            best_priors_fp.write_text(json.dumps(best_priors, indent=2) + "\n", encoding="utf-8")
            sp_payload = run_evaluation(
                rounds_dir=holdout_dir,
                query_budget=args.query_budget,
                viewport_w=args.viewport_w,
                viewport_h=args.viewport_h,
                policies=[args.policy],
                overlap_discount=args.overlap_discount,
                floor=args.floor,
                seed=args.seed,
                limit_samples=args.limit_samples,
                predictor_mode="spatial",
                distance_backend=args.distance_backend,
                spatial_priors_file=best_priors_fp,
            )
            sp_row = sp_payload.get("summary_by_policy", {}).get(args.policy, {})
            compare_spatial = {
                "mean_final_score": float(sp_row.get("mean_final_score", 0.0)),
                "std_final_score": float(sp_row.get("std_final_score", 0.0)),
                "mean_final_weighted_kl": float(sp_row.get("mean_final_weighted_kl", 0.0)),
                "margin_vs_best_hybrid": (
                    float(best["mean_final_score"]) - float(sp_row.get("mean_final_score", 0.0))
                ),
            }
    finally:
        shutil.rmtree(holdout_dir, ignore_errors=True)

    out = {
        "holdout_rounds": holdout_rounds,
        "holdout_sample_count": len(holdout_files),
        "policy_used": args.policy,
        "combo_count": len(combos),
        "best": best,
        "top_ranked": ranked[: max(1, int(args.top_k))],
        "spatial_compare_at_best_coast": compare_spatial,
        "config": {
            "query_budget": args.query_budget,
            "viewport_w": args.viewport_w,
            "viewport_h": args.viewport_h,
            "overlap_discount": args.overlap_discount,
            "floor": args.floor,
            "seed": args.seed,
            "limit_samples": args.limit_samples,
            "distance_backend": args.distance_backend,
            "base_spatial_priors_file": str(args.base_spatial_priors_file) if args.base_spatial_priors_file.is_file() else None,
            "unet_model_path": str(args.unet_model_path) if args.unet_model_path.is_file() else None,
            "hybrid_weight_grid": hybrid_grid,
            "coast_port_weight_grid": coast_w_grid,
            "coast_tau_grid": coast_tau_grid,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out.get("best"), indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

