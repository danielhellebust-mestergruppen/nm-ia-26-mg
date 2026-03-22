#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file
from src.offline_harness import save_json
from src.predictor_baseline import build_prediction_tensor
from src.predictor_spatial import SpatialConfig, load_spatial_dynamics_coeffs, load_spatial_priors
from src.scoring import apply_probability_floor, validate_prediction_tensor
from src.types import NUM_SEEDS, ViewportRequest
from src.visualize import save_prediction_visuals


def _pick_active_round(rounds: list[dict]) -> dict:
    active = [r for r in rounds if r.get("status") == "active"]
    if not active:
        raise RuntimeError("No active round found")
    return sorted(active, key=lambda x: x.get("round_number", 0))[-1]


def _viewport_grid(width: int, height: int, viewport_w: int, viewport_h: int) -> list[tuple[int, int]]:
    return [(x, y) for y in range(0, height - viewport_h + 1) for x in range(0, width - viewport_w + 1)]


def _entropy_map(pred: np.ndarray) -> np.ndarray:
    eps = 1e-12
    p = np.clip(pred, eps, 1.0)
    return -np.sum(p * np.log(p), axis=-1)


def _pick_next_viewport(
    policy: str,
    candidates: list[tuple[int, int]],
    used: set[tuple[int, int]],
    viewport_w: int,
    viewport_h: int,
    pred: np.ndarray | None,
    rng: np.random.Generator,
    utility_discount: np.ndarray | None,
    step_index: int,
    grid_warmup_queries: int,
    entropy_mode: str,
    entropy_temp: float,
    historical_overlap_penalty: float,
    history_counts: np.ndarray | None,
) -> tuple[int, int] | None:
    available = [c for c in candidates if c not in used]
    if not available:
        return None
    use_grid = policy == "grid" or (policy == "grid_then_entropy" and step_index < grid_warmup_queries)
    if use_grid:
        return available[0]
    if policy == "random":
        return available[int(rng.integers(0, len(available)))]
    if policy in {"entropy", "grid_then_entropy"}:
        if pred is None:
            return available[0]
        ent = _entropy_map(pred)
        if entropy_mode == "unobserved_only" and history_counts is not None:
            ent = ent * (history_counts <= 0).astype(np.float64)
        if abs(entropy_temp - 1.0) > 1e-9:
            ent = np.power(np.clip(ent, 0.0, None), max(1e-6, entropy_temp))
        discount = utility_discount if utility_discount is not None else np.ones_like(ent)
        utility = ent * discount
        if historical_overlap_penalty > 0 and history_counts is not None:
            utility = utility - historical_overlap_penalty * history_counts
        best = None
        best_score = -1e18
        for x, y in available:
            score = float(np.sum(utility[y : y + viewport_h, x : x + viewport_w]))
            if score > best_score:
                best_score = score
                best = (x, y)
        return best
    raise RuntimeError(f"Unknown query policy: {policy}")


def _per_seed_query_plan(total_budget: int, seeds: int, desired_per_seed: int) -> list[int]:
    if seeds <= 0:
        return []
    max_total = min(total_budget, seeds * max(0, desired_per_seed))
    base = max_total // seeds
    rem = max_total % seeds
    return [base + (1 if i < rem else 0) for i in range(seeds)]


def _parse_seed_query_plan(raw: str) -> list[int] | None:
    text = (raw or "").strip()
    if not text:
        return None
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) != NUM_SEEDS:
        raise RuntimeError(f"--seed-query-plan needs {NUM_SEEDS} comma-separated integers")
    vals = [max(0, int(p)) for p in parts]
    return vals


def _cap_plan_to_budget(plan: list[int], budget: int) -> list[int]:
    budget = max(0, int(budget))
    total = sum(plan)
    if total <= budget:
        return plan
    if total <= 0:
        return [0 for _ in plan]
    scaled = [p * budget / total for p in plan]
    base = [int(np.floor(x)) for x in scaled]
    rem = budget - sum(base)
    frac_order = sorted(
        range(len(plan)),
        key=lambda i: scaled[i] - base[i],
        reverse=True,
    )
    for i in frac_order[:rem]:
        base[i] += 1
    return base


def _load_blend_config(path: Path) -> tuple[float | None, np.ndarray | None]:
    if not path.is_file():
        return None, None
    data = json.loads(path.read_text(encoding="utf-8"))
    # Prefer explicit deploy block, then fall back to legacy top-level keys.
    deploy = data.get("deploy") if isinstance(data.get("deploy"), dict) else {}
    alpha = deploy.get("alpha", data.get("alpha"))
    mults = deploy.get("class_multipliers", data.get("class_multipliers"))
    alpha_val = float(alpha) if isinstance(alpha, (int, float)) else None
    mult_arr = None
    if isinstance(mults, list) and len(mults) == 6:
        mult_arr = np.asarray(mults, dtype=np.float64)
    return alpha_val, mult_arr


def _load_existing_viewports(workspace: Path, round_id: str, seed_index: int) -> set[tuple[int, int, int, int]]:
    out: set[tuple[int, int, int, int]] = set()
    obs_dir = workspace / "observations"
    for fp in sorted(obs_dir.glob(f"{round_id}_seed{seed_index}_*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            vp = data.get("viewport", {})
            x = int(vp.get("x", -1))
            y = int(vp.get("y", -1))
            w = int(vp.get("w", -1))
            h = int(vp.get("h", -1))
            if x >= 0 and y >= 0 and w > 0 and h > 0:
                out.add((x, y, w, h))
        except Exception:
            continue
    return out


def _load_shared_round_observations(workspace: Path, round_id: str) -> list[dict]:
    obs: list[dict] = []
    obs_dir = workspace / "observations"
    for fp in sorted(obs_dir.glob(f"{round_id}_seed*_*.json")):
        try:
            obs.append(json.loads(fp.read_text(encoding="utf-8")))
        except Exception:
            continue
    return obs


def _build_spatial_config_from_args(dynamics_model: Path, spatial_priors_file: Path, distance_backend: str) -> SpatialConfig:
    cfg = SpatialConfig()
    coeffs = load_spatial_dynamics_coeffs(dynamics_model if dynamics_model.is_file() else None)
    for k, v in coeffs.items():
        setattr(cfg, k, v)
    priors = load_spatial_priors(spatial_priors_file if spatial_priors_file.is_file() else None)
    for k, v in priors.items():
        setattr(cfg, k, v)
    cfg.distance_backend = distance_backend
    return cfg


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Collect observations and submit predictions.")
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--queries-per-seed", type=int, default=8)
    parser.add_argument(
        "--seed-query-plan",
        default="",
        help="Optional comma-separated per-seed query plan, e.g. '8,8,4,4,2'",
    )
    parser.add_argument("--viewport-w", type=int, default=15)
    parser.add_argument("--viewport-h", type=int, default=15)
    parser.add_argument("--floor", type=float, default=0.01)
    parser.add_argument(
        "--predictor-mode",
        choices=["baseline", "spatial", "spatial_unet", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "time_socio_unet"],
        default="baseline",
        help="Prediction engine to use",
    )
    parser.add_argument(
        "--query-policy",
        choices=["grid", "random", "entropy", "grid_then_entropy"],
        default="grid",
        help="Viewport selection policy per seed",
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
    parser.add_argument(
        "--overlap-discount",
        type=float,
        default=0.0,
        help="When using entropy policy, multiply utility in selected viewport by this value",
    )
    parser.add_argument(
        "--cross-seed-observations",
        action="store_true",
        help="Pool all cached/new observations across seeds for shared local evidence",
    )
    parser.add_argument(
        "--predict-time-guard-ms",
        type=float,
        default=0.0,
        help="If >0 and a spatial prediction call exceeds this time, fallback to baseline/grid for that seed",
    )
    parser.add_argument(
        "--dynamics-model",
        type=Path,
        default=ROOT / "data" / "reports" / "settlement_dynamics_model.json",
        help="Optional fitted settlement dynamics coefficients",
    )
    parser.add_argument(
        "--spatial-priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "spatial_priors_from_replay.json",
        help="Optional replay-calibrated spatial priors",
    )
    parser.add_argument(
        "--distance-backend",
        choices=["python", "scipy"],
        default="python",
        help="Terrain distance backend for spatial influence",
    )
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--save-visuals", action="store_true")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=ROOT / "data",
    )
    parser.add_argument(
        "--priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "tuned_priors.json",
        help="Optional tuned priors JSON produced by tune_baseline_priors.py",
    )
    parser.add_argument(
        "--blend-config",
        type=Path,
        default=ROOT / "data" / "reports" / "blend_tuning.json",
        help="Optional tuned blend config from tune_blend_weights.py",
    )
    parser.add_argument(
        "--alpha",
        type=float,
        default=None,
        help="Override blend alpha, 0..1 (if omitted may come from blend config)",
    )
    parser.add_argument(
        "--alpha-min",
        type=float,
        default=0.62,
        help="Minimum alpha when many observations are available",
    )
    parser.add_argument(
        "--alpha-obs-target",
        type=int,
        default=10,
        help="Observation count where alpha reaches alpha-min",
    )
    args = parser.parse_args()
    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    if not token:
        raise RuntimeError(
            "Missing bearer token. Set AINM_BEARER_TOKEN in shell or astar_island/.env "
            "or pass --token."
        )

    cfg_alpha, cfg_mult = _load_blend_config(args.blend_config)
    alpha = float(np.clip(args.alpha, 0.0, 1.0)) if args.alpha is not None else (
        float(np.clip(cfg_alpha, 0.0, 1.0)) if cfg_alpha is not None else 0.75
    )
    class_multipliers = cfg_mult

    client = AstarApiClient(bearer_token=token, base_url=base_url)
    active_round = _pick_active_round(client.list_rounds())
    round_id = active_round["id"]
    round_payload = client.get_round(round_id)
    width = int(round_payload["map_width"])
    height = int(round_payload["map_height"])
    budget = client.get_budget()
    remaining_budget = max(0, int(budget.get("queries_max", 0)) - int(budget.get("queries_used", 0)))

    viewport_candidates = _viewport_grid(width, height, args.viewport_w, args.viewport_h)
    raw_plan = _parse_seed_query_plan(args.seed_query_plan)
    if raw_plan is not None:
        query_plan = _cap_plan_to_budget(raw_plan, remaining_budget)
    else:
        query_plan = _per_seed_query_plan(
            total_budget=remaining_budget,
            seeds=NUM_SEEDS,
            desired_per_seed=args.queries_per_seed,
        )
    print(
        f"round={round_id} remaining_budget={remaining_budget} "
        f"desired_per_seed={args.queries_per_seed} query_plan={query_plan} alpha={alpha} "
        f"predictor_mode={args.predictor_mode} query_policy={args.query_policy}"
    )

    predictions: dict[int, np.ndarray] = {}
    seed_runtime_guard: dict[int, dict[str, object]] = {}
    budget_exhausted = remaining_budget <= 0
    rng = np.random.default_rng(1337)
    shared_observations = _load_shared_round_observations(args.workspace, round_id) if args.cross_seed_observations else []
    spatial_config = (
        _build_spatial_config_from_args(args.dynamics_model, args.spatial_priors_file, args.distance_backend)
        if args.predictor_mode == "spatial"
        else None
    )
    for seed_index in range(NUM_SEEDS):
        seed_predictor_mode = args.predictor_mode
        seed_query_policy = args.query_policy
        fallback_reason: str | None = None
        initial_grid = round_payload["initial_states"][seed_index]["grid"]
        observations: list[dict] = []
        existing_vps = _load_existing_viewports(args.workspace, round_id, seed_index)
        fresh_candidates = [
            (x, y)
            for (x, y) in viewport_candidates
            if (x, y, args.viewport_w, args.viewport_h) not in existing_vps
        ]
        candidate_pool = fresh_candidates if fresh_candidates else viewport_candidates
        planned_queries = min(query_plan[seed_index], len(viewport_candidates))
        used_positions: set[tuple[int, int]] = set((x, y) for (x, y, _, _) in existing_vps)
        utility_discount = np.ones((height, width), dtype=np.float64)
        history_counts = np.zeros((height, width), dtype=np.float64)
        pred_for_policy: np.ndarray | None = None
        for i in range(planned_queries):
            if budget_exhausted:
                break
            nxt = _pick_next_viewport(
                policy=seed_query_policy,
                candidates=candidate_pool,
                used=used_positions,
                viewport_w=args.viewport_w,
                viewport_h=args.viewport_h,
                pred=pred_for_policy,
                rng=rng,
                utility_discount=utility_discount,
                step_index=i,
                grid_warmup_queries=max(0, int(args.grid_warmup_queries)),
                entropy_mode=args.entropy_mode,
                entropy_temp=float(args.entropy_temp),
                historical_overlap_penalty=float(max(0.0, args.historical_overlap_penalty)),
                history_counts=history_counts,
            )
            if nxt is None:
                break
            vx, vy = nxt
            req = ViewportRequest(
                round_id=round_id,
                seed_index=seed_index,
                viewport_x=vx,
                viewport_y=vy,
                viewport_w=args.viewport_w,
                viewport_h=args.viewport_h,
            )
            try:
                obs = client.simulate(req.as_dict())
            except RuntimeError as exc:
                msg = str(exc).lower()
                if "429" in msg and "budget" in msg:
                    budget_exhausted = True
                    print("simulate budget exhausted; continuing with cached/partial observations")
                    break
                if "429" in msg:
                    print("simulate rate-limited after retries; moving on with partial observations")
                    break
                raise
            observations.append(obs)
            if args.cross_seed_observations:
                shared_observations.append(obs)
            used_positions.add((vx, vy))
            history_counts[vy : vy + args.viewport_h, vx : vx + args.viewport_w] += 1.0
            if seed_query_policy in {"entropy", "grid_then_entropy"}:
                utility_discount[vy : vy + args.viewport_h, vx : vx + args.viewport_w] *= float(
                    np.clip(args.overlap_discount, 0.0, 1.0)
                )
            file_path = (
                args.workspace
                / "observations"
                / f"{round_id}_seed{seed_index}_{int(time.time()*1000)}_{i}.json"
            )
            save_json(file_path, obs)
            if seed_query_policy in {"entropy", "grid_then_entropy"} and i + 1 < planned_queries:
                t0 = time.perf_counter()
                pred_for_policy = build_prediction_tensor(
                    initial_grid,
                    observations,
                    floor=args.floor,
                    priors_file=args.priors_file if args.priors_file.is_file() else None,
                    alpha=alpha,
                    alpha_min=args.alpha_min,
                    alpha_obs_target=args.alpha_obs_target,
                    class_multipliers=class_multipliers,
                    predictor_mode=seed_predictor_mode,
                    shared_observations=shared_observations if args.cross_seed_observations else None,
                    spatial_config=spatial_config,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if (
                    args.predict_time_guard_ms > 0
                    and seed_predictor_mode == "spatial"
                    and elapsed_ms > args.predict_time_guard_ms
                ):
                    seed_predictor_mode = "baseline"
                    seed_query_policy = "grid"
                    fallback_reason = (
                        f"predict_step_ms={elapsed_ms:.2f} exceeded guard_ms={args.predict_time_guard_ms:.2f}"
                    )
                    pred_for_policy = None
                    print(f"seed {seed_index}: runtime guard fallback activated ({fallback_reason})")

        t0 = time.perf_counter()
        pred = build_prediction_tensor(
            initial_grid,
            observations,
            floor=args.floor,
            priors_file=args.priors_file if args.priors_file.is_file() else None,
            alpha=alpha,
            alpha_min=args.alpha_min,
            alpha_obs_target=args.alpha_obs_target,
            class_multipliers=class_multipliers,
            predictor_mode=seed_predictor_mode,
            shared_observations=shared_observations if args.cross_seed_observations else None,
            spatial_config=spatial_config,
        )
        final_pred_ms = (time.perf_counter() - t0) * 1000.0
        if (
            args.predict_time_guard_ms > 0
            and seed_predictor_mode == "spatial"
            and final_pred_ms > args.predict_time_guard_ms
        ):
            seed_predictor_mode = "baseline"
            seed_query_policy = "grid"
            fallback_reason = (
                f"final_predict_ms={final_pred_ms:.2f} exceeded guard_ms={args.predict_time_guard_ms:.2f}"
            )
            pred = build_prediction_tensor(
                initial_grid,
                observations,
                floor=args.floor,
                priors_file=args.priors_file if args.priors_file.is_file() else None,
                alpha=alpha,
                alpha_min=args.alpha_min,
                alpha_obs_target=args.alpha_obs_target,
                class_multipliers=class_multipliers,
                predictor_mode="baseline",
                shared_observations=shared_observations if args.cross_seed_observations else None,
                spatial_config=spatial_config,
            )
            print(f"seed {seed_index}: runtime guard fallback activated ({fallback_reason})")
        pred = apply_probability_floor(pred, floor=args.floor)
        ok, msg = validate_prediction_tensor(pred, height=height, width=width)
        if not ok:
            raise RuntimeError(f"Prediction validation failed for seed {seed_index}: {msg}")

        predictions[seed_index] = pred
        seed_runtime_guard[seed_index] = {
            "effective_predictor_mode": seed_predictor_mode,
            "effective_query_policy": seed_query_policy,
            "final_prediction_ms": final_pred_ms,
            "fallback_reason": fallback_reason,
        }
        pred_file = args.workspace / "predictions" / f"{round_id}_seed{seed_index}.json"
        save_json(pred_file, pred.tolist())
        if args.save_visuals:
            save_prediction_visuals(pred, args.workspace / "reports", f"{round_id}_seed{seed_index}")

        if args.submit:
            payload = {"round_id": round_id, "seed_index": seed_index, "prediction": pred.tolist()}
            resp = client.submit(payload)
            print(f"submitted seed {seed_index}: {json.dumps(resp)}")

    summary = {
        "round_id": round_id,
        "submitted": bool(args.submit),
        "seeds_prepared": sorted(predictions.keys()),
        "remaining_budget_at_start": remaining_budget,
        "query_plan": query_plan,
        "budget_exhausted_during_run": budget_exhausted,
        "alpha": alpha,
        "alpha_min": args.alpha_min,
        "alpha_obs_target": args.alpha_obs_target,
        "predictor_mode": args.predictor_mode,
        "query_policy": args.query_policy,
        "grid_warmup_queries": int(max(0, int(args.grid_warmup_queries))),
        "entropy_mode": args.entropy_mode,
        "entropy_temp": float(args.entropy_temp),
        "historical_overlap_penalty": float(max(0.0, args.historical_overlap_penalty)),
        "predict_time_guard_ms": float(max(0.0, args.predict_time_guard_ms)),
        "overlap_discount": float(np.clip(args.overlap_discount, 0.0, 1.0)),
        "cross_seed_observations": bool(args.cross_seed_observations),
        "dynamics_model_file": str(args.dynamics_model) if args.dynamics_model.is_file() else None,
        "spatial_priors_file": str(args.spatial_priors_file) if args.spatial_priors_file.is_file() else None,
        "distance_backend": args.distance_backend,
        "seed_runtime_guard": seed_runtime_guard,
        "used_class_multipliers": class_multipliers.tolist() if class_multipliers is not None else None,
    }
    save_json(args.workspace / "reports" / f"{round_id}_run_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

