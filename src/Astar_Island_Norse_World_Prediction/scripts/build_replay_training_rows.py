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
    if not isinstance(obj, list) or not obj:
        return False
    first = obj[0]
    return isinstance(first, list) and len(first) > 0


def _extract_grid(frame: dict[str, Any]) -> list[list[int]] | None:
    for k in ("grid", "layout", "state", "map"):
        v = frame.get(k)
        if _is_grid(v):
            return v
    for k in ("world", "snapshot", "year_state"):
        v = frame.get(k)
        if isinstance(v, dict):
            for kk in ("grid", "layout", "state", "map"):
                vv = v.get(kk)
                if _is_grid(vv):
                    return vv
    return None


def _extract_settlements(frame: dict[str, Any]) -> list[dict[str, Any]]:
    s = frame.get("settlements")
    return s if isinstance(s, list) else []


def _extract_frames(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[Any] = []
    for k in ("years", "states", "frames", "layouts", "replay"):
        v = payload.get(k)
        if isinstance(v, list):
            candidates.append(v)
    if isinstance(payload.get("data"), dict):
        for k in ("years", "states", "frames", "layouts"):
            v = payload["data"].get(k)
            if isinstance(v, list):
                candidates.append(v)
    if isinstance(payload, list):
        candidates.append(payload)

    best: list[dict[str, Any]] = []
    for cand in candidates:
        frames: list[dict[str, Any]] = []
        for i, item in enumerate(cand):
            if isinstance(item, dict):
                f = dict(item)
                if "year" not in f:
                    f["year"] = i
                frames.append(f)
            elif _is_grid(item):
                frames.append({"year": i, "grid": item, "settlements": []})
        if len(frames) > len(best):
            best = frames
    return best


def _parse_round_seed(path: Path) -> tuple[str, int] | None:
    m = re.match(r"^(.+)_seed(\d+)\.json$", path.name)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def _coastal_mask(grid: np.ndarray) -> np.ndarray:
    h, w = grid.shape
    out = np.zeros((h, w), dtype=np.int8)
    for y in range(h):
        for x in range(w):
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= ny < h and 0 <= nx < w and int(grid[ny, nx]) == 10:
                    out[y, x] = 1
                    break
    return out


def _build_transition_rows(
    round_id: str,
    seed_index: int,
    frames: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    transition_rows: list[dict[str, Any]] = []
    settlement_rows: list[dict[str, Any]] = []
    for t in range(len(frames) - 1):
        g0_raw = _extract_grid(frames[t])
        g1_raw = _extract_grid(frames[t + 1])
        if g0_raw is None or g1_raw is None:
            continue
        g0 = np.asarray(g0_raw, dtype=np.int64)
        g1 = np.asarray(g1_raw, dtype=np.int64)
        if g0.shape != g1.shape:
            continue
        h, w = g0.shape
        c0 = np.vectorize(grid_value_to_class_index)(g0)
        c1 = np.vectorize(grid_value_to_class_index)(g1)
        coastal = _coastal_mask(g0)
        for y in range(h):
            for x in range(w):
                transition_rows.append(
                    {
                        "round_id": round_id,
                        "seed_index": seed_index,
                        "year": int(frames[t].get("year", t)),
                        "x": x,
                        "y": y,
                        "class_t": int(c0[y, x]),
                        "class_t1": int(c1[y, x]),
                        "is_coastal_t": int(coastal[y, x]),
                    }
                )
        settlements = _extract_settlements(frames[t])
        for s in settlements:
            x = int(s.get("x", -1))
            y = int(s.get("y", -1))
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            y1, y2 = max(0, y - 2), min(h, y + 3)
            x1, x2 = max(0, x - 2), min(w, x + 3)
            local = c1[y1:y2, x1:x2]
            settlement_rows.append(
                {
                    "round_id": round_id,
                    "seed_index": seed_index,
                    "year": int(frames[t].get("year", t)),
                    "x": x,
                    "y": y,
                    "population": float(s.get("population", 0.0) or 0.0),
                    "food": float(s.get("food", 0.0) or 0.0),
                    "wealth": float(s.get("wealth", 0.0) or 0.0),
                    "defense": float(s.get("defense", 0.0) or 0.0),
                    "has_port": bool(s.get("has_port", False)),
                    "target_settlement_prob_t1": float(np.mean(local == 1)),
                    "target_port_prob_t1": float(np.mean(local == 2)),
                    "target_ruin_prob_t1": float(np.mean(local == 3)),
                    "target_forest_prob_t1": float(np.mean(local == 4)),
                }
            )
    return transition_rows, settlement_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build replay-based training rows from cached replay payloads.")
    parser.add_argument("--replays-dir", type=Path, default=Path("data/replays"))
    parser.add_argument("--out", type=Path, default=Path("data/reports/replay_training_rows.json"))
    args = parser.parse_args()

    files = sorted(args.replays_dir.glob("*_seed*.json"))
    if not files:
        raise RuntimeError(f"No replay files found in {args.replays_dir}")

    all_transition_rows: list[dict[str, Any]] = []
    all_settlement_rows: list[dict[str, Any]] = []
    used_files = 0
    skipped_files = 0
    for fp in files:
        rs = _parse_round_seed(fp)
        if rs is None:
            skipped_files += 1
            continue
        round_id, seed_index = rs
        data = json.loads(fp.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            skipped_files += 1
            continue
        frames = _extract_frames(data)
        if len(frames) < 2:
            skipped_files += 1
            continue
        tr, sr = _build_transition_rows(round_id, seed_index, frames)
        all_transition_rows.extend(tr)
        all_settlement_rows.extend(sr)
        used_files += 1

    report = {
        "meta": {
            "replay_files_scanned": len(files),
            "replay_files_used": used_files,
            "replay_files_skipped": skipped_files,
            "transition_rows": len(all_transition_rows),
            "settlement_rows": len(all_settlement_rows),
        },
        "transition_rows": all_transition_rows,
        "settlement_rows": all_settlement_rows,
    }
    save_json(args.out, report)
    print(json.dumps(report["meta"], indent=2))


if __name__ == "__main__":
    main()

