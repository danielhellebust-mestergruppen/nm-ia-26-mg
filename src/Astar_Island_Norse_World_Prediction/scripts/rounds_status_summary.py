#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import csv


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize cached round/seed analysis status.")
    parser.add_argument(
        "--rounds-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "rounds",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "reports" / "rounds_status_summary.json",
    )
    parser.add_argument(
        "--csv-out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "reports" / "rounds_status_summary.csv",
    )
    args = parser.parse_args()

    by_round: dict[str, dict] = defaultdict(
        lambda: {
            "round_number": 0,
            "seeds_total": 0,
            "seeds_submitted": 0,
            "seed_indices": [],
            "scores": [],
        }
    )

    for fp in sorted(args.rounds_dir.glob("*_analysis.json")):
        data = json.loads(fp.read_text(encoding="utf-8"))
        rid = str(data["round_id"])
        item = by_round[rid]
        item["round_number"] = int(data.get("round_number", 0))
        item["seeds_total"] += 1
        item["seed_indices"].append(int(data.get("seed_index", -1)))
        if data.get("prediction") is not None:
            item["seeds_submitted"] += 1
        score = data.get("score")
        if score is not None:
            item["scores"].append(float(score))

    rows = []
    for rid, item in by_round.items():
        seeds_total = int(item["seeds_total"])
        submitted = int(item["seeds_submitted"])
        missing = seeds_total - submitted
        round_scores = item["scores"]
        row = {
            "round_id": rid,
            "round_number": int(item["round_number"]),
            "seeds_cached": seeds_total,
            "seeds_submitted": submitted,
            "seeds_missing_prediction": missing,
            "avg_score_if_available": _mean(round_scores),
            "min_score_if_available": min(round_scores) if round_scores else None,
            "max_score_if_available": max(round_scores) if round_scores else None,
        }
        rows.append(row)

    rows = sorted(rows, key=lambda x: x["round_number"])
    payload = {"rounds": rows}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    with args.csv_out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "round_number",
                "round_id",
                "seeds_cached",
                "seeds_submitted",
                "seeds_missing_prediction",
                "avg_score_if_available",
                "min_score_if_available",
                "max_score_if_available",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print("round_number  submitted/cached  missing  avg_score")
    for r in rows:
        avg_text = f"{r['avg_score_if_available']:.4f}" if r["avg_score_if_available"] else "-"
        print(
            f"{r['round_number']:>11}  "
            f"{r['seeds_submitted']}/{r['seeds_cached']:<13}  "
            f"{r['seeds_missing_prediction']:<7}  "
            f"{avg_text}"
        )
    print(f"\nWrote {args.json_out}")
    print(f"Wrote {args.csv_out}")


if __name__ == "__main__":
    main()

