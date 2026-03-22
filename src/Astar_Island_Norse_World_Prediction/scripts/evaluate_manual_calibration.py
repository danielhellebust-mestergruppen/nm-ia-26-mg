#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Sample:
    round_number: int
    init_class: np.ndarray
    coastal_mask: np.ndarray
    ground_truth: np.ndarray


def _grid_to_class(grid: np.ndarray) -> np.ndarray:
    mapped = np.zeros_like(grid)
    mapped[np.isin(grid, [0, 10, 11])] = 0
    mapped[grid == 1] = 1
    mapped[grid == 2] = 2
    mapped[grid == 3] = 3
    mapped[grid == 4] = 4
    mapped[grid == 5] = 5
    return mapped


def _adjacent_to_ocean_mask(grid: np.ndarray) -> np.ndarray:
    h, w = grid.shape
    mask = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and int(grid[ny, nx]) == 10:
                    mask[y, x] = True
                    break
    return mask


def _load_samples(rounds_dir: Path) -> list[Sample]:
    out: list[Sample] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        grid = np.asarray(data["initial_grid"], dtype=np.int64)
        out.append(
            Sample(
                round_number=int(data.get("round_number", 0)),
                init_class=_grid_to_class(grid),
                coastal_mask=_adjacent_to_ocean_mask(grid),
                ground_truth=np.asarray(data["ground_truth"], dtype=np.float64),
            )
        )
    return out


def _load_transition_matrix(priors_file: Path) -> np.ndarray:
    data = json.loads(priors_file.read_text(encoding="utf-8"))
    mat = np.asarray(data["transition_matrix"], dtype=np.float64)
    mat = np.maximum(mat, 0.0)
    rs = np.where(mat.sum(axis=1, keepdims=True) <= 0, 1.0, mat.sum(axis=1, keepdims=True))
    return mat / rs


def _score(gt: np.ndarray, pred: np.ndarray) -> float:
    eps = 1e-12
    p = np.clip(gt, eps, 1.0)
    q = np.clip(pred, eps, 1.0)
    kl = np.sum(p * np.log(p / q), axis=-1)
    ent = -np.sum(p * np.log(p), axis=-1)
    denom = float(ent.sum())
    wkl = float((ent * kl).sum() / denom) if denom > 1e-15 else 0.0
    return float(max(0.0, min(100.0, 100.0 * np.exp(-3.0 * wkl))))


def _predict(sample: Sample, tm: np.ndarray, alpha: float, mult: np.ndarray, floor: float = 0.01) -> np.ndarray:
    base = tm[sample.init_class]
    base[..., 2] = np.where(sample.coastal_mask, base[..., 2] * 1.6, base[..., 2] * 0.05)
    base = base / base.sum(axis=-1, keepdims=True)
    base = base * mult.reshape(1, 1, -1)
    base = base / base.sum(axis=-1, keepdims=True)
    observed = np.full((6,), 1.0 / 6.0, dtype=np.float64)
    pred = alpha * base + (1.0 - alpha) * observed.reshape(1, 1, -1)
    pred = np.maximum(pred, floor)
    pred = pred / pred.sum(axis=-1, keepdims=True)
    return pred


def main() -> None:
    parser = argparse.ArgumentParser(description="Quick offline check for manual calibration candidates.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument("--priors-file", type=Path, default=ROOT / "data" / "reports" / "tuned_priors.json")
    args = parser.parse_args()

    samples = _load_samples(args.rounds_dir)
    tm = _load_transition_matrix(args.priors_file)
    candidates = [
        ("manual_a086_r095", 0.86, np.asarray([1.0, 1.1, 1.05, 0.95, 1.0, 1.0], dtype=np.float64)),
        ("manual_a086_r100", 0.86, np.asarray([1.0, 1.1, 1.05, 1.0, 1.0, 1.0], dtype=np.float64)),
        ("manual_a088_r095", 0.88, np.asarray([1.0, 1.1, 1.05, 0.95, 1.0, 1.0], dtype=np.float64)),
        ("manual_a088_r100", 0.88, np.asarray([1.0, 1.1, 1.05, 1.0, 1.0, 1.0], dtype=np.float64)),
    ]

    by_round: dict[int, list[Sample]] = {}
    for s in samples:
        by_round.setdefault(s.round_number, []).append(s)

    out: list[dict] = []
    for name, alpha, mult in candidates:
        all_scores = [_score(s.ground_truth, _predict(s, tm, alpha, mult)) for s in samples]
        fold_scores = {}
        for r, rs in sorted(by_round.items()):
            fold_scores[str(r)] = float(sum(_score(s.ground_truth, _predict(s, tm, alpha, mult)) for s in rs) / len(rs))
        out.append(
            {
                "name": name,
                "alpha": alpha,
                "class_multipliers": mult.tolist(),
                "overall_mean_score": float(sum(all_scores) / len(all_scores)),
                "per_round_mean_score": fold_scores,
            }
        )
    out.sort(key=lambda x: x["overall_mean_score"], reverse=True)
    print(json.dumps({"sample_count": len(samples), "ranked_results": out}, indent=2))


if __name__ == "__main__":
    main()
