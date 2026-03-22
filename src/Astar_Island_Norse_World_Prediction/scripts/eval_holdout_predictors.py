#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

def _parse_int_list(raw: str) -> list[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_str_list(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


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


def _make_holdout_dir(files: list[Path]) -> Path:
    out = ROOT / "data" / "reports" / f"_holdout_tmp_{uuid.uuid4().hex[:10]}"
    out.mkdir(parents=True, exist_ok=True)
    for fp in files:
        target = out / fp.name
        try:
            os.symlink(fp, target)
        except Exception:
            shutil.copy2(fp, target)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate baseline/spatial/unet/spatial_unet on a strict holdout split. "
            "Default holdout is latest completed round."
        )
    )
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument(
        "--holdout-rounds",
        default="",
        help="Comma-separated holdout round numbers. Empty -> latest completed round only.",
    )
    parser.add_argument("--policy", choices=["grid", "random", "entropy", "grid_then_entropy"], default="entropy")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true", help="Validate split/config and exit without evaluation.")
    parser.add_argument(
        "--predictor-modes",
        default="baseline,spatial,unet,spatial_unet",
        help="Comma-separated modes from {baseline,spatial,unet,spatial_unet}.",
    )
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--overlap-discount", type=float, default=0.5)
    parser.add_argument("--floor", type=float, default=0.01)
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--limit-samples", type=int, default=0)
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument("--hybrid-unet-weight", type=float, default=0.30)
    parser.add_argument("--unet-model-path", type=Path, default=ROOT / "data" / "reports" / "unet_predictor.pth")
    parser.add_argument("--spatial-priors-file", type=Path, default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "holdout_predictor_eval.json")
    args = parser.parse_args()

    scanned = _scan_round_files(args.rounds_dir)
    if not scanned:
        raise RuntimeError(f"No valid *_analysis.json files with round_number in {args.rounds_dir}")
    all_rounds = sorted({rn for _, rn in scanned})
    if args.holdout_rounds.strip():
        holdout_rounds = sorted(set(_parse_int_list(args.holdout_rounds)))
    else:
        holdout_rounds = [all_rounds[-1]]

    holdout_files = [fp for fp, rn in scanned if rn in set(holdout_rounds)]
    if not holdout_files:
        raise RuntimeError(f"No holdout files found for rounds={holdout_rounds}")

    predictor_modes = _parse_str_list(args.predictor_modes)
    valid_modes = {"baseline", "spatial", "unet", "spatial_unet"}
    unknown = [m for m in predictor_modes if m not in valid_modes]
    if unknown:
        raise RuntimeError(f"Unknown predictor modes: {unknown}; valid={sorted(valid_modes)}")
    if not predictor_modes:
        raise RuntimeError("No predictor modes selected")
    predictors: dict[str, dict[str, float | dict]] = {}
    if not args.dry_run:
        from scripts.offline_evaluator import run_evaluation

        holdout_dir = _make_holdout_dir(holdout_files)
        try:
            for mode in predictor_modes:
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
                    predictor_mode=mode,
                    distance_backend=args.distance_backend,
                    spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
                    hybrid_unet_weight=args.hybrid_unet_weight,
                    unet_model_path=args.unet_model_path if args.unet_model_path.is_file() else None,
                )
                by_policy = payload.get("summary_by_policy", {})
                row = by_policy.get(args.policy, {})
                predictors[mode] = {
                    "mean_final_score": float(row.get("mean_final_score", 0.0)),
                    "mean_final_weighted_kl": float(row.get("mean_final_weighted_kl", 0.0)),
                    "std_final_score": float(row.get("std_final_score", 0.0)),
                    "summary_by_policy": by_policy,
                }
        finally:
            shutil.rmtree(holdout_dir, ignore_errors=True)

    out = {
        "holdout_round_numbers": holdout_rounds,
        "holdout_sample_count": len(holdout_files),
        "policy_used": args.policy,
        "dry_run": bool(args.dry_run),
        "predictors": predictors,
        "config": {
            "query_budget": args.query_budget,
            "viewport_w": args.viewport_w,
            "viewport_h": args.viewport_h,
            "overlap_discount": args.overlap_discount,
            "floor": args.floor,
            "seed": args.seed,
            "limit_samples": args.limit_samples,
            "distance_backend": args.distance_backend,
            "hybrid_unet_weight": args.hybrid_unet_weight,
            "unet_model_path": str(args.unet_model_path) if args.unet_model_path.is_file() else None,
            "spatial_priors_file": str(args.spatial_priors_file) if args.spatial_priors_file.is_file() else None,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

