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
from src.types import NUM_SEEDS, grid_value_to_class_index


def _pick_active_round(rounds: list[dict]) -> dict:
    active = [r for r in rounds if r.get("status") == "active"]
    if not active:
        raise RuntimeError("No active round found")
    return sorted(active, key=lambda x: x.get("round_number", 0))[-1]


def _load_prediction(path: Path) -> np.ndarray:
    return np.asarray(json.loads(path.read_text(encoding="utf-8")), dtype=np.float64)


def _seed_uncertainty(pred: np.ndarray) -> float:
    # normalized entropy + low-confidence fraction + dynamic mass
    eps = 1e-12
    p = np.clip(pred, eps, 1.0)
    ent = -np.sum(p * np.log(p), axis=-1) / np.log(6.0)
    conf = np.max(pred, axis=-1)
    low_conf = (conf < 0.55).astype(np.float64)
    dynamic_mass = np.sum(pred[..., 1:4], axis=-1)  # settlement/port/ruin
    return float(0.5 * np.mean(ent) + 0.3 * np.mean(low_conf) + 0.2 * np.mean(dynamic_mass))


def _observation_disagreement(workspace: Path, round_id: str, seed: int, pred: np.ndarray) -> float:
    obs_dir = workspace / "observations"
    disagreements = []
    
    for fp in sorted(obs_dir.glob(f"{round_id}_seed{seed}_*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            grid = data.get("grid")
            vp = data.get("viewport", {})
            if not grid: continue
            
            vx, vy = int(vp.get("x", -1)), int(vp.get("y", -1))
            if vx < 0 or vy < 0: continue
            
            arr = np.asarray(grid, dtype=np.int64)
            vh, vw = arr.shape
            
            # Bound check
            h, w, _ = pred.shape
            y2, x2 = min(h, vy + vh), min(w, vx + vw)
            if y2 <= vy or x2 <= vx: continue
            arr = arr[: y2 - vy, : x2 - vx]
            
            mapped = np.vectorize(grid_value_to_class_index)(arr)
            
            # Measure how far off the prediction was for this specific viewport
            for cy in range(arr.shape[0]):
                for cx in range(arr.shape[1]):
                    actual_cls = mapped[cy, cx]
                    predicted_prob = pred[vy + cy, vx + cx, actual_cls]
                    # If the actual class was given a low probability by the model, disagreement is high
                    disagreements.append(1.0 - predicted_prob)
                    
        except Exception:
            continue
            
    if not disagreements:
        return 0.0
    return float(np.mean(disagreements))

def _observation_dynamic_features(workspace: Path, round_id: str, seed: int) -> tuple[float, float]:
    obs_dir = workspace / "observations"
    dyn_ratios: list[float] = []
    for fp in sorted(obs_dir.glob(f"{round_id}_seed{seed}_*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            grid = data.get("grid")
            if not grid:
                continue
            arr = np.asarray(grid, dtype=np.int64)
            mapped = np.vectorize(grid_value_to_class_index)(arr)
            dyn = np.mean(np.isin(mapped, [1, 2, 3]).astype(np.float64))
            dyn_ratios.append(float(dyn))
        except Exception:
            continue
    if not dyn_ratios:
        return 0.0, 0.0
    return float(np.mean(dyn_ratios)), float(np.var(dyn_ratios))


def _allocate(total: int, scores: list[float], max_focus_seeds: int, min_per_seed: int) -> list[int]:
    total = max(0, int(total))
    if total == 0:
        return [0] * len(scores)
    n = len(scores)
    base_floor = min_per_seed * n
    if total <= base_floor:
        # Evenly distribute whatever is available, never exceeding total.
        out = [0] * n
        i = 0
        while sum(out) < total:
            out[i % n] += 1
            i += 1
        return out

    idx = np.argsort(scores)[::-1][: max(1, min(max_focus_seeds, len(scores)))]
    sel_scores = np.asarray([scores[i] for i in idx], dtype=np.float64)
    if np.all(sel_scores <= 1e-12):
        sel_scores = np.ones_like(sel_scores)
    weights = sel_scores / sel_scores.sum()
    extra = total - base_floor
    raw = weights * extra
    alloc = np.floor(raw).astype(int)
    rem = int(extra - alloc.sum())
    frac = raw - alloc
    for j in np.argsort(frac)[::-1][:rem]:
        alloc[j] += 1

    plan = [min_per_seed] * len(scores)
    for k, i in enumerate(idx):
        plan[i] += int(alloc[k])
    return plan


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Recommend per-seed second-pass query allocation.")
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--round-id", default="")
    parser.add_argument("--remaining-queries", type=int, default=-1, help="Override remaining query budget")
    parser.add_argument("--max-focus-seeds", type=int, default=2)
    parser.add_argument(
        "--skip-observation-features",
        action="store_true",
        help="Faster mode: do not scan observation files; use prediction uncertainty only.",
    )
    parser.add_argument("--min-per-seed", type=int, default=1, help="Never allocate below this floor when possible")
    parser.add_argument(
        "--min-per-seed-if-remaining-15",
        type=int,
        default=2,
        help="Use this higher floor when remaining queries >= 15 and activity is not very low",
    )
    parser.add_argument(
        "--low-activity-threshold",
        type=float,
        default=0.22,
        help="If mean dynamic/activity score is below this, use lower floor",
    )
    parser.add_argument("--workspace", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "reports" / "query_allocation_recommendation.json",
    )
    args = parser.parse_args()
    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")

    need_api = (not args.round_id) or (args.remaining_queries < 0)
    client = None
    if need_api:
        if not token:
            raise RuntimeError(
                "Missing bearer token. Either set AINM_BEARER_TOKEN or pass both "
                "--round-id and --remaining-queries to run offline."
            )
        client = AstarApiClient(bearer_token=token, base_url=base_url)

    if args.round_id:
        round_id = args.round_id
    else:
        # mypy-safe because need_api implies client is initialized
        round_id = _pick_active_round(client.list_rounds())["id"]  # type: ignore[union-attr]

    if args.remaining_queries >= 0:
        remaining = int(args.remaining_queries)
    else:
        budget = client.get_budget()  # type: ignore[union-attr]
        remaining = max(0, int(budget.get("queries_max", 0)) - int(budget.get("queries_used", 0)))

    per_seed_scores = []
    details: dict[str, dict[str, float]] = {}
    missing = []
    for seed in range(NUM_SEEDS):
        pred_path = args.workspace / "predictions" / f"{round_id}_seed{seed}.json"
        if not pred_path.is_file():
            per_seed_scores.append(0.0)
            missing.append(seed)
            continue
        pred = _load_prediction(pred_path)
        pred_u = _seed_uncertainty(pred)
        disagreement = _observation_disagreement(args.workspace, round_id, seed, pred)
        
        if args.skip_observation_features:
            dyn_mean, dyn_var = 0.0, 0.0
        else:
            dyn_mean, dyn_var = _observation_dynamic_features(args.workspace, round_id, seed)
            
        # Blend prediction uncertainty with observed viewport dynamics and the NEW Disagreement Factor
        combined = 0.20 * pred_u + 0.20 * disagreement + 0.45 * dyn_mean + 0.15 * min(1.0, dyn_var * 10.0)
        per_seed_scores.append(combined)
        details[str(seed)] = {
            "prediction_uncertainty": float(pred_u),
            "model_observation_disagreement": float(disagreement),
            "observed_dynamic_mean": float(dyn_mean),
            "observed_dynamic_var": float(dyn_var),
            "combined_score": float(combined),
        }

    mean_activity = float(np.mean(per_seed_scores)) if per_seed_scores else 0.0
    min_floor = max(0, int(args.min_per_seed))
    if remaining >= 15 and mean_activity >= args.low_activity_threshold:
        min_floor = max(min_floor, int(args.min_per_seed_if_remaining_15))

    plan = _allocate(
        remaining,
        per_seed_scores,
        max_focus_seeds=args.max_focus_seeds,
        min_per_seed=min_floor,
    )
    plan_str = ",".join(str(x) for x in plan)
    payload = {
        "round_id": round_id,
        "remaining_queries": remaining,
        "mean_activity_score": mean_activity,
        "seed_details": details,
        "uncertainty_scores": {str(i): float(per_seed_scores[i]) for i in range(NUM_SEEDS)},
        "min_per_seed_used": min_floor,
        "missing_prediction_files": missing,
        "recommended_plan": plan,
        "recommended_seed_query_plan_arg": plan_str,
        "example_command": f"python scripts/run_active_round.py --seed-query-plan {plan_str} --save-visuals",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

