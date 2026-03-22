#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    deep_weights = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    results = []

    print("Sweeping ENSEMBLE_W_DEEP for ensemble predictor (Time-Socio + Time-Socio Deep)...")

    for weight in deep_weights:
        print(f"\\n--- Evaluating with ENSEMBLE_W_DEEP = {weight} ---")
        env = os.environ.copy()
        env["ENSEMBLE_W_DEEP"] = str(weight)
        
        cmd = [
            "python", str(ROOT / "scripts/offline_evaluator.py"),
            "--predictor-mode", "ensemble",
            "--out", str(ROOT / f"data/reports/eval_ensemble_{weight}.json"),
            "--limit-samples", "15" # Speed up evaluation
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error evaluating weight {weight}:")
            print(result.stderr)
            continue
            
        try:
            report_path = ROOT / f"data/reports/eval_ensemble_{weight}.json"
            data = json.loads(report_path.read_text())
            random_policy_score = data.get("summary_by_policy", {}).get("random (budget: 8)", {}).get("mean_final_score", 0)
            results.append({
                "weight": weight,
                "random_score": random_policy_score
            })
            print(f"Score (Random Policy): {random_policy_score:.4f}")
        except Exception as e:
            print(f"Failed to parse report for weight {weight}: {e}")

    print("\\n=== SWEEP SUMMARY ===")
    results.sort(key=lambda x: x["random_score"], reverse=True)
    for r in results:
        print(f"Deep UNet Weight: {r['weight']:<4} | Score: {r['random_score']:.4f}")

    if results:
        best = results[0]
        print(f"\\nBest Deep UNet Weight: {best['weight']} with score {best['random_score']:.4f}")
        
if __name__ == "__main__":
    main()
