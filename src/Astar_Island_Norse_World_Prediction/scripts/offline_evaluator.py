#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_baseline import build_prediction_tensor
from src.predictor_spatial import SpatialConfig, load_spatial_priors
from src.scoring import score_prediction, weighted_kl
from src.types import NUM_CLASSES


@dataclass
class RoundSeedSample:
    round_id: str
    round_number: int
    seed_index: int
    initial_grid: np.ndarray  # HxW ints
    ground_truth: np.ndarray  # HxWx6 probs


def _load_samples(rounds_dir: Path) -> list[RoundSeedSample]:
    out: list[RoundSeedSample] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        gt = np.asarray(data["ground_truth"], dtype=np.float64)
        if gt.ndim != 3 or gt.shape[-1] != NUM_CLASSES:
            continue
        out.append(
            RoundSeedSample(
                round_id=str(data["round_id"]),
                round_number=int(data.get("round_number", 0)),
                seed_index=int(data["seed_index"]),
                initial_grid=np.asarray(data["initial_grid"], dtype=np.int64),
                ground_truth=gt,
            )
        )
    return out


def _viewport_grid(width: int, height: int, viewport_w: int, viewport_h: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(0, max(1, height - viewport_h + 1)) for x in range(0, max(1, width - viewport_w + 1))]


def _class_to_grid_value(class_idx: np.ndarray, initial_grid: np.ndarray) -> np.ndarray:
    # Class 0 maps to ocean (10) on known ocean cells, otherwise plains (11).
    out = np.full(class_idx.shape, 11, dtype=np.int64)
    ocean_mask = initial_grid == 10
    out[ocean_mask] = 10
    out[class_idx == 1] = 1
    out[class_idx == 2] = 2
    out[class_idx == 3] = 3
    out[class_idx == 4] = 4
    out[class_idx == 5] = 5
    return out


def _sample_realized_grid(ground_truth: np.ndarray, initial_grid: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    h, w, c = ground_truth.shape
    flat = ground_truth.reshape((-1, c))
    probs = np.maximum(flat, 0.0)
    row_sums = probs.sum(axis=1, keepdims=True)
    bad = row_sums <= 0
    if np.any(bad):
        probs[bad[:, 0]] = 1.0 / c
        row_sums = probs.sum(axis=1, keepdims=True)
    probs = probs / row_sums
    cdf = np.cumsum(probs, axis=1)
    u = rng.random((flat.shape[0], 1))
    sampled = np.sum(u > cdf, axis=1).astype(np.int64)
    sampled = np.clip(sampled, 0, c - 1)
    class_grid = sampled.reshape((h, w))
    return _class_to_grid_value(class_grid, initial_grid=initial_grid)


def _entropy_map(pred: np.ndarray) -> np.ndarray:
    eps = 1e-12
    p = np.clip(pred, eps, 1.0)
    return -np.sum(p * np.log(p), axis=-1)


def _integral_image(arr: np.ndarray) -> np.ndarray:
    ii = np.zeros((arr.shape[0] + 1, arr.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = np.cumsum(np.cumsum(arr, axis=0), axis=1)
    return ii


def _rect_sums_from_integral(
    ii: np.ndarray,
    xs: np.ndarray,
    ys: np.ndarray,
    w: int,
    h: int,
) -> np.ndarray:
    x2 = xs + w
    y2 = ys + h
    return ii[y2, x2] - ii[ys, x2] - ii[y2, xs] + ii[ys, xs]


def _pick_next_viewport(
    policy: str,
    candidates: list[tuple[int, int]],
    used: set[tuple[int, int]],
    pred: np.ndarray,
    viewport_w: int,
    viewport_h: int,
    rng: np.random.Generator,
    discount: np.ndarray,
    step_index: int,
    grid_warmup_queries: int,
    entropy_mode: str,
    entropy_temp: float,
    historical_overlap_penalty: float,
    history_counts: np.ndarray,
) -> tuple[int, int] | None:
    available = [c for c in candidates if c not in used]
    if not available:
        return None

    use_grid = policy == "grid" or (policy == "grid_then_entropy" and step_index < grid_warmup_queries)
    if use_grid:
        return available[0]
    if policy == "random":
        idx = int(rng.integers(0, len(available)))
        return available[idx]
    if policy in {"entropy", "grid_then_entropy"}:
        ent = _entropy_map(pred)
        if entropy_mode == "unobserved_only":
            ent = ent * (history_counts <= 0).astype(np.float64)
        if abs(entropy_temp - 1.0) > 1e-9:
            ent = np.power(np.clip(ent, 0.0, None), max(1e-6, entropy_temp))
        utility = ent * discount
        if historical_overlap_penalty > 0:
            utility = utility - historical_overlap_penalty * history_counts
        ii = _integral_image(utility)
        arr = np.asarray(available, dtype=np.int64)
        xs = arr[:, 0]
        ys = arr[:, 1]
        scores = _rect_sums_from_integral(ii, xs=xs, ys=ys, w=viewport_w, h=viewport_h)
        j = int(np.argmax(scores))
        return int(xs[j]), int(ys[j])
    raise ValueError(f"Unknown policy: {policy}")


def _build_observation(realized_grid: np.ndarray, x: int, y: int, w: int, h: int, queries_used: int = 1) -> dict[str, Any]:
    vp = realized_grid[y : y + h, x : x + w]
    settlements: list[dict[str, Any]] = []
    ys, xs = np.where((vp == 1) | (vp == 2))
    for ly, lx in zip(ys, xs, strict=False):
        gx = int(x + lx)
        gy = int(y + ly)
        has_port = int(vp[ly, lx]) == 2
        settlements.append(
            {
                "x": gx,
                "y": gy,
                "population": 2.0 if has_port else 1.8,
                "food": 0.55,
                "wealth": 0.35 if has_port else 0.22,
                "defense": 0.7,
                "has_port": has_port,
                "alive": True,
            }
        )
    return {
        "grid": vp.tolist(),
        "settlements": settlements,
        "viewport": {"x": x, "y": y, "w": w, "h": h},
        "width": int(realized_grid.shape[1]),
        "height": int(realized_grid.shape[0]),
        "queries_used": queries_used,
        "queries_max": 50,
    }


def _simulate_sample(
    sample: RoundSeedSample,
    policy: str,
    query_budget: int,
    viewport_w: int,
    viewport_h: int,
    overlap_discount: float,
    floor: float,
    seed: int,
    predictor_mode: str,
    spatial_config: SpatialConfig | None,
    priors_file: Path | None,
    grid_warmup_queries: int,
    entropy_mode: str,
    entropy_temp: float,
    historical_overlap_penalty: float,
    hybrid_unet_weight: float,
    unet_model_path: Path | None,
) -> dict[str, Any]:
    h, w = sample.initial_grid.shape
    candidates = _viewport_grid(width=w, height=h, viewport_w=viewport_w, viewport_h=viewport_h)
    used: set[tuple[int, int]] = set()
    observations: list[dict[str, Any]] = []
    discount = np.ones((h, w), dtype=np.float64)
    history_counts = np.zeros((h, w), dtype=np.float64)
    rng = np.random.default_rng(seed)
    t_sampling_start = time.perf_counter()
    realized_grid = _sample_realized_grid(sample.ground_truth, sample.initial_grid, rng=rng)
    sampling_ms = (time.perf_counter() - t_sampling_start) * 1000.0
    predict_ms = 0.0
    query_score_ms = 0.0

    steps: list[dict[str, float]] = []
    max_steps = min(query_budget, len(candidates))
    for step in range(max_steps + 1):
        t_pred_start = time.perf_counter()
        pred = build_prediction_tensor(
            sample.initial_grid.tolist(),
            observations,
            floor=floor,
            priors_file=priors_file,
            predictor_mode=predictor_mode,
            shared_observations=observations,
            spatial_config=spatial_config,
            hybrid_unet_weight=hybrid_unet_weight,
            unet_model_path=unet_model_path,
        )
        predict_ms += (time.perf_counter() - t_pred_start) * 1000.0
        score = float(score_prediction(sample.ground_truth, pred))
        wkl = float(weighted_kl(sample.ground_truth, pred))
        steps.append(
            {
                "step": float(step),
                "queries_used": float(len(observations)),
                "score": score,
                "weighted_kl": wkl,
            }
        )

        if step == max_steps:
            break
        t_pick_start = time.perf_counter()
        nxt = _pick_next_viewport(
            policy=policy,
            candidates=candidates,
            used=used,
            pred=pred,
            viewport_w=viewport_w,
            viewport_h=viewport_h,
            rng=rng,
            discount=discount,
            step_index=step,
            grid_warmup_queries=grid_warmup_queries,
            entropy_mode=entropy_mode,
            entropy_temp=entropy_temp,
            historical_overlap_penalty=historical_overlap_penalty,
            history_counts=history_counts,
        )
        query_score_ms += (time.perf_counter() - t_pick_start) * 1000.0
        if nxt is None:
            break
        x, y = nxt
        observations.append(_build_observation(realized_grid, x=x, y=y, w=viewport_w, h=viewport_h, queries_used=len(observations) + 1))
        used.add((x, y))
        history_counts[y : y + viewport_h, x : x + viewport_w] += 1.0
        # Critical de-overlap tweak: discount entropy utility in selected viewport immediately.
        discount[y : y + viewport_h, x : x + viewport_w] *= overlap_discount

    return {
        "round_id": sample.round_id,
        "round_number": sample.round_number,
        "seed_index": sample.seed_index,
        "policy": policy,
        "query_budget": query_budget,
        "viewport_w": viewport_w,
        "viewport_h": viewport_h,
        "overlap_discount": overlap_discount,
        "floor": floor,
        "predictor_mode": predictor_mode,
        "initial_score": steps[0]["score"] if steps else 0.0,
        "final_score": steps[-1]["score"] if steps else 0.0,
        "initial_weighted_kl": steps[0]["weighted_kl"] if steps else 0.0,
        "final_weighted_kl": steps[-1]["weighted_kl"] if steps else 0.0,
        "score_delta": (steps[-1]["score"] - steps[0]["score"]) if steps else 0.0,
        "timing_ms": {
            "sampling": float(sampling_ms),
            "prediction_total": float(predict_ms),
            "viewport_selection_total": float(query_score_ms),
        },
        "steps": steps,
    }


def _aggregate_policy_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_policy: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        by_policy.setdefault(str(row["policy"]), []).append(row)

    out: dict[str, Any] = {}
    for policy, rows in by_policy.items():
        final_scores = [float(r["final_score"]) for r in rows]
        deltas = [float(r["score_delta"]) for r in rows]
        final_wkl = [float(r["final_weighted_kl"]) for r in rows]
        out[policy] = {
            "n": len(rows),
            "mean_final_score": float(np.mean(final_scores)) if final_scores else 0.0,
            "std_final_score": float(np.std(final_scores)) if final_scores else 0.0,
            "mean_score_delta": float(np.mean(deltas)) if deltas else 0.0,
            "mean_final_weighted_kl": float(np.mean(final_wkl)) if final_wkl else 0.0,
        }
    return out


def _build_spatial_config(
    floor: float,
    tau: float,
    smoothing_weight: float,
    smoothing_passes: int,
    disable_local_evidence: bool,
    disable_neighbor_smoothing: bool,
    disable_settlement_influence: bool,
    disable_dynamic_alpha: bool,
    local_count_threshold: int,
    local_blend_max: float,
    alpha_count_weight: float,
    alpha_entropy_weight: float,
    alpha_distance_weight: float,
    influence_settlement_weight: float,
    influence_port_weight: float,
    influence_ruin_weight: float,
    influence_forest_weight: float,
    distance_backend: str,
) -> SpatialConfig:
    cfg = SpatialConfig(
        floor=floor,
        influence_tau=tau,
        smoothing_weight=smoothing_weight,
        smoothing_passes=smoothing_passes,
        local_count_threshold=max(1, int(local_count_threshold)),
        local_blend_max=float(np.clip(local_blend_max, 0.0, 1.0)),
        alpha_count_weight=float(max(0.0, alpha_count_weight)),
        alpha_entropy_weight=float(max(0.0, alpha_entropy_weight)),
        alpha_distance_weight=float(max(0.0, alpha_distance_weight)),
        influence_settlement_weight=float(max(0.0, influence_settlement_weight)),
        influence_port_weight=float(max(0.0, influence_port_weight)),
        influence_ruin_weight=float(max(0.0, influence_ruin_weight)),
        influence_forest_weight=float(max(0.0, influence_forest_weight)),
        distance_backend=distance_backend,
    )
    if disable_local_evidence:
        cfg.local_blend_max = 0.0
    if disable_neighbor_smoothing:
        cfg.smoothing_weight = 0.0
        cfg.smoothing_passes = 0
    if disable_settlement_influence:
        cfg.influence_settlement_weight = 0.0
        cfg.influence_port_weight = 0.0
        cfg.influence_ruin_weight = 0.0
        cfg.influence_forest_weight = 0.0
    if disable_dynamic_alpha:
        cfg.alpha_count_weight = 0.0
        cfg.alpha_entropy_weight = 0.0
        cfg.alpha_distance_weight = 0.0
        cfg.alpha_min = cfg.alpha_base
    return cfg


def run_evaluation(
    rounds_dir: Path,
    query_budget: int,
    viewport_w: int,
    viewport_h: int,
    policies: list[str],
    overlap_discount: float,
    floor: float,
    seed: int,
    limit_samples: int = 0,
    predictor_mode: str = "baseline",
    tau: float = 4.5,
    smoothing_weight: float = 0.12,
    smoothing_passes: int = 1,
    disable_local_evidence: bool = False,
    disable_neighbor_smoothing: bool = False,
    disable_settlement_influence: bool = False,
    disable_dynamic_alpha: bool = False,
    priors_file: Path | None = None,
    grid_warmup_queries: int = 2,
    entropy_mode: str = "plain",
    entropy_temp: float = 1.0,
    historical_overlap_penalty: float = 0.0,
    local_count_threshold: int = 5,
    local_blend_max: float = 0.22,
    alpha_count_weight: float = 0.22,
    alpha_entropy_weight: float = 0.10,
    alpha_distance_weight: float = 0.12,
    influence_settlement_weight: float = 0.55,
    influence_port_weight: float = 0.45,
    influence_ruin_weight: float = 0.20,
    influence_forest_weight: float = 0.18,
    distance_backend: str = "python",
    spatial_priors_file: Path | None = None,
    hybrid_unet_weight: float = 0.30,
    unet_model_path: Path | None = None,
) -> dict[str, Any]:
    valid = {"grid", "random", "entropy", "grid_then_entropy"}
    unknown = [p for p in policies if p not in valid]
    if unknown:
        raise RuntimeError(f"Unknown policies: {unknown}; valid={sorted(valid)}")
    if predictor_mode not in {"baseline", "spatial", "spatial_unet", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "time_socio_unet", "gnn"}:
        raise RuntimeError("predictor_mode must be valid")
    if distance_backend not in {"python", "scipy"}:
        raise RuntimeError("distance_backend must be one of {python,scipy}")
    if entropy_mode not in {"plain", "unobserved_only"}:
        raise RuntimeError("entropy_mode must be one of {plain,unobserved_only}")
    if not policies:
        raise RuntimeError("No policies selected")

    overlap_discount = float(np.clip(overlap_discount, 0.0, 1.0))
    floor = float(max(1e-12, floor))
    if priors_file is None:
        default_priors = ROOT / "data" / "reports" / "tuned_priors.json"
        priors_file = default_priors if default_priors.is_file() else None
    samples = _load_samples(rounds_dir)
    if not samples:
        raise RuntimeError(f"No *_analysis.json samples found in {rounds_dir}")
    if limit_samples > 0:
        samples = samples[:limit_samples]
    spatial_config = _build_spatial_config(
        floor=floor,
        tau=tau,
        smoothing_weight=smoothing_weight,
        smoothing_passes=smoothing_passes,
        disable_local_evidence=disable_local_evidence,
        disable_neighbor_smoothing=disable_neighbor_smoothing,
        disable_settlement_influence=disable_settlement_influence,
        disable_dynamic_alpha=disable_dynamic_alpha,
        local_count_threshold=local_count_threshold,
        local_blend_max=local_blend_max,
        alpha_count_weight=alpha_count_weight,
        alpha_entropy_weight=alpha_entropy_weight,
        alpha_distance_weight=alpha_distance_weight,
        influence_settlement_weight=influence_settlement_weight,
        influence_port_weight=influence_port_weight,
        influence_ruin_weight=influence_ruin_weight,
        influence_forest_weight=influence_forest_weight,
        distance_backend=distance_backend,
    ) if predictor_mode in {"spatial", "spatial_unet"} else None
    if spatial_config is not None:
        priors = load_spatial_priors(spatial_priors_file if (spatial_priors_file and spatial_priors_file.is_file()) else None)
        for k, v in priors.items():
            setattr(spatial_config, k, v)

    all_results: list[dict[str, Any]] = []
    for i, sample in enumerate(samples):
        for policy in policies:
            row = _simulate_sample(
                sample=sample,
                policy=policy,
                query_budget=max(0, int(query_budget)),
                viewport_w=max(1, int(viewport_w)),
                viewport_h=max(1, int(viewport_h)),
                overlap_discount=overlap_discount,
                floor=floor,
                seed=seed + i * 1009 + sum(ord(ch) for ch in policy),
                predictor_mode=predictor_mode,
                spatial_config=spatial_config,
                priors_file=priors_file,
                grid_warmup_queries=max(0, int(grid_warmup_queries)),
                entropy_mode=entropy_mode,
                entropy_temp=float(entropy_temp),
                historical_overlap_penalty=float(max(0.0, historical_overlap_penalty)),
                hybrid_unet_weight=float(np.clip(hybrid_unet_weight, 0.0, 1.0)),
                unet_model_path=unet_model_path if (unet_model_path and unet_model_path.is_file()) else None,
            )
            all_results.append(row)

    summary = _aggregate_policy_results(all_results)
    payload = {
        "config": {
            "rounds_dir": str(rounds_dir),
            "sample_count": len(samples),
            "query_budget": int(query_budget),
            "viewport_w": int(viewport_w),
            "viewport_h": int(viewport_h),
            "policies": policies,
            "overlap_discount": overlap_discount,
            "floor": floor,
            "seed": int(seed),
            "predictor_mode": predictor_mode,
            "tau": tau,
            "smoothing_weight": smoothing_weight,
            "smoothing_passes": int(smoothing_passes),
            "disable_local_evidence": bool(disable_local_evidence),
            "disable_neighbor_smoothing": bool(disable_neighbor_smoothing),
            "disable_settlement_influence": bool(disable_settlement_influence),
            "disable_dynamic_alpha": bool(disable_dynamic_alpha),
            "priors_file": str(priors_file) if priors_file is not None else None,
            "grid_warmup_queries": int(max(0, int(grid_warmup_queries))),
            "entropy_mode": entropy_mode,
            "entropy_temp": float(entropy_temp),
            "historical_overlap_penalty": float(max(0.0, historical_overlap_penalty)),
            "local_count_threshold": int(local_count_threshold),
            "local_blend_max": float(local_blend_max),
            "alpha_count_weight": float(alpha_count_weight),
            "alpha_entropy_weight": float(alpha_entropy_weight),
            "alpha_distance_weight": float(alpha_distance_weight),
            "influence_settlement_weight": float(influence_settlement_weight),
            "influence_port_weight": float(influence_port_weight),
            "influence_ruin_weight": float(influence_ruin_weight),
            "influence_forest_weight": float(influence_forest_weight),
            "distance_backend": distance_backend,
            "spatial_priors_file": str(spatial_priors_file) if (spatial_priors_file and spatial_priors_file.is_file()) else None,
            "hybrid_unet_weight": float(np.clip(hybrid_unet_weight, 0.0, 1.0)),
            "unet_model_path": str(unet_model_path) if (unet_model_path and unet_model_path.is_file()) else None,
        },
        "summary_by_policy": summary,
        "results": all_results,
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline budgeted replay evaluator for Astar Island.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "offline_evaluator_report.json")
    parser.add_argument("--query-budget", type=int, default=8)
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument(
        "--policies",
        default="grid,random,entropy",
        help="Comma-separated policies from {grid,random,entropy,grid_then_entropy}",
    )
    parser.add_argument(
        "--overlap-discount",
        type=float,
        default=0.0,
        help="Entropy policy discount multiplier applied to selected viewport after each pick",
    )
    parser.add_argument(
        "--floor",
        type=float,
        default=0.01,
        help="Minimum per-class probability floor passed into prediction tensor",
    )
    parser.add_argument(
        "--predictor-mode",
        choices=["baseline", "spatial", "spatial_unet", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "time_socio_unet", "gnn"],
        default="baseline",
    )
    parser.add_argument(
        "--priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "tuned_priors.json",
        help="Optional tuned priors JSON; used by both baseline and spatial paths",
    )
    parser.add_argument("--tau", type=float, default=4.5, help="Spatial influence decay")
    parser.add_argument("--smoothing-weight", type=float, default=0.12)
    parser.add_argument("--smoothing-passes", type=int, default=1)
    parser.add_argument("--disable-local-evidence", action="store_true")
    parser.add_argument("--disable-neighbor-smoothing", action="store_true")
    parser.add_argument("--disable-settlement-influence", action="store_true")
    parser.add_argument("--disable-dynamic-alpha", action="store_true")
    parser.add_argument("--local-count-threshold", type=int, default=5)
    parser.add_argument("--local-blend-max", type=float, default=0.22)
    parser.add_argument("--alpha-count-weight", type=float, default=0.22)
    parser.add_argument("--alpha-entropy-weight", type=float, default=0.10)
    parser.add_argument("--alpha-distance-weight", type=float, default=0.12)
    parser.add_argument("--influence-settlement-weight", type=float, default=0.55)
    parser.add_argument("--influence-port-weight", type=float, default=0.45)
    parser.add_argument("--influence-ruin-weight", type=float, default=0.20)
    parser.add_argument("--influence-forest-weight", type=float, default=0.18)
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument(
        "--spatial-priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json",
        help="Optional replay-calibrated spatial priors",
    )
    parser.add_argument(
        "--hybrid-unet-weight",
        type=float,
        default=0.30,
        help="Blend weight for UNet branch when predictor-mode=spatial_unet",
    )
    parser.add_argument(
        "--unet-model-path",
        type=Path,
        default=ROOT / "data" / "reports" / "unet_predictor.pth",
        help="Optional UNet model file for unet/spatial_unet modes",
    )
    parser.add_argument(
        "--grid-warmup-queries",
        type=int,
        default=2,
        help="For grid_then_entropy policy: number of initial queries taken by grid order",
    )
    parser.add_argument(
        "--entropy-mode",
        choices=["plain", "unobserved_only"],
        default="plain",
        help="Entropy utility variant used by entropy-based policies",
    )
    parser.add_argument(
        "--entropy-temp",
        type=float,
        default=1.0,
        help="Exponent applied to entropy utility before viewport scoring",
    )
    parser.add_argument(
        "--historical-overlap-penalty",
        type=float,
        default=0.0,
        help="Penalty weight for repeatedly querying historically covered cells",
    )
    parser.add_argument("--seed", type=int, default=1337)
    parser.add_argument("--limit-samples", type=int, default=0, help="0 means all cached samples")
    args = parser.parse_args()

    policies = [p.strip() for p in args.policies.split(",") if p.strip()]
    payload = run_evaluation(
        rounds_dir=args.rounds_dir,
        query_budget=args.query_budget,
        viewport_w=args.viewport_w,
        viewport_h=args.viewport_h,
        policies=policies,
        overlap_discount=args.overlap_discount,
        floor=args.floor,
        seed=args.seed,
        limit_samples=args.limit_samples,
        predictor_mode=args.predictor_mode,
        tau=args.tau,
        smoothing_weight=args.smoothing_weight,
        smoothing_passes=args.smoothing_passes,
        disable_local_evidence=args.disable_local_evidence,
        disable_neighbor_smoothing=args.disable_neighbor_smoothing,
        disable_settlement_influence=args.disable_settlement_influence,
        disable_dynamic_alpha=args.disable_dynamic_alpha,
        priors_file=args.priors_file if args.priors_file.is_file() else None,
        grid_warmup_queries=args.grid_warmup_queries,
        entropy_mode=args.entropy_mode,
        entropy_temp=args.entropy_temp,
        historical_overlap_penalty=args.historical_overlap_penalty,
        local_count_threshold=args.local_count_threshold,
        local_blend_max=args.local_blend_max,
        alpha_count_weight=args.alpha_count_weight,
        alpha_entropy_weight=args.alpha_entropy_weight,
        alpha_distance_weight=args.alpha_distance_weight,
        influence_settlement_weight=args.influence_settlement_weight,
        influence_port_weight=args.influence_port_weight,
        influence_ruin_weight=args.influence_ruin_weight,
        influence_forest_weight=args.influence_forest_weight,
        distance_backend=args.distance_backend,
        spatial_priors_file=args.spatial_priors_file if args.spatial_priors_file.is_file() else None,
        hybrid_unet_weight=args.hybrid_unet_weight,
        unet_model_path=args.unet_model_path if args.unet_model_path.is_file() else None,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary_by_policy"], indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

