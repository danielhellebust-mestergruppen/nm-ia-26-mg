import subprocess
import json
import sys

models = ["baseline", "spatial", "gnn", "convlstm", "unet", "attn_unet", "time_socio_unet"]
print(f"{'Model':<15} | {'Active Score (/100)':<18} | {'Delta vs 0-Obs'}")
print("-" * 55)

for model in models:
    try:
        cmd = [
            "python", "scripts/offline_evaluator.py",
            "--predictor-mode", model,
            "--policies", "entropy",
            "--query-budget", "8",
            "--floor", "1e-5"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{model:<15} | {'FAILED':<18} | {''}")
            continue
            
        with open("data/reports/offline_evaluator_report.json", "r") as f:
            data = json.load(f)
            
        score = data["summary_by_policy"]["entropy"]["mean_final_score"]
        delta = data["summary_by_policy"]["entropy"]["mean_score_delta"]
        print(f"{model:<15} | {score:>18.2f} | {delta:+.2f}")
    except Exception as e:
        print(f"{model:<15} | {'ERROR':<18} | {''}")
