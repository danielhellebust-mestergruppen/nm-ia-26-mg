#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file
from src.offline_harness import load_json, save_json
from src.types import NUM_CLASSES, NUM_SEEDS, grid_value_to_class_index


def _is_round_completed(round_obj: dict[str, Any]) -> bool:
    return round_obj.get("status") in {"completed", "scoring"}


def _safe_get_round(client: AstarApiClient, round_id: str) -> dict[str, Any] | None:
    try:
        return client.get_round(round_id)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: failed get_round({round_id}): {exc}")
        return None


def _safe_get_analysis(
    client: AstarApiClient, round_id: str, seed_index: int
) -> dict[str, Any] | None:
    try:
        return client.analysis(round_id, seed_index)
    except Exception as exc:  # noqa: BLE001
        print(f"warn: failed analysis({round_id}, seed={seed_index}): {exc}")
        return None


def _border_is_ocean(grid: np.ndarray) -> bool:
    # Ocean internal code is 10
    top = np.all(grid[0, :] == 10)
    bottom = np.all(grid[-1, :] == 10)
    left = np.all(grid[:, 0] == 10)
    right = np.all(grid[:, -1] == 10)
    return bool(top and bottom and left and right)


def _collect_pattern_stats(round_seed_items: list[dict[str, Any]]) -> dict[str, Any]:
    transition_mass = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.float64)
    transition_argmax = np.zeros((NUM_CLASSES, NUM_CLASSES), dtype=np.int64)
    initial_class_counts = np.zeros((NUM_CLASSES,), dtype=np.int64)
    border_total = 0
    border_full_ocean = 0

    for item in round_seed_items:
        initial_grid = np.asarray(item["initial_grid"], dtype=np.int64)
        ground_truth = np.asarray(item["ground_truth"], dtype=np.float64)

        h, w = initial_grid.shape
        border_total += 1
        if _border_is_ocean(initial_grid):
            border_full_ocean += 1

        mapped_init = np.vectorize(grid_value_to_class_index)(initial_grid)
        gt_argmax = np.argmax(ground_truth, axis=-1)

        for y in range(h):
            for x in range(w):
                init_cls = int(mapped_init[y, x])
                initial_class_counts[init_cls] += 1
                transition_argmax[init_cls, int(gt_argmax[y, x])] += 1
                transition_mass[init_cls] += ground_truth[y, x]

    def row_norm(mat: np.ndarray) -> np.ndarray:
        denom = mat.sum(axis=1, keepdims=True)
        denom = np.where(denom <= 0, 1.0, denom)
        return mat / denom

    transition_mass_p = row_norm(transition_mass)
    transition_argmax_p = row_norm(transition_argmax.astype(np.float64))

    class_names = ["empty", "settlement", "port", "ruin", "forest", "mountain"]
    report = {
        "samples": len(round_seed_items),
        "border_full_ocean_ratio": float(border_full_ocean / max(1, border_total)),
        "initial_class_counts": {class_names[i]: int(initial_class_counts[i]) for i in range(NUM_CLASSES)},
        "expected_transition_probs": {
            class_names[i]: {class_names[j]: float(transition_mass_p[i, j]) for j in range(NUM_CLASSES)}
            for i in range(NUM_CLASSES)
        },
        "argmax_transition_probs": {
            class_names[i]: {class_names[j]: float(transition_argmax_p[i, j]) for j in range(NUM_CLASSES)}
            for i in range(NUM_CLASSES)
        },
        "focus_metrics": {
            "settlement_to_ruin_expected": float(transition_mass_p[1, 3]),
            "ruin_to_settlement_expected": float(transition_mass_p[3, 1]),
            "empty_to_settlement_expected": float(transition_mass_p[0, 1]),
            "empty_to_ruin_expected": float(transition_mass_p[0, 3]),
        },
    }
    return report


def _build_settlement_dynamics_rows(
    workspace: Path, round_seed_items: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_key: dict[tuple[str, int], dict[str, Any]] = {}
    for item in round_seed_items:
        by_key[(str(item["round_id"]), int(item["seed_index"]))] = item

    rows: list[dict[str, Any]] = []
    obs_dir = workspace / "observations"
    obs_files = sorted(obs_dir.glob("*_seed*_*.json"))
    used_files = 0
    skipped_missing_gt = 0
    for fp in obs_files:
        name = fp.name
        try:
            # expected: <round_id>_seed<seed_idx>_<ts>_<i>.json
            if "_seed" not in name:
                continue
            round_id = name.split("_seed")[0]
            rest = name.split("_seed", 1)[1]
            seed_text = rest.split("_", 1)[0]
            seed_index = int(seed_text)
        except Exception:
            continue
        key = (round_id, seed_index)
        if key not in by_key:
            skipped_missing_gt += 1
            continue
        item = by_key[key]
        gt = np.asarray(item["ground_truth"], dtype=np.float64)
        h, w, _ = gt.shape
        try:
            obs = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        settlements = obs.get("settlements") or []
        if not settlements:
            continue
        used_files += 1
        for s in settlements:
            x = int(s.get("x", -1))
            y = int(s.get("y", -1))
            if x < 0 or y < 0 or x >= w or y >= h:
                continue
            y1 = max(0, y - 2)
            y2 = min(h, y + 3)
            x1 = max(0, x - 2)
            x2 = min(w, x + 3)
            local = gt[y1:y2, x1:x2]
            local_mean = np.mean(local, axis=(0, 1))
            row = {
                "round_id": round_id,
                "seed_index": seed_index,
                "x": x,
                "y": y,
                "population": float(s.get("population", 0.0) or 0.0),
                "food": float(s.get("food", 0.0) or 0.0),
                "wealth": float(s.get("wealth", 0.0) or 0.0),
                "defense": float(s.get("defense", 0.0) or 0.0),
                "has_port": bool(s.get("has_port", False)),
                "alive": bool(s.get("alive", True)),
                # proxy targets for settlement dynamics and nearby influence outcomes
                "target_settlement_prob": float(local_mean[1]),
                "target_port_prob": float(local_mean[2]),
                "target_ruin_prob": float(local_mean[3]),
                "target_forest_prob": float(local_mean[4]),
            }
            rows.append(row)

    meta = {
        "observation_files_scanned": len(obs_files),
        "observation_files_used": used_files,
        "rows": len(rows),
        "skipped_missing_ground_truth": skipped_missing_gt,
    }
    return rows, meta


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Download completed-round analyses and compute pattern report."
    )
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=ROOT / "data",
    )
    parser.add_argument("--limit-rounds", type=int, default=0, help="0 means all completed rounds")
    parser.add_argument(
        "--emit-dynamics-rows",
        action="store_true",
        help="Also export settlement dynamics training rows if local observations exist",
    )
    args = parser.parse_args()
    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    if not token:
        raise RuntimeError(
            "Missing bearer token. Set AINM_BEARER_TOKEN in shell or astar_island/.env or pass --token."
        )

    client = AstarApiClient(bearer_token=token, base_url=base_url)
    rounds = client.my_rounds()
    completed = [r for r in rounds if _is_round_completed(r)]
    completed = sorted(completed, key=lambda x: x.get("round_number", 0))
    if args.limit_rounds > 0:
        completed = completed[-args.limit_rounds :]

    cache_items: list[dict[str, Any]] = []
    for round_obj in completed:
        round_id = str(round_obj["id"])
        detail = _safe_get_round(client, round_id)
        if not detail:
            continue
        initial_states = detail.get("initial_states", [])
        if not initial_states:
            continue
        seeds_count = min(int(detail.get("seeds_count", NUM_SEEDS)), len(initial_states), NUM_SEEDS)

        for seed_index in range(seeds_count):
            analysis = _safe_get_analysis(client, round_id, seed_index)
            if not analysis:
                continue
            item = {
                "round_id": round_id,
                "round_number": int(round_obj.get("round_number", 0)),
                "seed_index": seed_index,
                "initial_grid": initial_states[seed_index]["grid"],
                "ground_truth": analysis["ground_truth"],
                "prediction": analysis.get("prediction"),
                "score": analysis.get("score"),
            }
            cache_items.append(item)
            out_file = args.workspace / "rounds" / f"{round_id}_seed{seed_index}_analysis.json"
            save_json(out_file, item)

    report = {
        "completed_rounds_considered": len(completed),
        "cached_round_seed_items": len(cache_items),
        "round_ids": [str(r["id"]) for r in completed],
    }
    if cache_items:
        report["patterns"] = _collect_pattern_stats(cache_items)
    else:
        report["patterns"] = {}

    if args.emit_dynamics_rows and cache_items:
        rows, meta = _build_settlement_dynamics_rows(args.workspace, cache_items)
        save_json(args.workspace / "reports" / "settlement_dynamics_rows.json", {"meta": meta, "rows": rows})
        report["settlement_dynamics_rows_meta"] = meta
    report_path = args.workspace / "reports" / "completed_rounds_pattern_report.json"
    save_json(report_path, report)
    print(json.dumps(report, indent=2))

    # Optional compact CSV-style print for quick inspection
    if report.get("patterns"):
        fm = report["patterns"]["focus_metrics"]
        print(
            "focus_metrics:",
            f"settlement->ruin={fm['settlement_to_ruin_expected']:.4f}",
            f"ruin->settlement={fm['ruin_to_settlement_expected']:.4f}",
            f"empty->settlement={fm['empty_to_settlement_expected']:.4f}",
            f"empty->ruin={fm['empty_to_ruin_expected']:.4f}",
        )


if __name__ == "__main__":
    main()

