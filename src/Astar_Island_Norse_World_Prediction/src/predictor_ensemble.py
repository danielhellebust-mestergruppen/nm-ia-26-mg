from __future__ import annotations

import numpy as np
from pathlib import Path
from typing import Any

from .scoring import apply_probability_floor
from .predictor_unet import build_prediction_tensor_unet
from .predictor_attention_unet import build_prediction_tensor_attn_unet
from .predictor_convlstm import build_prediction_tensor_convlstm

def build_prediction_tensor_ensemble(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 1e-5,
    unet_path: Path | None = None,
    attn_unet_path: Path | None = None,
    convlstm_path: Path | None = None,
) -> np.ndarray:
    """
    Ensemble engine that mathematically averages the probabilities from the three deep learning models
    (U-Net, Attention U-Net, and ConvLSTM) to create a highly robust, low-variance final prediction.
    """
    
    # 1. Generate predictions from all three independent Deep Learning architectures
    pred_unet = build_prediction_tensor_unet(
        initial_grid, 
        observations, 
        floor=floor, 
        model_path=unet_path
    )
    
    pred_attn = build_prediction_tensor_attn_unet(
        initial_grid, 
        observations, 
        floor=floor, 
        model_path=attn_unet_path
    )
    
    pred_lstm = build_prediction_tensor_convlstm(
        initial_grid, 
        observations, 
        floor=floor, 
        model_path=convlstm_path
    )
    
    # 2. Mathematically fuse their distributions (Weighted Average)
    # We heavily weight the Attention U-Net because it is statistically the strongest standalone model,
    # but we mix in the other two to smooth out any hallucinations or edge-case epistemic uncertainty.
    w_attn = 0.60
    w_unet = 0.25
    w_lstm = 0.15
    
    pred_ensemble = (w_attn * pred_attn) + (w_unet * pred_unet) + (w_lstm * pred_lstm)
    
    # 3. Ensure the final fused tensor perfectly sums to 1.0 per tile and respects the KL safety floor
    sums = pred_ensemble.sum(axis=-1, keepdims=True)
    pred_ensemble = pred_ensemble / np.where(sums <= 0, 1.0, sums)
    
    return apply_probability_floor(pred_ensemble, floor=floor)
