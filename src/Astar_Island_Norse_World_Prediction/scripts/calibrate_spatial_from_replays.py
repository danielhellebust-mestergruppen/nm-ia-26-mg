#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.offline_harness import save_json
from src.types import grid_value_to_class_index


def _is_grid(obj: Any) -> bool:
    return isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], list)


def _extract_frames(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cands: list[list[Any]] = []
    for k in ("years", "states", "frames", "layouts", "replay"):
        v = payload.get(k)
        if isinstance(v, list):
            cands.append(v)
    if isinstance(payload.get("data"), dict):
        for k in ("years", "states", "frames", "layouts"):
            v = payload["data"].get(k)
            if isinstance(v, list):
                cands.append(v)
    best: list[dict[str, Any]] = []
    for c in cands:
        out: list[dict[str, Any]] = []
        for i, item in enumerate(c):
            if isinstance(item, dict):
                d = dict(item)
                d.setdefault("year", i)
                out.append(d)
            elif _is_grid(item):
                out.append({"year": i, "grid": item, "settlements": []})
        if len(out) > len(best):
            best = out
    return best


def _extract_grid(frame: dict[str, Any]) -> list[list[int]] | None:
    for k in ("grid", "layout", "state", "map"):
        v = frame.get(k)
        if _is_grid(v):
            return v
    if isinstance(frame.get("world"), dict):
        for k in ("grid", "layout", "state", "map"):
            v = frame["world"].get(k)
            if _is_grid(v):
                return v
    return None


def _parse_round_seed(name: str) -> tuple[str, int] | None:
    m = re.match(r"^(.+)_seed(\d+)\.json$", name)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate spatial priors from cached replay trajectories.")
    parser.add_argument("--replays-dir", type=Path, default=Path("data/replays"))
    parser.add_argument("--out", type=Path, default=Path("data/reports/spatial_priors_from_replay.json"))
    args = parser.parse_args()

    files = sorted(args.replays_dir.glob("*_seed*.json"))
    if not files:
        raise RuntimeError(f"No replay files found in {args.replays_dir}")

    trans = np.zeros((6, 6), dtype=np.float64)
    settlement_count = 0
    port_count = 0
    settlement_to_ruin = 0.0
    settlement_to_settlement = 0.0
    empty_to_settlement = 0.0
    empty_to_ruin = 0.0
    total_pairs = 0

    for fp in files:
        if _parse_round_seed(fp.name) is None:
            continue
        payload = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            continue
        frames = _extract_frames(payload)
        if len(frames) < 2:
            continue
        for i in range(len(frames) - 1):
            g0_raw = _extract_grid(frames[i])
            g1_raw = _extract_grid(frames[i + 1])
            if g0_raw is None or g1_raw is None:
                continue
            g0 = np.asarray(g0_raw, dtype=np.int64)
            g1 = np.asarray(g1_raw, dtype=np.int64)
            if g0.shape != g1.shape:
                continue
            c0 = np.vectorize(grid_value_to_class_index)(g0)
            c1 = np.vectorize(grid_value_to_class_index)(g1)
            for a in range(6):
                mask = c0 == a
                if np.any(mask):
                    binc = np.bincount(c1[mask].ravel(), minlength=6)
                    trans[a] += binc
            total_pairs += int(c0.size)
            settlement_count += int(np.sum(c0 == 1))
            port_count += int(np.sum(c0 == 2))

    trans_rows = trans / np.maximum(1.0, trans.sum(axis=1, keepdims=True))
    settlement_to_ruin = float(trans_rows[1, 3])
    settlement_to_settlement = float(trans_rows[1, 1])
    empty_to_settlement = float(trans_rows[0, 1])
    empty_to_ruin = float(trans_rows[0, 3])

    # Heuristic calibration from replay transition dynamics.
    influence_settlement_weight = float(np.clip(0.25 + 3.0 * empty_to_settlement, 0.25, 0.9))
    influence_ruin_weight = float(np.clip(0.05 + 4.0 * settlement_to_ruin, 0.05, 0.5))
    influence_port_weight = float(np.clip(0.30 + 2.0 * float(trans_rows[0, 2]), 0.2, 0.8))
    influence_forest_weight = float(np.clip(0.10 + 1.0 * float(trans_rows[0, 4]), 0.05, 0.4))
    local_blend_max = float(np.clip(0.10 + 0.8 * settlement_to_settlement, 0.12, 0.30))
    local_count_threshold = int(np.clip(4 + round(8.0 * settlement_to_ruin), 4, 8))

    out = {
        "source": "replay_calibration",
        "meta": {
            "replay_files": len(files),
            "total_cell_pairs": total_pairs,
            "settlement_cells": settlement_count,
            "port_cells": port_count,
        },
        "transition_probs": trans_rows.tolist(),
        "calibrated_spatial_priors": {
            "local_count_threshold": local_count_threshold,
            "local_blend_max": local_blend_max,
            "influence_settlement_weight": influence_settlement_weight,
            "influence_port_weight": influence_port_weight,
            "influence_ruin_weight": influence_ruin_weight,
            "influence_forest_weight": influence_forest_weight,
            "alpha_count_weight": 0.22,
            "alpha_entropy_weight": 0.10,
            "alpha_distance_weight": 0.12,
            "smoothing_weight": 0.12,
            "smoothing_passes": 1,
            "influence_tau": 4.5,
            "distance_backend": "python",
        },
    }
    save_json(args.out, out["calibrated_spatial_priors"])
    save_json(args.out.with_name("spatial_priors_from_replay_meta.json"), out)
    print(json.dumps(out["calibrated_spatial_priors"], indent=2))


if __name__ == "__main__":
    main()

