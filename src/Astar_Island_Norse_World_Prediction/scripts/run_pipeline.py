#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(script_name: str, extra_args: list[str]) -> int:
    script_path = SCRIPTS / script_name
    if not script_path.is_file():
        print(f"error: missing script {script_path}")
        return 2
    cmd = [sys.executable, str(script_path), *extra_args]
    print(">", " ".join(shlex.quote(x) for x in cmd))
    proc = subprocess.run(cmd, cwd=ROOT)
    return int(proc.returncode)


def _forward(parser: argparse.ArgumentParser) -> list[str]:
    args, extra = parser.parse_known_args()
    setattr(args, "_forward", extra)
    return args


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Unified orchestrator for Astar Island workflows. "
            "All existing scripts remain supported; this is a convenience wrapper."
        )
    )
    subparsers = parser.add_subparsers(dest="group", required=True)

    data = subparsers.add_parser("data", help="Backfill and row-building workflows")
    data_sub = data.add_subparsers(dest="task", required=True)
    data_sub.add_parser("backfill-replays", help="Run backfill_replays.py")
    data_sub.add_parser("backfill-analyses", help="Run backfill_completed_rounds.py")
    data_sub.add_parser("backfill-all", help="Run replays then analyses")
    data_sub.add_parser("build-replay-rows", help="Run build_replay_training_rows.py")

    calibrate = subparsers.add_parser("calibrate", help="Calibration/training workflows")
    cal_sub = calibrate.add_subparsers(dest="task", required=True)
    cal_sub.add_parser("spatial", help="Run calibrate_spatial_from_replays.py")
    cal_sub.add_parser("dynamics", help="Run fit_settlement_dynamics.py")
    cal_sub.add_parser("baseline-priors", help="Run tune_baseline_priors.py")
    cal_sub.add_parser("blend", help="Run tune_blend_weights.py")

    tune = subparsers.add_parser("tune", help="Tuning and sweeps")
    tune_sub = tune.add_subparsers(dest="task", required=True)
    tune_sub.add_parser("spatial", help="Run tune_spatial_params.py")
    tune_sub.add_parser("policy-sweep", help="Run sweep_round8_policy.py")
    tune_sub.add_parser("hybrid-knobs", help="Run sweep_hybrid_spatial_knobs.py")
    tune_sub.add_parser("freeze", help="Run freeze_best_known_config.py")

    eval_parser = subparsers.add_parser("eval", help="Offline evaluation and gates")
    eval_sub = eval_parser.add_subparsers(dest="task", required=True)
    eval_sub.add_parser("offline", help="Run offline_evaluator.py")
    eval_sub.add_parser("ablation", help="Run ablate_predictor_components.py")
    eval_sub.add_parser("gates", help="Run check_promotion_gates.py")
    eval_sub.add_parser("profile", help="Run profile_offline_evaluator.py")
    eval_sub.add_parser("compare-priors", help="Run compare_priors.py")
    eval_sub.add_parser("manual", help="Run evaluate_manual_calibration.py")
    eval_sub.add_parser("postmortem", help="Run analyze_round_postmortem.py")
    eval_sub.add_parser("holdout", help="Run eval_holdout_predictors.py")

    deploy = subparsers.add_parser("deploy", help="Active round and completed-round evaluation")
    dep_sub = deploy.add_subparsers(dest="task", required=True)
    dep_sub.add_parser("active", help="Run run_active_round.py")
    dep_sub.add_parser("eval-round", help="Run eval_completed_round.py")
    dep_sub.add_parser("freeze", help="Run freeze_best_known_config.py")
    dep_sub.add_parser("two-stage", help="Run two_stage_round_workflow.py")

    status = subparsers.add_parser("status", help="Status and diagnostics")
    status_sub = status.add_subparsers(dest="task", required=True)
    status_sub.add_parser("rounds", help="Run rounds_status_summary.py")
    status_sub.add_parser("active", help="Run check_active_round.py")
    status_sub.add_parser("scripts-audit", help="Run audit_script_inventory.py")
    status_sub.add_parser("recommend-allocation", help="Run recommend_query_allocation.py")
    status_sub.add_parser("port-diagnostic", help="Run diagnose_port_coastal.py")

    args = _forward(parser)
    extra = getattr(args, "_forward", [])

    group_task = (args.group, args.task)
    dispatch = {
        ("data", "backfill-replays"): ["backfill_replays.py"],
        ("data", "backfill-analyses"): ["backfill_completed_rounds.py"],
        ("data", "build-replay-rows"): ["build_replay_training_rows.py"],
        ("data", "backfill-all"): ["backfill_replays.py", "backfill_completed_rounds.py"],
        ("calibrate", "spatial"): ["calibrate_spatial_from_replays.py"],
        ("calibrate", "dynamics"): ["fit_settlement_dynamics.py"],
        ("calibrate", "baseline-priors"): ["tune_baseline_priors.py"],
        ("calibrate", "blend"): ["tune_blend_weights.py"],
        ("tune", "spatial"): ["tune_spatial_params.py"],
        ("tune", "policy-sweep"): ["sweep_round8_policy.py"],
        ("tune", "hybrid-knobs"): ["sweep_hybrid_spatial_knobs.py"],
        ("tune", "freeze"): ["freeze_best_known_config.py"],
        ("eval", "offline"): ["offline_evaluator.py"],
        ("eval", "ablation"): ["ablate_predictor_components.py"],
        ("eval", "gates"): ["check_promotion_gates.py"],
        ("eval", "profile"): ["profile_offline_evaluator.py"],
        ("eval", "compare-priors"): ["compare_priors.py"],
        ("eval", "manual"): ["evaluate_manual_calibration.py"],
        ("eval", "postmortem"): ["analyze_round_postmortem.py"],
        ("eval", "holdout"): ["eval_holdout_predictors.py"],
        ("deploy", "active"): ["run_active_round.py"],
        ("deploy", "eval-round"): ["eval_completed_round.py"],
        ("deploy", "freeze"): ["freeze_best_known_config.py"],
        ("deploy", "two-stage"): ["two_stage_round_workflow.py"],
        ("status", "rounds"): ["rounds_status_summary.py"],
        ("status", "active"): ["check_active_round.py"],
        ("status", "scripts-audit"): ["audit_script_inventory.py"],
        ("status", "recommend-allocation"): ["recommend_query_allocation.py"],
        ("status", "port-diagnostic"): ["diagnose_port_coastal.py"],
    }
    scripts = dispatch.get(group_task)
    if not scripts:
        print(f"error: unsupported command group/task: {group_task}")
        raise SystemExit(2)

    code = 0
    for i, script_name in enumerate(scripts):
        this_extra = extra if i == len(scripts) - 1 else []
        code = _run(script_name, this_extra)
        if code != 0:
            break
    raise SystemExit(code)


if __name__ == "__main__":
    main()

