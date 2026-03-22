from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .scoring import score_prediction


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def load_observations(observations_dir: Path, round_id: str, seed_index: int) -> list[dict[str, Any]]:
    pattern = f"{round_id}_seed{seed_index}_*.json"
    files = sorted(observations_dir.glob(pattern))
    result: list[dict[str, Any]] = []
    for file_path in files:
        result.append(load_json(file_path))
    return result


def evaluate_against_analysis(
    prediction: np.ndarray, analysis_payload: dict[str, Any]
) -> dict[str, float]:
    ground_truth = np.asarray(analysis_payload["ground_truth"], dtype=np.float64)
    score = score_prediction(ground_truth, prediction)
    api_score = float(analysis_payload.get("score", 0.0) or 0.0)
    return {
        "local_score": float(score),
        "api_score": api_score,
        "delta": float(score - api_score),
    }

