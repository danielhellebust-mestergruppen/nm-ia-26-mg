#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _matrix_from_report(report: dict) -> np.ndarray:
    names = ["empty", "settlement", "port", "ruin", "forest", "mountain"]
    expected = report["patterns"]["expected_transition_probs"]
    mat = np.zeros((6, 6), dtype=np.float64)
    for i, src in enumerate(names):
        for j, dst in enumerate(names):
            mat[i, j] = float(expected[src][dst])
    # safety normalize
    mat = np.maximum(mat, 0.0)
    row_sums = mat.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums <= 0, 1.0, row_sums)
    return mat / row_sums


def main() -> None:
    parser = argparse.ArgumentParser(description="Create tuned priors from backfill report.")
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "reports"
        / "completed_rounds_pattern_report.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "reports" / "tuned_priors.json",
    )
    parser.add_argument(
        "--smoothing",
        type=float,
        default=0.0,
        help="Blend towards uniform to reduce overfitting, e.g. 0.05",
    )
    args = parser.parse_args()

    if not args.report.is_file():
        raise RuntimeError(f"Report not found: {args.report}")

    report = json.loads(args.report.read_text(encoding="utf-8"))
    if not report.get("patterns"):
        raise RuntimeError("No patterns present in report")

    mat = _matrix_from_report(report)
    if args.smoothing > 0:
        alpha = float(args.smoothing)
        uni = np.full_like(mat, 1.0 / mat.shape[1])
        mat = (1.0 - alpha) * mat + alpha * uni
        mat = mat / mat.sum(axis=1, keepdims=True)

    payload = {
        "source_report": str(args.report),
        "samples": int(report["patterns"].get("samples", 0)),
        "smoothing": float(args.smoothing),
        "transition_matrix": mat.tolist(),
        "class_order": ["empty", "settlement", "port", "ruin", "forest", "mountain"],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"written": str(args.out), "samples": payload["samples"]}, indent=2))


if __name__ == "__main__":
    main()

