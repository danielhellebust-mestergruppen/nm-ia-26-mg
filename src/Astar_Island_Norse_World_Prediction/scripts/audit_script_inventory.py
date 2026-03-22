#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
README = ROOT / "README.md"


CATEGORY_MAP = {
    "data_collection": [
        "backfill_replays.py",
        "backfill_completed_rounds.py",
        "build_replay_training_rows.py",
    ],
    "calibration_training": [
        "calibrate_spatial_from_replays.py",
        "fit_settlement_dynamics.py",
        "tune_baseline_priors.py",
        "tune_blend_weights.py",
    ],
    "tuning_sweeps": [
        "tune_spatial_params.py",
        "sweep_round8_policy.py",
        "freeze_best_known_config.py",
    ],
    "evaluation_and_gates": [
        "offline_evaluator.py",
        "ablate_predictor_components.py",
        "check_promotion_gates.py",
        "evaluate_manual_calibration.py",
        "compare_priors.py",
        "profile_offline_evaluator.py",
        "analyze_round_postmortem.py",
    ],
    "deployment": [
        "run_active_round.py",
        "eval_completed_round.py",
    ],
    "status_and_diagnostics": [
        "check_active_round.py",
        "rounds_status_summary.py",
        "recommend_query_allocation.py",
        "diagnose_port_coastal.py",
        "audit_script_inventory.py",
    ],
    "orchestration": [
        "run_pipeline.py",
    ],
}


def _recommendation(script_name: str) -> dict[str, str]:
    if script_name in {
        "evaluate_manual_calibration.py",
        "diagnose_port_coastal.py",
        "compare_priors.py",
    }:
        return {
            "status": "candidate_deprecate",
            "reason": (
                "Specialized diagnostic with narrow usage. Keep for now, but deprecate if not used in two rounds."
            ),
        }
    if script_name in {
        "run_pipeline.py",
    }:
        return {"status": "new_primary_entrypoint", "reason": "Use as grouped command surface."}
    return {"status": "keep", "reason": "Active in core training/eval/deploy workflow."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit scripts for overlap and deprecation candidates.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "reports" / "script_inventory_audit.json",
    )
    args = parser.parse_args()

    readme_text = README.read_text(encoding="utf-8") if README.is_file() else ""
    script_files = sorted([p.name for p in SCRIPTS_DIR.glob("*.py")])
    by_script = {}
    for name in script_files:
        cat = next((c for c, items in CATEGORY_MAP.items() if name in items), "unclassified")
        by_script[name] = {
            "category": cat,
            "mentioned_in_readme": (name in readme_text),
            **_recommendation(name),
        }

    payload = {
        "total_scripts": len(script_files),
        "categories": CATEGORY_MAP,
        "scripts": by_script,
        "deprecation_candidates": [
            name for name, row in by_script.items() if row.get("status") == "candidate_deprecate"
        ],
        "notes": [
            "No script is removed automatically.",
            "Deprecation candidates should be archived only after two consecutive rounds of non-use.",
            "Prefer run_pipeline.py for grouped workflows while preserving direct script CLIs.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"saved_report={args.out}")


if __name__ == "__main__":
    main()

