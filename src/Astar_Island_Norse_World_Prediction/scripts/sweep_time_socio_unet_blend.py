#!/usr/bin/env python3
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main():
    blend_weights = [0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09, 0.1]
    results = []

    print("Sweeping TIME_SOCIO_BLEND for time_socio_unet predictor...")

    for weight in blend_weights:
        print(f"\\n--- Evaluating with TIME_SOCIO_BLEND = {weight} ---")
        env = os.environ.copy()
        env["TIME_SOCIO_BLEND"] = str(weight)
        
        # Run the offline evaluator
        cmd = [
            "python", str(ROOT / "scripts/offline_evaluator.py"),
            "--predictor-mode", "time_socio_unet",
            "--out", str(ROOT / f"data/reports/eval_blend_{weight}.json"),
            "--limit-samples", "15" # Speed up evaluation
        ]
        
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error evaluating weight {weight}:")
            print(result.stderr)
            continue
            
        try:
            # We parse the saved report
            report_path = ROOT / f"data/reports/eval_blend_{weight}.json"
            data = json.loads(report_path.read_text())
            random_policy_score = data.get("summary_by_policy", {}).get("random", {}).get("mean_final_score", 0)
            entropy_policy_score = data.get("summary_by_policy", {}).get("entropy", {}).get("mean_final_score", 0)
            results.append({
                "weight": weight,
                "random_score": random_policy_score,
                "entropy_score": entropy_policy_score
            })
            print(f"Score (Random): {random_policy_score:.4f} | Score (Entropy): {entropy_policy_score:.4f}")
        except Exception as e:
            print(f"Failed to parse report for weight {weight}: {e}")

    # Print summary
    print("\\n=== SWEEP SUMMARY ===")
    results.sort(key=lambda x: x["entropy_score"], reverse=True)
    for r in results:
        print(f"Weight: {r['weight']:<4} | Random Score: {r['random_score']:.4f} | Entropy Score: {r['entropy_score']:.4f}")

    if results:
        best = results[0]
        print(f"\\nBest Blend Weight (by Entropy Score): {best['weight']} with score {best['entropy_score']:.4f}")
        
if __name__ == "__main__":
    main()
