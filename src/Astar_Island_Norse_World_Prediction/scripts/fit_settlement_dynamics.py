#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _fit_linear(features: np.ndarray, target: np.ndarray) -> np.ndarray:
    # Bias + linear terms via least squares.
    x = np.concatenate([np.ones((features.shape[0], 1), dtype=np.float64), features], axis=1)
    coeffs, _, _, _ = np.linalg.lstsq(x, target, rcond=None)
    return coeffs


def main() -> None:
    parser = argparse.ArgumentParser(description="Fit lightweight settlement dynamics coefficients from exported rows.")
    parser.add_argument(
        "--rows-file",
        type=Path,
        default=Path("data/reports/settlement_dynamics_rows.json"),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/reports/settlement_dynamics_model.json"),
    )
    args = parser.parse_args()

    payload = json.loads(args.rows_file.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    if not rows:
        raise RuntimeError(f"No rows found in {args.rows_file}")

    # Features used by influence strength heuristics.
    f = np.asarray(
        [
            [
                float(r.get("population", 0.0)),
                float(r.get("food", 0.0)),
                float(r.get("wealth", 0.0)),
                float(r.get("defense", 0.0)),
                1.0 if bool(r.get("has_port", False)) else 0.0,
            ]
            for r in rows
        ],
        dtype=np.float64,
    )
    y_settlement = np.asarray([float(r.get("target_settlement_prob", 0.0)) for r in rows], dtype=np.float64)
    y_port = np.asarray([float(r.get("target_port_prob", 0.0)) for r in rows], dtype=np.float64)
    y_ruin = np.asarray([float(r.get("target_ruin_prob", 0.0)) for r in rows], dtype=np.float64)

    c_settlement = _fit_linear(f, y_settlement)
    c_port = _fit_linear(f, y_port)
    c_ruin = _fit_linear(f, y_ruin)

    report = {
        "feature_names": ["bias", "population", "food", "wealth", "defense", "has_port"],
        "row_count": int(f.shape[0]),
        "models": {
            "settlement_prob": c_settlement.tolist(),
            "port_prob": c_port.tolist(),
            "ruin_prob": c_ruin.tolist(),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

