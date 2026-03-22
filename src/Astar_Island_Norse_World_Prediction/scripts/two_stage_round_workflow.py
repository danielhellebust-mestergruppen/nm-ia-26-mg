#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file


def _pick_active_round(rounds: list[dict]) -> dict:
    active = [r for r in rounds if r.get("status") == "active"]
    if not active:
        raise RuntimeError("No active round found")
    return sorted(active, key=lambda x: x.get("round_number", 0))[-1]


def _run(cmd: list[str]) -> int:
    print(">", " ".join(shlex.quote(x) for x in cmd))
    return int(subprocess.run(cmd, cwd=ROOT).returncode)


def main() -> None:
    load_dotenv_file(ROOT / ".env")
    parser = argparse.ArgumentParser(
        description=(
            "Two-stage round workflow: optional probe queries, then adaptive per-seed allocation, "
            "then a final submit command."
        )
    )
    parser.add_argument("--token", default="")
    parser.add_argument("--base-url", default="")
    parser.add_argument("--workspace", type=Path, default=ROOT / "data")
    parser.add_argument("--round-id", default="")
    parser.add_argument("--probe-queries-per-seed", type=int, default=2)
    parser.add_argument("--predictor-mode", choices=["baseline", "spatial", "spatial_unet", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "gnn", "time_socio_unet", "time_socio_deep_unet", "meta_ensemble"], default="meta_ensemble")
    parser.add_argument("--query-policy", choices=["grid", "random", "entropy", "grid_then_entropy"], default="grid")
    parser.add_argument("--grid-warmup-queries", type=int, default=2)
    parser.add_argument("--overlap-discount", type=float, default=0.5)
    parser.add_argument("--entropy-mode", choices=["plain", "unobserved_only"], default="plain")
    parser.add_argument("--entropy-temp", type=float, default=0.95)
    parser.add_argument("--historical-overlap-penalty", type=float, default=0.0)
    parser.add_argument("--predict-time-guard-ms", type=float, default=300.0)
    parser.add_argument("--floor", type=float, default=1e-5)
    parser.add_argument("--cross-seed-observations", action="store_true")
    parser.add_argument("--distance-backend", choices=["python", "scipy"], default="python")
    parser.add_argument("--execute-probe", action="store_true", help="Run probe stage now (consumes query budget).")
    parser.add_argument("--auto-submit", action="store_true", help="Run final submit command automatically.")
    parser.add_argument("--save-visuals", action="store_true")
    parser.add_argument("--max-focus-seeds", type=int, default=2)
    parser.add_argument(
        "--skip-observation-features",
        action="store_true",
        help="Use faster allocation (prediction uncertainty only).",
    )
    parser.add_argument("--out", type=Path, default=ROOT / "data" / "reports" / "two_stage_workflow_plan.json")
    args = parser.parse_args()

    token = args.token or os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = args.base_url or os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    if not token:
        raise RuntimeError("Missing bearer token. Set AINM_BEARER_TOKEN or pass --token.")

    client = AstarApiClient(bearer_token=token, base_url=base_url)
    if args.round_id:
        round_id = args.round_id
    else:
        round_id = str(_pick_active_round(client.list_rounds())["id"])

    common = [
        "--predictor-mode",
        args.predictor_mode,
        "--query-policy",
        args.query_policy,
        "--grid-warmup-queries",
        str(max(0, int(args.grid_warmup_queries))),
        "--overlap-discount",
        str(args.overlap_discount),
        "--entropy-mode",
        args.entropy_mode,
        "--entropy-temp",
        str(args.entropy_temp),
        "--historical-overlap-penalty",
        str(max(0.0, args.historical_overlap_penalty)),
        "--predict-time-guard-ms",
        str(max(0.0, args.predict_time_guard_ms)),
        "--floor",
        str(args.floor),
        "--distance-backend",
        args.distance_backend,
    ]
    if args.cross_seed_observations:
        common.append("--cross-seed-observations")
    if args.save_visuals:
        common.append("--save-visuals")

    stage_a_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_active_round.py"),
        "--queries-per-seed",
        str(max(0, int(args.probe_queries_per_seed))),
        "--workspace",
        str(args.workspace),
        *common,
    ]
    alloc_cmd = [
        sys.executable,
        str(ROOT / "scripts" / "recommend_query_allocation.py"),
        "--round-id",
        round_id,
        "--workspace",
        str(args.workspace),
        "--max-focus-seeds",
        str(max(1, int(args.max_focus_seeds))),
    ]
    if args.skip_observation_features:
        alloc_cmd.append("--skip-observation-features")
    stage_b_cmd_prefix = [
        sys.executable,
        str(ROOT / "scripts" / "run_active_round.py"),
        "--workspace",
        str(args.workspace),
        "--submit",
        *common,
    ]

    stage_a_exit = None
    alloc_exit = None
    stage_b_exit = None
    recommended_seed_query_plan_arg = None

    if args.execute_probe:
        stage_a_exit = _run(stage_a_cmd)
        if stage_a_exit != 0:
            raise SystemExit(stage_a_exit)

    alloc_exit = _run(alloc_cmd)
    if alloc_exit != 0:
        raise SystemExit(alloc_exit)
    alloc_report = args.workspace / "reports" / "query_allocation_recommendation.json"
    alloc_payload = json.loads(alloc_report.read_text(encoding="utf-8"))
    recommended_seed_query_plan_arg = str(alloc_payload.get("recommended_seed_query_plan_arg", ""))
    if not recommended_seed_query_plan_arg:
        raise RuntimeError("Allocation script did not produce recommended_seed_query_plan_arg.")

    stage_b_cmd = [
        *stage_b_cmd_prefix,
        "--seed-query-plan",
        recommended_seed_query_plan_arg,
    ]
    if args.auto_submit:
        stage_b_exit = _run(stage_b_cmd)
        if stage_b_exit != 0:
            raise SystemExit(stage_b_exit)

    payload = {
        "round_id": round_id,
        "execute_probe": bool(args.execute_probe),
        "auto_submit": bool(args.auto_submit),
        "stage_a_exit_code": stage_a_exit,
        "allocation_exit_code": alloc_exit,
        "stage_b_exit_code": stage_b_exit,
        "recommended_seed_query_plan_arg": recommended_seed_query_plan_arg,
        "stage_a_command": " ".join(shlex.quote(x) for x in stage_a_cmd),
        "allocation_command": " ".join(shlex.quote(x) for x in alloc_cmd),
        "stage_b_command": " ".join(shlex.quote(x) for x in stage_b_cmd),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()

