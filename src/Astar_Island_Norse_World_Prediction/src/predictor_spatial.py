from __future__ import annotations

import json
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .scoring import apply_probability_floor
from .types import GRID_OCEAN, NUM_CLASSES, grid_value_to_class_index

_INFLUENCE_FIELD_CACHE: dict[tuple[Any, ...], np.ndarray] = {}
_INFLUENCE_FIELD_CACHE_MAX = 8192


@dataclass
class SpatialConfig:
    floor: float = 1e-5
    local_count_threshold: int = 5
    local_blend_max: float = 0.22
    smoothing_weight: float = 0.12
    smoothing_passes: int = 1
    influence_tau: float = 4.5
    influence_max_distance: int = 14
    influence_settlement_weight: float = 0.55
    influence_port_weight: float = 0.45
    coast_port_weight: float = 0.0
    coast_tau: float = 6.0
    influence_ruin_weight: float = 0.20
    influence_forest_weight: float = 0.18
    fallback_blend_weight: float = 0.28
    static_class_prior_shrink: float = 0.80
    alpha_base: float = 0.78
    alpha_min: float = 0.58
    alpha_entropy_weight: float = 0.10
    alpha_distance_weight: float = 0.12
    alpha_count_weight: float = 0.22
    settlement_prob_coeffs: np.ndarray | None = None
    port_prob_coeffs: np.ndarray | None = None
    ruin_prob_coeffs: np.ndarray | None = None
    distance_backend: str = "python"


def _safe_row_norm(x: np.ndarray) -> np.ndarray:
    sums = x.sum(axis=-1, keepdims=True)
    sums = np.where(sums <= 0, 1.0, sums)
    return x / sums


def _deemphasize_static_classes(prior: np.ndarray, shrink: float) -> np.ndarray:
    out = np.asarray(prior, dtype=np.float64).copy()
    if out.shape != (NUM_CLASSES,):
        return prior
    s_shrink = float(np.clip(shrink, 0.1, 1.0))
    out[0] *= s_shrink
    out[5] *= s_shrink
    s = float(out.sum())
    if s <= 0:
        return prior
    return out / s


def _default_distribution_for_grid_value(value: int) -> np.ndarray:
    probs = np.full((NUM_CLASSES,), 1e-6, dtype=np.float64)
    cls = grid_value_to_class_index(value)
    probs[cls] = 0.98
    if cls == 0:
        probs[1] += 0.006
        probs[2] += 0.004
        probs[3] += 0.004
        probs[4] += 0.004
        probs[5] += 0.002
    elif cls == 4:
        probs[3] += 0.008
        probs[0] += 0.008
        probs[1] += 0.004
    elif cls == 5:
        probs[0] += 0.01
    return probs / probs.sum()


def _load_tuned_matrix(priors_file: Path | None) -> np.ndarray | None:
    if priors_file is None or not priors_file.is_file():
        return None
    data = json.loads(priors_file.read_text(encoding="utf-8"))
    matrix = np.asarray(data.get("transition_matrix"), dtype=np.float64)
    if matrix.shape != (NUM_CLASSES, NUM_CLASSES):
        return None
    matrix = np.maximum(matrix, 0.0)
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return matrix / row_sums


def _collect_global_observed_priors(observations: list[dict[str, Any]], static_shrink: float) -> np.ndarray:
    counts = np.ones((NUM_CLASSES,), dtype=np.float64)
    for obs in observations:
        grid = obs.get("grid")
        if grid is None:
            continue
        arr = np.asarray(grid, dtype=np.int64)
        mapped = np.vectorize(grid_value_to_class_index)(arr)
        for c in range(NUM_CLASSES):
            counts[c] += float(np.sum(mapped == c))
    probs = counts / counts.sum()
    return _deemphasize_static_classes(probs, shrink=static_shrink)


def _build_local_evidence(
    h: int,
    w: int,
    observations: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    evidence = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)
    counts = np.zeros((h, w), dtype=np.float64)
    observed_mask = np.zeros((h, w), dtype=bool)
    for obs in observations:
        grid = obs.get("grid")
        vp = obs.get("viewport", {})
        if grid is None:
            continue
        x = int(vp.get("x", -1))
        y = int(vp.get("y", -1))
        if x < 0 or y < 0:
            continue
        arr = np.asarray(grid, dtype=np.int64)
        vh, vw = arr.shape
        y2 = min(h, y + vh)
        x2 = min(w, x + vw)
        if y2 <= y or x2 <= x:
            continue
        arr = arr[: y2 - y, : x2 - x]
        cls = np.vectorize(grid_value_to_class_index)(arr)
        for c in range(NUM_CLASSES):
            m = cls == c
            evidence[y:y2, x:x2, c] += m.astype(np.float64)
        counts[y:y2, x:x2] += 1.0
        observed_mask[y:y2, x:x2] = True
    local_probs = np.full((h, w, NUM_CLASSES), 1.0 / NUM_CLASSES, dtype=np.float64)
    valid = counts > 0
    if np.any(valid):
        local_probs[valid] = evidence[valid] / counts[valid, None]
    return evidence, counts, local_probs


def _multi_source_manhattan_distance(observed_mask: np.ndarray) -> np.ndarray:
    h, w = observed_mask.shape
    inf = 10**9
    dist = np.full((h, w), inf, dtype=np.int64)
    qy = np.zeros((h * w,), dtype=np.int64)
    qx = np.zeros((h * w,), dtype=np.int64)
    head = 0
    tail = 0
    ys, xs = np.where(observed_mask)
    for y, x in zip(ys, xs, strict=False):
        dist[y, x] = 0
        qy[tail] = y
        qx[tail] = x
        tail += 1
    if tail == 0:
        # No observed cells: return normalized large distance map.
        yy, xx = np.indices((h, w))
        center_y = h // 2
        center_x = w // 2
        d = np.abs(yy - center_y) + np.abs(xx - center_x)
        d = d.astype(np.float64)
        mx = float(np.max(d)) if d.size else 1.0
        return d / max(1.0, mx)
    while head < tail:
        y = int(qy[head])
        x = int(qx[head])
        head += 1
        nd = dist[y, x] + 1
        if y > 0 and nd < dist[y - 1, x]:
            dist[y - 1, x] = nd
            qy[tail] = y - 1
            qx[tail] = x
            tail += 1
        if y + 1 < h and nd < dist[y + 1, x]:
            dist[y + 1, x] = nd
            qy[tail] = y + 1
            qx[tail] = x
            tail += 1
        if x > 0 and nd < dist[y, x - 1]:
            dist[y, x - 1] = nd
            qy[tail] = y
            qx[tail] = x - 1
            tail += 1
        if x + 1 < w and nd < dist[y, x + 1]:
            dist[y, x + 1] = nd
            qy[tail] = y
            qx[tail] = x + 1
            tail += 1
    d = dist.astype(np.float64)
    mx = float(np.max(d)) if d.size else 1.0
    return d / max(1.0, mx)


def _distance_to_ocean(init_grid: np.ndarray) -> np.ndarray:
    h, w = init_grid.shape
    inf = 10**9
    dist = np.full((h, w), inf, dtype=np.int64)
    qy = np.zeros((h * w,), dtype=np.int64)
    qx = np.zeros((h * w,), dtype=np.int64)
    head = 0
    tail = 0
    ys, xs = np.where(init_grid == GRID_OCEAN)
    for y, x in zip(ys, xs, strict=False):
        dist[y, x] = 0
        qy[tail] = y
        qx[tail] = x
        tail += 1
    if tail == 0:
        yy, xx = np.indices((h, w))
        center_y = h // 2
        center_x = w // 2
        return (np.abs(yy - center_y) + np.abs(xx - center_x)).astype(np.float64)
    while head < tail:
        y = int(qy[head])
        x = int(qx[head])
        head += 1
        nd = dist[y, x] + 1
        if y > 0 and nd < dist[y - 1, x]:
            dist[y - 1, x] = nd
            qy[tail] = y - 1
            qx[tail] = x
            tail += 1
        if y + 1 < h and nd < dist[y + 1, x]:
            dist[y + 1, x] = nd
            qy[tail] = y + 1
            qx[tail] = x
            tail += 1
        if x > 0 and nd < dist[y, x - 1]:
            dist[y, x - 1] = nd
            qy[tail] = y
            qx[tail] = x - 1
            tail += 1
        if x + 1 < w and nd < dist[y, x + 1]:
            dist[y, x + 1] = nd
            qy[tail] = y
            qx[tail] = x + 1
            tail += 1
    return dist.astype(np.float64)


def _movement_cost(value: int) -> float:
    if value == GRID_OCEAN:
        return 6.0
    if value == 5:  # mountain
        return 3.0
    return 1.0


def _dijkstra_influence_from_source(
    init_grid: np.ndarray,
    src_y: int,
    src_x: int,
    tau: float,
    max_distance: int,
) -> np.ndarray:
    import heapq

    h, w = init_grid.shape
    inf = 10**9
    dist = np.full((h, w), inf, dtype=np.float64)
    pq: list[tuple[float, int, int]] = []
    dist[src_y, src_x] = 0.0
    heapq.heappush(pq, (0.0, src_y, src_x))
    while pq:
        d, y, x = heapq.heappop(pq)
        if d > dist[y, x]:
            continue
        if d > max_distance:
            continue
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if ny < 0 or ny >= h or nx < 0 or nx >= w:
                continue
            nd = d + _movement_cost(int(init_grid[ny, nx]))
            if nd < dist[ny, nx] and nd <= max_distance:
                dist[ny, nx] = nd
                heapq.heappush(pq, (nd, ny, nx))
    out = np.exp(-dist / max(1e-6, tau))
    out[dist >= inf / 2] = 0.0
    return out


def _dijkstra_influence_from_source_scipy(
    init_grid: np.ndarray,
    src_y: int,
    src_x: int,
    tau: float,
    max_distance: int,
) -> np.ndarray:
    # Optional fast path using SciPy sparse graph shortest paths.
    try:
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import dijkstra as sp_dijkstra
    except Exception:
        return _dijkstra_influence_from_source(init_grid, src_y, src_x, tau, max_distance)

    h, w = init_grid.shape
    n = h * w
    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []

    def node(y: int, x: int) -> int:
        return y * w + x

    for y in range(h):
        for x in range(w):
            u = node(y, x)
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if ny < 0 or ny >= h or nx < 0 or nx >= w:
                    continue
                rows.append(u)
                cols.append(node(ny, nx))
                data.append(_movement_cost(int(init_grid[ny, nx])))
    g = coo_matrix((data, (rows, cols)), shape=(n, n)).tocsr()
    src = node(src_y, src_x)
    dist = sp_dijkstra(csgraph=g, directed=True, indices=src, limit=max_distance, return_predecessors=False)
    dist = np.asarray(dist, dtype=np.float64).reshape((h, w))
    out = np.exp(-dist / max(1e-6, tau))
    out[np.isinf(dist)] = 0.0
    return out


def _build_settlement_influence(
    init_grid: np.ndarray,
    observations: list[dict[str, Any]],
    cfg: SpatialConfig,
) -> np.ndarray:
    h, w = init_grid.shape
    influence = np.zeros((h, w), dtype=np.float64)
    terrain_signature = int(zlib.crc32(np.ascontiguousarray(init_grid).tobytes()))
    for obs in observations:
        settlements = obs.get("settlements") or []
        for s in settlements:
            x = int(s.get("x", -1))
            y = int(s.get("y", -1))
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            pop = float(s.get("population", 0.0) or 0.0)
            food = float(s.get("food", 0.0) or 0.0)
            wealth = float(s.get("wealth", 0.0) or 0.0)
            defense = float(s.get("defense", 0.0) or 0.0)
            has_port = bool(s.get("has_port", False))
            if cfg.settlement_prob_coeffs is not None:
                feat = np.asarray([1.0, pop, food, wealth, defense, 1.0 if has_port else 0.0], dtype=np.float64)
                pred_s = float(np.dot(cfg.settlement_prob_coeffs, feat))
                pred_p = float(np.dot(cfg.port_prob_coeffs, feat)) if cfg.port_prob_coeffs is not None else 0.0
                pred_r = float(np.dot(cfg.ruin_prob_coeffs, feat)) if cfg.ruin_prob_coeffs is not None else 0.0
                strength = max(0.0, pred_s + 0.7 * pred_p + 0.4 * pred_r)
            else:
                # Light-weight heuristic fallback.
                strength = max(0.0, 0.45 * pop + 0.40 * wealth + 0.20 * defense + 0.10 * food)
                if has_port:
                    strength *= 1.12
            cache_key = (
                terrain_signature,
                h,
                w,
                y,
                x,
                round(float(cfg.influence_tau), 5),
                int(cfg.influence_max_distance),
            )
            field = _INFLUENCE_FIELD_CACHE.get(cache_key)
            if field is None:
                if cfg.distance_backend == "scipy":
                    field = _dijkstra_influence_from_source_scipy(
                        init_grid=init_grid,
                        src_y=y,
                        src_x=x,
                        tau=cfg.influence_tau,
                        max_distance=cfg.influence_max_distance,
                    )
                else:
                    field = _dijkstra_influence_from_source(
                        init_grid=init_grid,
                        src_y=y,
                        src_x=x,
                        tau=cfg.influence_tau,
                        max_distance=cfg.influence_max_distance,
                    )
                if len(_INFLUENCE_FIELD_CACHE) >= _INFLUENCE_FIELD_CACHE_MAX:
                    _INFLUENCE_FIELD_CACHE.pop(next(iter(_INFLUENCE_FIELD_CACHE)))
                _INFLUENCE_FIELD_CACHE[cache_key] = field
            influence += strength * field
    if np.max(influence) > 0:
        influence = influence / float(np.max(influence))
    return influence


def load_spatial_dynamics_coeffs(model_file: Path | None) -> dict[str, np.ndarray]:
    if model_file is None or not model_file.is_file():
        return {}
    data = json.loads(model_file.read_text(encoding="utf-8"))
    models = data.get("models", {})
    out: dict[str, np.ndarray] = {}
    for k, kk in (
        ("settlement_prob_coeffs", "settlement_prob"),
        ("port_prob_coeffs", "port_prob"),
        ("ruin_prob_coeffs", "ruin_prob"),
    ):
        arr = np.asarray(models.get(kk, []), dtype=np.float64)
        if arr.shape == (6,):
            out[k] = arr
    return out


def load_spatial_priors(priors_file: Path | None) -> dict[str, Any]:
    if priors_file is None or not priors_file.is_file():
        return {}
    data = json.loads(priors_file.read_text(encoding="utf-8"))
    allowed = {
        "local_count_threshold",
        "local_blend_max",
        "smoothing_weight",
        "smoothing_passes",
        "influence_tau",
        "influence_settlement_weight",
        "influence_port_weight",
        "coast_port_weight",
        "coast_tau",
        "influence_ruin_weight",
        "influence_forest_weight",
        "fallback_blend_weight",
        "static_class_prior_shrink",
        "alpha_count_weight",
        "alpha_entropy_weight",
        "alpha_distance_weight",
        "distance_backend",
    }
    return {k: v for k, v in data.items() if k in allowed}


def _neighbor_average(pred: np.ndarray) -> np.ndarray:
    h, w, _ = pred.shape
    out = np.zeros_like(pred)
    out += np.roll(pred, 1, axis=0)
    out += np.roll(pred, -1, axis=0)
    out += np.roll(pred, 1, axis=1)
    out += np.roll(pred, -1, axis=1)
    # Fix borders to avoid wrap-around artifacts.
    out[0, :, :] -= pred[-1, :, :]
    out[-1, :, :] -= pred[0, :, :]
    out[:, 0, :] -= pred[:, -1, :]
    out[:, -1, :] -= pred[:, 0, :]
    denom = np.full((h, w, 1), 4.0, dtype=np.float64)
    denom[0, :, :] -= 1.0
    denom[-1, :, :] -= 1.0
    denom[:, 0, :] -= 1.0
    denom[:, -1, :] -= 1.0
    denom = np.maximum(denom, 1.0)
    return out / denom


def _dynamic_alpha(
    base_alpha: float,
    cfg: SpatialConfig,
    local_counts: np.ndarray,
    entropy_map: np.ndarray,
    dist_to_observed: np.ndarray,
) -> np.ndarray:
    c = np.clip(local_counts / max(1.0, float(cfg.local_count_threshold) * 3.0), 0.0, 1.0)
    e = entropy_map / max(1e-6, np.log(float(NUM_CLASSES)))
    d = np.clip(dist_to_observed, 0.0, 1.0)
    alpha = (
        base_alpha
        - cfg.alpha_count_weight * c
        - cfg.alpha_entropy_weight * e
        + cfg.alpha_distance_weight * d
    )
    alpha = np.clip(alpha, cfg.alpha_min, 0.98)
    return alpha


def build_prediction_tensor_spatial(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    shared_observations: list[dict[str, Any]] | None = None,
    floor: float = 1e-5,
    transition_matrix: np.ndarray | None = None,
    priors_file: Any = None,
    alpha: float = 0.78,
    class_multipliers: np.ndarray | None = None,
    config: SpatialConfig | None = None,
    custom_base_tensor: np.ndarray | None = None,
) -> np.ndarray:
    cfg = config or SpatialConfig(floor=floor)
    init_grid = np.asarray(initial_grid, dtype=np.int64)
    h, w = init_grid.shape
    all_obs = (shared_observations or []) + observations

    tuned_matrix = transition_matrix
    if tuned_matrix is None and custom_base_tensor is None:
        tuned_matrix = _load_tuned_matrix(priors_file)

    if custom_base_tensor is not None:
        base = custom_base_tensor.copy()
    elif tuned_matrix is None:
        base = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)
        for y in range(h):
            for x in range(w):
                base[y, x] = _default_distribution_for_grid_value(int(init_grid[y, x]))
    else:
        tuned_matrix = np.asarray(tuned_matrix, dtype=np.float64)
        init_cls = np.vectorize(grid_value_to_class_index)(init_grid)
        base = tuned_matrix[init_cls]  # HxWx6
    if class_multipliers is not None and class_multipliers.shape == (NUM_CLASSES,):
        base = base * np.maximum(class_multipliers.reshape((1, 1, -1)), 0.0)
        base = _safe_row_norm(base)

    _, local_counts, local_probs = _build_local_evidence(h=h, w=w, observations=all_obs)
    observed_mask = local_counts > 0
    dist_to_observed = _multi_source_manhattan_distance(observed_mask)
    global_prior = _collect_global_observed_priors(
        all_obs,
        static_shrink=cfg.static_class_prior_shrink,
    )
    influence = _build_settlement_influence(init_grid=init_grid, observations=all_obs, cfg=cfg)
    dist_to_coast = _distance_to_ocean(init_grid)
    coast_factor = np.exp(-dist_to_coast / max(1e-6, float(cfg.coast_tau)))

    pred = base.copy()
    # Spatial class shifts from settlement influence.
    pred[..., 1] *= 1.0 + cfg.influence_settlement_weight * influence
    pred[..., 2] *= 1.0 + cfg.influence_port_weight * influence + cfg.coast_port_weight * coast_factor
    pred[..., 3] *= 1.0 + cfg.influence_ruin_weight * influence
    pred[..., 4] *= 1.0 - cfg.influence_forest_weight * influence
    pred = _safe_row_norm(pred)

    # Local evidence blend where available.
    local_blend = np.clip(local_counts / max(1.0, float(cfg.local_count_threshold)), 0.0, 1.0)
    local_blend = np.minimum(local_blend, cfg.local_blend_max)
    pred = (1.0 - local_blend[..., None]) * pred + local_blend[..., None] * local_probs
    pred = _safe_row_norm(pred)

    # Global fallback blend where local evidence is weak.
    fallback_blend = np.clip(1.0 - local_blend, 0.0, 1.0)
    fbw = float(np.clip(cfg.fallback_blend_weight, 0.0, 1.0))
    pred = (1.0 - fbw * fallback_blend[..., None]) * pred + fbw * fallback_blend[..., None] * global_prior
    pred = _safe_row_norm(pred)

    # Neighbor smoothing.
    for _ in range(max(0, int(cfg.smoothing_passes))):
        neigh = _neighbor_average(pred)
        pred = (1.0 - cfg.smoothing_weight) * pred + cfg.smoothing_weight * neigh
        pred = _safe_row_norm(pred)

    # Dynamic alpha blend against original transition prior.
    ent = -np.sum(np.clip(pred, 1e-12, 1.0) * np.log(np.clip(pred, 1e-12, 1.0)), axis=-1)
    alpha_map = _dynamic_alpha(
        base_alpha=alpha,
        cfg=cfg,
        local_counts=local_counts,
        entropy_map=ent,
        dist_to_observed=dist_to_observed,
    )
    pred = alpha_map[..., None] * pred + (1.0 - alpha_map[..., None]) * base
    pred = _safe_row_norm(pred)

    ocean_mask = (init_grid == 10)
    coastal_mask = np.zeros_like(ocean_mask)
    for y in range(h):
        for x in range(w):
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and init_grid[ny, nx] == 10:
                    coastal_mask[y, x] = True
                    break
                    
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    mountain_mask = (init_grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    return apply_probability_floor(pred, floor=max(cfg.floor, floor))

