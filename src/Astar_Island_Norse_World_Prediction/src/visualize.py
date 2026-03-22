from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from .scoring import entropy, kl_divergence


def _save_matrix_png(matrix: np.ndarray, title: str, out_path: Path, cmap: str = "viridis") -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(6, 6))
    plt.imshow(matrix, cmap=cmap)
    plt.title(title)
    plt.colorbar()
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def save_prediction_visuals(prediction: np.ndarray, out_dir: Path, stem: str) -> None:
    argmax_map = np.argmax(prediction, axis=-1)
    confidence = np.max(prediction, axis=-1)
    pred_entropy = entropy(prediction)
    _save_matrix_png(argmax_map, f"{stem} argmax", out_dir / f"{stem}_argmax.png", cmap="tab20")
    _save_matrix_png(confidence, f"{stem} confidence", out_dir / f"{stem}_confidence.png")
    _save_matrix_png(pred_entropy, f"{stem} entropy", out_dir / f"{stem}_entropy.png")


def save_error_visuals(
    prediction: np.ndarray, ground_truth: np.ndarray, out_dir: Path, stem: str
) -> None:
    cell_kl = kl_divergence(ground_truth, prediction)
    _save_matrix_png(cell_kl, f"{stem} KL error", out_dir / f"{stem}_kl.png")

