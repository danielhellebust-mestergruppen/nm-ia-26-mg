#!/usr/bin/env python3
"""
K-fold CV over latest rounds: train with holdout, evaluate via offline_evaluator.

Run from `astar_island/` (or any cwd; script cd's to repo root).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

# Repo root (parent of scripts/)
ROOT = Path(__file__).resolve().parents[1]
REPORTS_CV = ROOT / "data" / "reports" / "cv_kfold"

ALL_TRAINABLE = [
    ("attn_unet", "scripts/train_attention_unet_predictor.py", "holdout"),
    ("socio_unet", "scripts/train_socio_unet_predictor.py", "exclude"),
    ("time_socio_unet", "scripts/train_time_socio_unet_predictor.py", "exclude"),
    ("time_socio_deep_unet", "scripts/train_time_socio_deep_unet_predictor.py", "exclude"),
    ("gnn", "scripts/train_gnn_predictor.py", "holdout"),
]
DEFAULT_EVAL = ["attn_unet", "socio_unet", "time_socio_unet", "time_socio_deep_unet", "gnn", "ensemble"]
KNOWN_MODELS = {m[0] for m in ALL_TRAINABLE} | {"ensemble"}


def _train_cmd(
    python_exe: str,
    script_rel: str,
    mode: str,
    holdout_id: str,
    epochs: int,
    batch_size: int,
    lr: str,
) -> list[str]:
    base = [
        python_exe,
        script_rel,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--lr",
        lr,
    ]
    if mode == "holdout":
        return base + ["--holdout-round", holdout_id]
    return base + ["--exclude-rounds", holdout_id]


def _parse_models(s: str) -> list[str]:
    out = [x.strip() for x in s.split(",") if x.strip()]
    bad = [x for x in out if x not in KNOWN_MODELS]
    if bad:
        raise SystemExit(f"Unknown model(s): {bad}. Known: {sorted(KNOWN_MODELS)}")
    return out


def _extract_holdout_score(report: dict, holdout_id: str, query_budget: int) -> float:
    holdout_scores = []
    for row in report.get("results", []):
        if (
            row.get("policy") == "entropy"
            and row.get("round_id") == holdout_id
            and row.get("query_budget") == query_budget
        ):
            holdout_scores.append(float(row["final_score"]))
    return float(np.mean(holdout_scores)) if holdout_scores else 0.0


def main() -> None:
    os.chdir(ROOT)

    parser = argparse.ArgumentParser(description="K-fold CV for Astar Island predictors.")
    parser.add_argument("--rounds-dir", type=Path, default=ROOT / "data" / "rounds")
    parser.add_argument(
        "--folds",
        type=int,
        default=3,
        help="Number of latest rounds to use as holdouts (default: 3).",
    )
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=str, default="1e-3")
    parser.add_argument(
        "--query-budget",
        type=int,
        default=None,
        help="Active-query budget for offline eval (default: 8, or 4 with --fast-cv).",
    )
    parser.add_argument(
        "--limit-samples",
        type=int,
        default=None,
        help="Cap seeds per round in evaluator (0 = all). Default: 0, or 8 with --fast-cv.",
    )
    parser.add_argument(
        "--models",
        type=str,
        default=",".join(DEFAULT_EVAL),
        help="Comma-separated predictors to evaluate (subset of attn_unet,socio_unet,time_socio_deep_unet,ensemble).",
    )
    parser.add_argument(
        "--skip-ensemble",
        action="store_true",
        help="Do not evaluate ensemble even if listed in --models.",
    )
    parser.add_argument(
        "--fast-cv",
        action="store_true",
        help="Faster iteration: disable TTA in predictors, lower default query budget and sample cap unless overridden.",
    )
    parser.add_argument(
        "--continue-on-train-error",
        action="store_true",
        help="If set, continue after a failed training (default: fail fast and exit).",
    )
    args = parser.parse_args()

    query_budget = args.query_budget if args.query_budget is not None else (4 if args.fast_cv else 8)
    limit_samples = args.limit_samples if args.limit_samples is not None else (8 if args.fast_cv else 0)

    eval_models = _parse_models(args.models)
    if args.skip_ensemble:
        eval_models = [m for m in eval_models if m != "ensemble"]

    trainable_models = [m for m in ALL_TRAINABLE if m[0] in eval_models]

    round_files = list(args.rounds_dir.glob("*_seed0_analysis.json"))
    rounds: list[tuple[int, str]] = []
    for fp in round_files:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            rounds.append((int(data.get("round_number", 0)), fp.stem.split("_")[0]))
        except Exception:
            continue
    rounds.sort()
    nfold = max(1, min(args.folds, len(rounds)))
    test_rounds = [r[1] for r in rounds[-nfold:]]

    if not test_rounds:
        print("No rounds found for CV.", file=sys.stderr)
        sys.exit(1)

    print(
        f"Running {nfold}-fold CV. Holdouts: {test_rounds} | query_budget={query_budget} "
        f"| limit_samples={limit_samples} | fast_cv={args.fast_cv}",
        flush=True,
    )

    cv_scores: dict[str, list[float]] = {m: [] for m in eval_models}
    timing_train: dict[str, list[float]] = {m[0]: [] for m in trainable_models}
    timing_eval: dict[str, list[float]] = {m: [] for m in eval_models}

    eval_env = os.environ.copy()
    if args.fast_cv:
        eval_env["ASTAR_PREDICTOR_DISABLE_TTA"] = "1"

    python_exe = sys.executable
    REPORTS_CV.mkdir(parents=True, exist_ok=True)

    for holdout_id in test_rounds:
        print(f"\n========== FOLD: Holdout Round {holdout_id} ==========", flush=True)
        t_fold_start = time.perf_counter()

        for model_name, train_script, arg_mode in trainable_models:
            print(f"-> Training {model_name} (excluding {holdout_id})...", flush=True)
            cmd = _train_cmd(
                python_exe,
                train_script,
                arg_mode,
                holdout_id,
                args.epochs,
                args.batch_size,
                args.lr,
            )
            t0 = time.perf_counter()
            res = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            dt = time.perf_counter() - t0
            timing_train[model_name].append(dt)
            print(f"   Training wall time: {dt:.1f}s", flush=True)

            if res.returncode != 0:
                print(f"   [Error training {model_name}: {res.stderr}]", flush=True)
                if not args.continue_on_train_error:
                    sys.exit(1)

        for model_name in eval_models:
            print(f"-> Evaluating {model_name} (entropy, {query_budget} queries)...", flush=True)
            out_report = REPORTS_CV / f"fold_{holdout_id}_{model_name}.json"
            cmd = [
                python_exe,
                "scripts/offline_evaluator.py",
                "--predictor-mode",
                model_name,
                "--policies",
                "entropy",
                "--query-budget",
                str(query_budget),
                "--floor",
                "1e-5",
                "--target-round",
                holdout_id,
                "--out",
                str(out_report),
            ]
            if limit_samples > 0:
                cmd.extend(["--limit-samples", str(limit_samples)])

            t0 = time.perf_counter()
            res = subprocess.run(
                cmd,
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                env=eval_env,
            )
            dt = time.perf_counter() - t0
            timing_eval[model_name].append(dt)
            print(f"   Evaluation wall time: {dt:.1f}s", flush=True)

            if res.returncode != 0:
                print(f"   [Error evaluating {model_name}: {res.stderr}]", flush=True)
                cv_scores[model_name].append(0.0)
                continue

            try:
                report = json.loads(out_report.read_text(encoding="utf-8"))
                mean_score = _extract_holdout_score(report, holdout_id, query_budget)
                cv_scores[model_name].append(mean_score)
                print(f"   Holdout score: {mean_score:.2f}", flush=True)
            except Exception as e:
                print(f"   [Error parsing report for {model_name}: {e}]", flush=True)
                cv_scores[model_name].append(0.0)

        print(f"   Fold total wall time: {time.perf_counter() - t_fold_start:.1f}s", flush=True)

    print("\n================ FINAL K-FOLD CV RESULTS ================")
    for model_name in cv_scores:
        scores = cv_scores[model_name]
        te = timing_eval.get(model_name, [])
        eval_sum = sum(te) if te else 0.0
        print(
            f"{model_name:<22} | mean score: {np.mean(scores):.2f} | folds: {[round(s, 2) for s in scores]} "
            f"| eval time sum: {eval_sum:.1f}s",
        )
    if trainable_models:
        print("\n--- Training time per model (sum over folds) ---")
        for model_name, _, _ in trainable_models:
            tt = timing_train.get(model_name, [])
            print(f"{model_name:<22} | train time sum: {sum(tt):.1f}s")

    if args.fast_cv:
        print(
            "\nNote: --fast-cv uses no TTA and smaller default budget/samples. "
            "Re-run without --fast-cv (and default query-budget/limit-samples) for deployment-grade scores.",
            flush=True,
        )


if __name__ == "__main__":
    main()
