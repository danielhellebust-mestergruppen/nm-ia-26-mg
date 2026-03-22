import json
import subprocess

models = ["attn_unet", "time_socio_unet"]
budgets = "0,2,4,8,16"

print(f"{'Model':<18} | {'Budget':<8} | {'Score (/100)':<10} | {'Delta vs 0-Obs'}")
print("-" * 55)

for model in models:
    res = subprocess.run([
        "python", "scripts/offline_evaluator.py",
        "--predictor-mode", model,
        "--policies", "entropy",
        "--query-budgets", budgets,
        "--floor", "1e-5"
    ], capture_output=True, text=True)
    
    if res.returncode != 0:
        print(f"Error running {model}: {res.stderr}")
        continue
        
    with open("data/reports/offline_evaluator_report.json", "r") as f:
        data = json.load(f)
        
    summary = data.get("summary_by_policy", {})
    for b in [0, 2, 4, 8, 16]:
        key = f"entropy (budget: {b})"
        if key in summary:
            score = summary[key]["mean_final_score"]
            delta = summary[key]["mean_score_delta"]
            print(f"{model:<18} | {b:<8} | {score:>10.2f} | {delta:+.2f}")
    print("-" * 55)
