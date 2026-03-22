#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_baseline import build_prediction_tensor
from src.scoring import round_score, score_prediction
from src.types import NUM_CLASSES, grid_value_to_class_index


@dataclass
class Sample:
    round_id: str
    round_number: int
    seed_index: int
    initial_grid: list[list[int]]
    ground_truth: np.ndarray


def _load_samples(rounds_dir: Path) -> list[Sample]:
    samples: list[Sample] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        samples.append(
            Sample(
                round_id=str(data["round_id"]),
                round_number=int(data.get("round_number", 0)),
                seed_index=int(data["seed_index"]),
                initial_grid=data["initial_grid"],
                ground_truth=np.asarray(data["ground_truth"], dtype=np.float64),
            )
        )
    return samples


def _uniform_prediction(h: int, w: int) -> np.ndarray:
    return np.full((h, w, NUM_CLASSES), 1.0 / NUM_CLASSES, dtype=np.float64)


def _load_tuned_matrix(priors_file: Path) -> np.ndarray | None:
    if not priors_file.is_file():
        return None
    data = json.loads(priors_file.read_text(encoding="utf-8"))
    mat = np.asarray(data.get("transition_matrix"), dtype=np.float64)
    if mat.shape != (NUM_CLASSES, NUM_CLASSES):
        return None
    mat = np.maximum(mat, 0.0)
    rs = mat.sum(axis=1, keepdims=True)
    rs = np.where(rs <= 0, 1.0, rs)
    return mat / rs


def _build_recency_matrix(samples: list[Sample], gamma: float) -> np.ndarray:
    mat = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.float64)
    min_round = min(s.round_number for s in samples)
    for s in samples:
        init = np.asarray(s.initial_grid, dtype=np.int64)
        gt = s.ground_truth
        weight = gamma ** (s.round_number - min_round)
        mapped = np.vectorize(grid_value_to_class_index)(init)
        h, w = mapped.shape
        for y in range(h):
            for x in range(w):
                mat[int(mapped[y, x])] += weight * gt[y, x]
    mat = np.maximum(mat, 0.0)
    rs = mat.sum(axis=1, keepdims=True)
    rs = np.where(rs <= 0, 1.0, rs)
    return mat / rs


def _evaluate(samples: list[Sample], mode: str, tuned_matrix: np.ndarray | None, recency_matrix: np.ndarray | None) -> dict:
    per_round: dict[str, list[float]] = {}
    all_scores: list[float] = []

    for s in samples:
        h, w = np.asarray(s.initial_grid, dtype=np.int64).shape
        if mode == "uniform":
            pred = _uniform_prediction(h, w)
        elif mode == "default":
            pred = build_prediction_tensor(s.initial_grid, observations=[], floor=0.01)
        elif mode == "tuned":
            pred = build_prediction_tensor(
                s.initial_grid,
                observations=[],
                floor=0.01,
                transition_matrix=tuned_matrix,
            )
        elif mode == "recency":
            pred = build_prediction_tensor(
                s.initial_grid,
                observations=[],
                floor=0.01,
                transition_matrix=recency_matrix,
            )
        else:
            raise RuntimeError(f"Unknown mode: {mode}")

        sc = float(score_prediction(s.ground_truth, pred))
        key = f"{s.round_number}:{s.round_id}"
        per_round.setdefault(key, []).append(sc)
        all_scores.append(sc)

    round_means = {k: round_score(v) for k, v in per_round.items()}
    return {
        "mode": mode,
        "sample_count": len(samples),
        "overall_mean_score": float(round_score(all_scores)),
        "per_round_mean_score": round_means,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare baseline prior strategies on cached completed rounds.")
    parser.add_argument(
        "--rounds-dir",
        type=Path,
        default=ROOT / "data" / "rounds",
    )
    parser.add_argument(
        "--priors-file",
        type=Path,
        default=ROOT / "data" / "reports" / "tuned_priors.json",
    )
    parser.add_argument("--recency-gamma", type=float, default=1.15)
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "reports" / "prior_compare_report.json",
    )
    args = parser.parse_args()

    samples = _load_samples(args.rounds_dir)
    if not samples:
        raise RuntimeError(f"No cached analysis samples found in {args.rounds_dir}")

    tuned_matrix = _load_tuned_matrix(args.priors_file)
    recency_matrix = _build_recency_matrix(samples, gamma=args.recency_gamma)

    results = []
    results.append(_evaluate(samples, "uniform", tuned_matrix, recency_matrix))
    results.append(_evaluate(samples, "default", tuned_matrix, recency_matrix))
    if tuned_matrix is not None:
        results.append(_evaluate(samples, "tuned", tuned_matrix, recency_matrix))
    results.append(_evaluate(samples, "recency", tuned_matrix, recency_matrix))

    ranked = sorted(results, key=lambda x: x["overall_mean_score"], reverse=True)
    payload = {
        "sample_count": len(samples),
        "recency_gamma": args.recency_gamma,
        "ranked_results": ranked,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

