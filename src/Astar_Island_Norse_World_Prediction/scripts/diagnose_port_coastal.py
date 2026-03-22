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


@dataclass
class Sample:
    round_id: str
    round_number: int
    initial_grid: list[list[int]]


def _load_samples(rounds_dir: Path) -> list[Sample]:
    out: list[Sample] = []
    for fp in sorted(rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        out.append(
            Sample(
                round_id=str(data["round_id"]),
                round_number=int(data.get("round_number", 0)),
                initial_grid=data["initial_grid"],
            )
        )
    return out


def _adjacent_to_ocean(grid: np.ndarray) -> np.ndarray:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose coastal vs inland port probabilities.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument(
        "--priors-file", type=Path, default=ROOT / "data" / "reports" / "tuned_priors.json"
    )
    parser.add_argument(
        "--blend-config", type=Path, default=ROOT / "data" / "reports" / "blend_tuning.json"
    )
    parser.add_argument("--port-threshold", type=float, default=0.10)
    parser.add_argument(
        "--out", type=Path, default=ROOT / "data" / "reports" / "port_coastal_diagnostic.json"
    )
    args = parser.parse_args()

    alpha = 0.75
    mult = None
    if args.blend_config.is_file():
        cfg = json.loads(args.blend_config.read_text(encoding="utf-8"))
        deploy = cfg.get("deploy", {})
        if "alpha" in deploy:
            alpha = float(deploy["alpha"])
        if isinstance(deploy.get("class_multipliers"), list) and len(deploy["class_multipliers"]) == 6:
            mult = np.asarray(deploy["class_multipliers"], dtype=np.float64)

    samples = _load_samples(args.rounds_dir)
    if not samples:
        raise RuntimeError("No cached round samples found")

    coastal_probs = []
    inland_probs = []
    coastal_high = 0
    inland_high = 0
    coastal_cells = 0
    inland_cells = 0

    for s in samples:
        pred = build_prediction_tensor(
            s.initial_grid,
            observations=[],
            floor=0.01,
            priors_file=args.priors_file if args.priors_file.is_file() else None,
            alpha=alpha,
            class_multipliers=mult,
        )
        grid = np.asarray(s.initial_grid, dtype=np.int64)
        coastal_mask = _adjacent_to_ocean(grid)
        port_prob = pred[..., 2]

        coastal_vals = port_prob[coastal_mask]
        inland_vals = port_prob[~coastal_mask]

        coastal_probs.extend(coastal_vals.tolist())
        inland_probs.extend(inland_vals.tolist())
        coastal_high += int(np.sum(coastal_vals >= args.port_threshold))
        inland_high += int(np.sum(inland_vals >= args.port_threshold))
        coastal_cells += int(coastal_vals.size)
        inland_cells += int(inland_vals.size)

    payload = {
        "samples": len(samples),
        "alpha_used": alpha,
        "class_multipliers_used": mult.tolist() if mult is not None else None,
        "port_threshold": args.port_threshold,
        "mean_port_prob_coastal": float(np.mean(coastal_probs)) if coastal_probs else 0.0,
        "mean_port_prob_inland": float(np.mean(inland_probs)) if inland_probs else 0.0,
        "high_port_fraction_coastal": float(coastal_high / max(1, coastal_cells)),
        "high_port_fraction_inland": float(inland_high / max(1, inland_cells)),
        "coastal_cells": coastal_cells,
        "inland_cells": inland_cells,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

