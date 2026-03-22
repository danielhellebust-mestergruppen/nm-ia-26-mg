from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Any

from .scoring import apply_probability_floor
from .predictor_attention_unet import build_prediction_tensor_attn_unet
from .predictor_socio_unet import build_prediction_tensor_socio_unet
from .predictor_time_socio_unet import build_prediction_tensor_time_socio_unet
from .predictor_time_socio_deep_unet import build_prediction_tensor_time_socio_deep_unet

def build_prediction_tensor_meta_ensemble(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 1e-5,
) -> np.ndarray:
    """
    The Meta-Ensemble: Mathematically fuses our four best models to achieve
    maximum stability and minimum variance across unseen rounds.
    """
    
    # 1. Generate predictions from the core elite models
    pred_attn = build_prediction_tensor_attn_unet(initial_grid, observations, floor=floor)
    pred_socio = build_prediction_tensor_socio_unet(initial_grid, observations, floor=floor)
    pred_time = build_prediction_tensor_time_socio_unet(initial_grid, observations, floor=floor)
    pred_deep = build_prediction_tensor_time_socio_deep_unet(initial_grid, observations, floor=floor)
    
    # 2. Mathematically fuse (Equally weighted for maximum stability)
    # This prevents any single model's hallucination from dominating the result.
    pred_ensemble = (pred_attn + pred_socio + pred_time + pred_deep) / 4.0
    
    # 3. Ensure normalization
    sums = pred_ensemble.sum(axis=-1, keepdims=True)
    pred_ensemble = pred_ensemble / np.where(sums <= 0, 1.0, sums)
    
    return apply_probability_floor(pred_ensemble, floor=floor)
