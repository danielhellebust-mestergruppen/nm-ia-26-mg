#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file


def _safe_mean(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _safe_std(values: list[float]) -> float | None:
    if len(values) < 2:
        return 0.0 if values else None
    return float(statistics.pstdev(values))


def _extract_round_payload(round_item: dict[str, Any]) -> dict[str, Any]:
    seed_scores = [float(x) for x in (round_item.get("seed_scores") or [])]
    return {
        "round_id": str(round_item.get("id")),
        "round_number": int(round_item.get("round_number", 0)),
        "status": str(round_item.get("status", "")),
        "round_score": float(round_item["round_score"]) if round_item.get("round_score") is not None else None,
        "seed_scores": seed_scores,
        "seed_score_mean": _safe_mean(seed_scores),
        "seed_score_std": _safe_std(seed_scores),
        "seeds_submitted": int(round_item.get("seeds_submitted", 0)),
        "queries_used": int(round_item.get("queries_used", 0)),
        "queries_max": int(round_item.get("queries_max", 0)),
        "rank": round_item.get("rank"),
        "total_teams": round_item.get("total_teams"),
    }


def _load_run_summary(workspace: Path, round_id: str) -> dict[str, Any] | None:
    fp = workspace / "reports" / f"{round_id}_run_summary.json"
    if not fp.is_file():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def _diff_section(base: dict[str, Any], cur: dict[str, Any]) -> dict[str, Any]:
    base_score = base.get("round_score")
    cur_score = cur.get("round_score")
    score_delta = None
    if isinstance(base_score, (int, float)) and isinstance(cur_score, (int, float)):
        score_delta = float(cur_score - base_score)

    base_rank = base.get("rank")
    cur_rank = cur.get("rank")
    rank_delta = None
    if isinstance(base_rank, int) and isinstance(cur_rank, int):
        rank_delta = int(cur_rank - base_rank)

    seed_deltas: list[float] = []
    b_seed = base.get("seed_scores") or []
    c_seed = cur.get("seed_scores") or []
    for i in range(min(len(b_seed), len(c_seed))):
        seed_deltas.append(float(c_seed[i] - b_seed[i]))

    return {
        "score_delta_round7_minus_round6": score_delta,
        "rank_delta_round7_minus_round6": rank_delta,
        "seed_score_deltas_round7_minus_round6": seed_deltas,
        "mean_seed_delta": _safe_mean(seed_deltas),
        "std_seed_delta": _safe_std(seed_deltas),
        "queries_used_delta_round7_minus_round6": int(cur.get("queries_used", 0) - base.get("queries_used", 0)),
    }


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(description="Official-first round postmortem (round 6 vs round 7 by default).")
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--baseline-round", type=int, default=6)
    parser.add_argument("--target-round", type=int, default=7)
    parser.add_argument("--workspace", type=Path, default=ROOT / "data")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "reports" / "round6_vs_round7_postmortem.json",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")

    report: dict[str, Any] = {
        "baseline_round_number": args.baseline_round,
        "target_round_number": args.target_round,
        "source": "local_fallback",
    }
    baseline_payload = None
    target_payload = None

    if token:
        try:
            client = AstarApiClient(bearer_token=token, base_url=base_url)
            my_rounds = client.my_rounds()
            by_num = {int(r.get("round_number", -1)): r for r in my_rounds}
            b = by_num.get(args.baseline_round)
            t = by_num.get(args.target_round)
            if b and t:
                baseline_payload = _extract_round_payload(b)
                target_payload = _extract_round_payload(t)
                report["source"] = "official_api_my_rounds"
        except Exception as exc:  # noqa: BLE001
            report["api_error"] = str(exc)

    # Fallback from cached rounds status when API is unavailable.
    if baseline_payload is None or target_payload is None:
        status_fp = args.workspace / "reports" / "rounds_status_summary.json"
        if status_fp.is_file():
            payload = json.loads(status_fp.read_text(encoding="utf-8"))
            by_num_local = {int(r.get("round_number", -1)): r for r in payload.get("rounds", [])}
            b = by_num_local.get(args.baseline_round)
            t = by_num_local.get(args.target_round)
            if b:
                baseline_payload = {
                    "round_id": str(b.get("round_id")),
                    "round_number": int(b.get("round_number", 0)),
                    "status": "completed_or_cached",
                    "round_score": b.get("avg_score_if_available"),
                    "seed_scores": [],
                    "seed_score_mean": b.get("avg_score_if_available"),
                    "seed_score_std": None,
                    "seeds_submitted": int(b.get("seeds_submitted", 0)),
                    "queries_used": None,
                    "queries_max": None,
                    "rank": None,
                    "total_teams": None,
                }
            if t:
                target_payload = {
                    "round_id": str(t.get("round_id")),
                    "round_number": int(t.get("round_number", 0)),
                    "status": "completed_or_cached",
                    "round_score": t.get("avg_score_if_available"),
                    "seed_scores": [],
                    "seed_score_mean": t.get("avg_score_if_available"),
                    "seed_score_std": None,
                    "seeds_submitted": int(t.get("seeds_submitted", 0)),
                    "queries_used": None,
                    "queries_max": None,
                    "rank": None,
                    "total_teams": None,
                }

    report["baseline_round"] = baseline_payload
    report["target_round"] = target_payload

    if baseline_payload and target_payload:
        report["comparison"] = _diff_section(baseline_payload, target_payload)
        b_run = _load_run_summary(args.workspace, str(baseline_payload["round_id"]))
        t_run = _load_run_summary(args.workspace, str(target_payload["round_id"]))
        report["baseline_run_summary"] = b_run
        report["target_run_summary"] = t_run
    else:
        report["comparison"] = None
        report["diagnostic"] = (
            "Missing one or both rounds in API/local cache. "
            "Use backfill scripts or replay diagnostics until official stats are available."
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

