from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .scoring import apply_probability_floor
from .types import GRID_OCEAN, NUM_CLASSES, grid_value_to_class_index
from .predictor_spatial import SpatialConfig, build_prediction_tensor_spatial
from .predictor_unet import build_prediction_tensor_unet
from .predictor_convlstm import build_prediction_tensor_convlstm
from .predictor_attention_unet import build_prediction_tensor_attn_unet
from .predictor_ensemble import build_prediction_tensor_ensemble
from .predictor_socio_unet import build_prediction_tensor_socio_unet
from .predictor_time_socio_unet import build_prediction_tensor_time_socio_unet

_STATIC_CLASS_PRIOR_SHRINK = 0.80  # class-0 (incl. ocean) and mountain dampening


def _deemphasize_static_classes(prior: np.ndarray) -> np.ndarray:
    # Keep static terrain classes from dominating observed global prior blends.
    out = np.asarray(prior, dtype=np.float64).copy()
    if out.shape != (NUM_CLASSES,):
        return prior
    out[0] *= _STATIC_CLASS_PRIOR_SHRINK
    out[5] *= _STATIC_CLASS_PRIOR_SHRINK
    s = float(out.sum())
    if s <= 0:
        return prior
    return out / s


def _default_distribution_for_grid_value(value: int) -> np.ndarray:
    probs = np.full((NUM_CLASSES,), 1e-6, dtype=np.float64)
    cls = grid_value_to_class_index(value)
    probs[cls] = 0.98
    # small dynamic mass for plausible changes
    if cls == 0:
        probs[1] += 0.006
        probs[2] += 0.004
        probs[3] += 0.004
        probs[4] += 0.004
        probs[5] += 0.002
    elif cls == 4:  # forest mostly static, but can change
        probs[3] += 0.008
        probs[0] += 0.008
        probs[1] += 0.004
    elif cls == 5:  # mountain mostly static
        probs[0] += 0.01
    return probs / probs.sum()


def _collect_dynamic_stats(observations: list[dict[str, Any]]) -> np.ndarray:
    # class counts from observed viewport grids
    counts = np.ones((NUM_CLASSES,), dtype=np.float64)  # Laplace smoothing
    for obs in observations:
        grid = obs.get("grid")
        if not grid:
            continue
        arr = np.asarray(grid, dtype=np.int64)
        mapped = np.vectorize(grid_value_to_class_index)(arr)
        for i in range(NUM_CLASSES):
            counts[i] += float(np.sum(mapped == i))
    probs = counts / counts.sum()
    return _deemphasize_static_classes(probs)


def _load_tuned_matrix(priors_file: Path | None) -> np.ndarray | None:
    if priors_file is None or not priors_file.is_file():
        return None
    data = json.loads(priors_file.read_text(encoding="utf-8"))
    matrix = np.asarray(data.get("transition_matrix"), dtype=np.float64)
    if matrix.shape != (NUM_CLASSES, NUM_CLASSES):
        return None
    # Ensure valid probability rows
    matrix = np.maximum(matrix, 0.0)
    row_sums = matrix.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return matrix / row_sums


def _adjacent_to_ocean(grid: np.ndarray, y: int, x: int) -> bool:
    h, w = grid.shape
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w and int(grid[ny, nx]) == GRID_OCEAN:
            return True
    return False


def _apply_coastal_port_bias(base: np.ndarray, near_ocean: bool) -> np.ndarray:
    # Ports are strongly coastal in practice.
    biased = base.copy()
    if near_ocean:
        biased[2] *= 1.6
    else:
        biased[2] *= 0.05
    s = biased.sum()
    if s <= 0:
        return base
    return biased / s


def _apply_class_multipliers(base: np.ndarray, class_multipliers: np.ndarray | None) -> np.ndarray:
    if class_multipliers is None:
        return base
    if class_multipliers.shape != (NUM_CLASSES,):
        return base
    out = base * np.maximum(class_multipliers, 0.0)
    s = out.sum()
    if s <= 0:
        return base
    return out / s


def build_prediction_tensor(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 1e-5,
    priors_file: Path | None = None,
    transition_matrix: np.ndarray | None = None,
    alpha: float = 0.75,
    alpha_min: float = 0.62,
    alpha_obs_target: int = 10,
    class_multipliers: np.ndarray | None = None,
    predictor_mode: str = "baseline",
    shared_observations: list[dict[str, Any]] | None = None,
    spatial_config: SpatialConfig | None = None,
    hybrid_unet_weight: float = 0.30,
    unet_model_path: Path | None = None,
) -> np.ndarray:
    if predictor_mode == "spatial":
        return build_prediction_tensor_spatial(
            initial_grid=initial_grid,
            observations=observations,
            shared_observations=shared_observations,
            floor=floor,
            transition_matrix=transition_matrix,
            priors_file=priors_file,
            alpha=alpha,
            class_multipliers=class_multipliers,
            config=spatial_config,
        )
    elif predictor_mode == "spatial_unet":
        spatial_pred = build_prediction_tensor_spatial(
            initial_grid=initial_grid,
            observations=observations,
            shared_observations=shared_observations,
            floor=floor,
            transition_matrix=transition_matrix,
            priors_file=priors_file,
            alpha=alpha,
            class_multipliers=class_multipliers,
            config=spatial_config,
        )
        unet_pred = build_prediction_tensor_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor,
            model_path=unet_model_path,
        )
        w_unet = float(np.clip(hybrid_unet_weight, 0.0, 1.0))
        pred = (1.0 - w_unet) * spatial_pred + w_unet * unet_pred
        return apply_probability_floor(pred, floor=floor)
    elif predictor_mode == "unet":
        return build_prediction_tensor_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor,
            model_path=unet_model_path,
        )
    elif predictor_mode == "convlstm":
        return build_prediction_tensor_convlstm(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "attn_unet":
        return build_prediction_tensor_attn_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "time_socio_unet":
        from .predictor_time_socio_unet import build_prediction_tensor_time_socio_unet
        return build_prediction_tensor_time_socio_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "gnn":
        from .predictor_gnn import build_prediction_tensor_gnn
        return build_prediction_tensor_gnn(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "socio_unet":
        return build_prediction_tensor_socio_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "time_socio_unet":
        return build_prediction_tensor_time_socio_unet(
            initial_grid=initial_grid,
            observations=observations,
            floor=floor
        )
    elif predictor_mode == "unet_spatial":
        # 1. Use the powerful U-Net to generate a map-specific perfect prior (0 queries)
        unet_prior = build_prediction_tensor_unet(
            initial_grid=initial_grid,
            observations=[],
            floor=floor
        )
        
        # 2. Disable redundant spatial heuristics (U-Net already calculates them inherently)
        if spatial_config is None:
            spatial_config = SpatialConfig()
        spatial_config.influence_settlement_weight = 0.0
        spatial_config.influence_port_weight = 0.0
        spatial_config.influence_ruin_weight = 0.0
        spatial_config.influence_forest_weight = 0.0
        spatial_config.smoothing_weight = 0.0
        spatial_config.fallback_blend_weight = 0.0
        
        # 3. Feed the U-Net prior into the Spatial model, which acts as a robust Active Learning observation blender
        return build_prediction_tensor_spatial(
            initial_grid=initial_grid,
            observations=observations,
            shared_observations=shared_observations,
            floor=floor,
            transition_matrix=transition_matrix,
            priors_file=priors_file,
            alpha=alpha,
            class_multipliers=class_multipliers,
            config=spatial_config,
            custom_base_tensor=unet_prior,
        )
    elif predictor_mode == "attn_unet_spatial":
        unet_prior = build_prediction_tensor_attn_unet(
            initial_grid=initial_grid,
            observations=[],
            floor=floor
        )
        if spatial_config is None:
            spatial_config = SpatialConfig()
        spatial_config.influence_settlement_weight = 0.0
        spatial_config.influence_port_weight = 0.0
        spatial_config.influence_ruin_weight = 0.0
        spatial_config.influence_forest_weight = 0.0
        spatial_config.smoothing_weight = 0.0
        spatial_config.fallback_blend_weight = 0.0
        return build_prediction_tensor_spatial(
            initial_grid=initial_grid,
            observations=observations,
            shared_observations=shared_observations,
            floor=floor,
            transition_matrix=transition_matrix,
            priors_file=priors_file,
            alpha=alpha,
            class_multipliers=class_multipliers,
            config=spatial_config,
            custom_base_tensor=unet_prior,
        )

    grid = np.asarray(initial_grid, dtype=np.int64)
    h, w = grid.shape
    pred = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)

    observed_priors = _collect_dynamic_stats(observations)
    tuned_matrix = transition_matrix
    if tuned_matrix is None:
        tuned_matrix = _load_tuned_matrix(priors_file)
    n_obs = len(observations)
    # More observations -> lean more on observed distribution.
    obs_frac = min(1.0, n_obs / max(1, int(alpha_obs_target)))
    a_base = float(np.clip(alpha, 0.0, 1.0))
    a_min = float(np.clip(alpha_min, 0.0, 1.0))
    a_eff = a_base * (1.0 - obs_frac) + a_min * obs_frac

    for y in range(h):
        for x in range(w):
            cls = grid_value_to_class_index(int(grid[y, x]))
            if tuned_matrix is not None:
                base = tuned_matrix[cls]
            else:
                base = _default_distribution_for_grid_value(int(grid[y, x]))
            base = _apply_coastal_port_bias(base, near_ocean=_adjacent_to_ocean(grid, y, x))
            base = _apply_class_multipliers(base, class_multipliers=class_multipliers)
            # Blend per-cell prior with observed global frequencies.
            pred[y, x] = a_eff * base + (1.0 - a_eff) * observed_priors

    ocean_mask = (grid == 10)
    coastal_mask = np.zeros_like(ocean_mask)
    for y in range(h):
        for x in range(w):
            if _adjacent_to_ocean(grid, y, x):
                coastal_mask[y, x] = True
                
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    pred = apply_probability_floor(pred, floor=floor)
    return pred

