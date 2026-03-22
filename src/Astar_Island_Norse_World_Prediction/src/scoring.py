from __future__ import annotations

import math
from typing import Iterable

import numpy as np

from .types import NUM_CLASSES


def apply_probability_floor(prediction: np.ndarray, floor: float = 0.01) -> np.ndarray:
    clipped = np.maximum(prediction, floor)
    sums = clipped.sum(axis=-1, keepdims=True)
    return clipped / sums


def validate_prediction_tensor(
    prediction: np.ndarray, height: int, width: int, tol: float = 1e-2
) -> tuple[bool, str]:
    if prediction.shape != (height, width, NUM_CLASSES):
        return False, f"Expected shape {(height, width, NUM_CLASSES)}, got {prediction.shape}"
    if np.any(prediction < 0):
        return False, "Negative probabilities found"
    sums = prediction.sum(axis=-1)
    if not np.all(np.abs(sums - 1.0) <= tol):
        return False, "Cell probabilities must sum to 1.0 (+/- tolerance)"
    return True, "ok"


def kl_divergence(p: np.ndarray, q: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    p_safe = np.clip(p, eps, 1.0)
    q_safe = np.clip(q, eps, 1.0)
    return np.sum(p_safe * np.log(p_safe / q_safe), axis=-1)


def entropy(p: np.ndarray, eps: float = 1e-12) -> np.ndarray:
    p_safe = np.clip(p, eps, 1.0)
    return -np.sum(p_safe * np.log(p_safe), axis=-1)


def weighted_kl(ground_truth: np.ndarray, prediction: np.ndarray) -> float:
    ent = entropy(ground_truth)
    kl = kl_divergence(ground_truth, prediction)
    denom = float(np.sum(ent))
    if denom <= 1e-15:
        return 0.0
    return float(np.sum(ent * kl) / denom)


def score_from_weighted_kl(weighted_kl_value: float) -> float:
    raw = 100.0 * math.exp(-3.0 * weighted_kl_value)
    return max(0.0, min(100.0, raw))


def score_prediction(ground_truth: np.ndarray, prediction: np.ndarray) -> float:
    wkl = weighted_kl(ground_truth, prediction)
    return score_from_weighted_kl(wkl)


def round_score(seed_scores: Iterable[float]) -> float:
    values = list(seed_scores)
    if not values:
        return 0.0
    return float(sum(values) / len(values))

