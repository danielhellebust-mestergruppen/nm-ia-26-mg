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
    round_id: str
    round_number: int
    init_class: np.ndarray
    coastal_mask: np.ndarray
    ground_truth: np.ndarray


def _load_samples(rounds_dir: Path) -> list[Sample]:
    out: list[Sample] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        grid = np.asarray(data["initial_grid"], dtype=np.int64)
        out.append(
            Sample(
                round_id=str(data["round_id"]),
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
    rs = mat.sum(axis=1, keepdims=True)
    rs = np.where(rs <= 0, 1.0, rs)
    return mat / rs


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


def _grid_to_class(grid: np.ndarray) -> np.ndarray:
    mapped = np.zeros_like(grid)
    mapped[np.isin(grid, [0, 10, 11])] = 0
    mapped[grid == 1] = 1
    mapped[grid == 2] = 2
    mapped[grid == 3] = 3
    mapped[grid == 4] = 4
    mapped[grid == 5] = 5
    return mapped


def _apply_floor(pred: np.ndarray, floor: float) -> np.ndarray:
    pred = np.maximum(pred, floor)
    return pred / pred.sum(axis=-1, keepdims=True)


def _score(gt: np.ndarray, pred: np.ndarray) -> float:
    eps = 1e-12
    p = np.clip(gt, eps, 1.0)
    q = np.clip(pred, eps, 1.0)
    kl = np.sum(p * np.log(p / q), axis=-1)
    ent = -np.sum(p * np.log(p), axis=-1)
    denom = float(ent.sum())
    wkl = float((ent * kl).sum() / denom) if denom > 1e-15 else 0.0
    return float(max(0.0, min(100.0, 100.0 * np.exp(-3.0 * wkl))))


def _predict(
    sample: Sample,
    transition_matrix: np.ndarray,
    alpha: float,
    class_multipliers: np.ndarray,
    floor: float = 0.01,
) -> np.ndarray:
    base = transition_matrix[sample.init_class]  # HxWx6

    # coastal port bias
    base[..., 2] = np.where(sample.coastal_mask, base[..., 2] * 1.6, base[..., 2] * 0.05)
    base = base / base.sum(axis=-1, keepdims=True)

    # class-level calibration
    base = base * class_multipliers.reshape(1, 1, -1)
    base = base / base.sum(axis=-1, keepdims=True)

    observed = np.full((6,), 1.0 / 6.0, dtype=np.float64)  # offline no-query mode
    pred = alpha * base + (1.0 - alpha) * observed.reshape(1, 1, -1)
    pred = _apply_floor(pred, floor=floor)
    return pred


def _grid_candidates() -> list[tuple[float, np.ndarray]]:
    # Fast focused search around recently strong values.
    alphas = [0.84, 0.86, 0.88, 0.90]
    settlement = [1.05, 1.1, 1.15]
    port = [1.0, 1.05, 1.1]
    ruin = [0.95, 1.0]
    forest = [1.0]

    out: list[tuple[float, np.ndarray]] = []
    for a in alphas:
        for ms in settlement:
            for mp in port:
                for mr in ruin:
                    for mf in forest:
                        mult = np.asarray([1.0, ms, mp, mr, mf, 1.0], dtype=np.float64)
                        out.append((a, mult))
    return out


def _mean_score(samples: list[Sample], tm: np.ndarray, alpha: float, mult: np.ndarray) -> float:
    scores = []
    for s in samples:
        pred = _predict(s, tm, alpha, mult)
        scores.append(_score(s.ground_truth, pred))
    return float(sum(scores) / len(scores)) if scores else 0.0


def _round_holdout_cv(samples: list[Sample], tm: np.ndarray) -> dict:
    by_round: dict[int, list[Sample]] = {}
    for s in samples:
        by_round.setdefault(s.round_number, []).append(s)

    candidates = _grid_candidates()
    fold_results = []
    for holdout_round, holdout_samples in sorted(by_round.items()):
        train_samples = [s for s in samples if s.round_number != holdout_round]
        best_alpha = 0.75
        best_mult = np.ones((6,), dtype=np.float64)
        best_train = -1.0
        for alpha, mult in candidates:
            sc = _mean_score(train_samples, tm, alpha, mult)
            if sc > best_train:
                best_train = sc
                best_alpha = alpha
                best_mult = mult
        holdout_score = _mean_score(holdout_samples, tm, best_alpha, best_mult)
        fold_results.append(
            {
                "holdout_round": holdout_round,
                "best_train_score": best_train,
                "holdout_score": holdout_score,
                "alpha": best_alpha,
                "class_multipliers": best_mult.tolist(),
            }
        )
    cv_mean = float(sum(f["holdout_score"] for f in fold_results) / len(fold_results))
    return {"folds": fold_results, "cv_mean_holdout_score": cv_mean}


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune alpha + class multipliers with round holdout CV.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument(
        "--priors-file", type=Path, default=ROOT / "data" / "reports" / "tuned_priors.json"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "reports" / "blend_tuning.json"
    )
    args = parser.parse_args()

    if not args.priors_file.is_file():
        raise RuntimeError(f"Priors file not found: {args.priors_file}")
    samples = _load_samples(args.rounds_dir)
    if len(samples) < 5:
        raise RuntimeError("Need more cached samples for tuning")
    tm = _load_transition_matrix(args.priors_file)

    cv = _round_holdout_cv(samples, tm)

    # Fit best on all samples for deployment
    best_all = {"score": -1.0, "alpha": 0.75, "mult": np.ones((6,), dtype=np.float64)}
    for alpha, mult in _grid_candidates():
        sc = _mean_score(samples, tm, alpha, mult)
        if sc > best_all["score"]:
            best_all = {"score": sc, "alpha": alpha, "mult": mult}

    payload = {
        "sample_count": len(samples),
        "cv": cv,
        "deploy": {
            "alpha": best_all["alpha"],
            "class_multipliers": best_all["mult"].tolist(),
            "in_sample_score": best_all["score"],
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

