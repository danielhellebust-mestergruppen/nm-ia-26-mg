import json
import subprocess
from pathlib import Path
import numpy as np

def main():
    rounds_dir = Path("data/rounds")
    round_files = list(rounds_dir.glob("*_seed0_analysis.json"))
    rounds = []
    for fp in round_files:
        data = json.loads(fp.read_text())
        rounds.append((data.get("round_number", 0), fp.stem.split('_')[0]))
    rounds.sort()
    
    # Take the last 3 rounds for a 3-fold CV (Rounds 7, 8, 9)
    test_rounds = [r[1] for r in rounds[-3:]]
    print(f"Running 3-Fold CV on latest rounds. Holdouts: {test_rounds}")
    
    models = [
        ("attn_unet", "scripts/train_attention_unet_predictor.py"),
        ("time_socio_unet", "scripts/train_time_socio_unet_predictor.py")
    ]
    
    cv_scores = {m: [] for m, _ in models}
    
    for holdout_id in test_rounds:
        print(f"\n========== FOLD: Holdout Round {holdout_id} ==========")
        for model_name, train_script in models:
            print(f"-> Training {model_name} (Excluding {holdout_id})...")
            # 100 epochs gives a solid convergence without waiting an hour
            subprocess.run([
                "python", train_script,
                "--epochs", "100",
                "--batch-size", "16",
                "--lr", "1e-3",
                "--holdout-round", holdout_id
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            print(f"-> Evaluating {model_name} on active querying (8 queries)...")
            subprocess.run([
                "python", "scripts/offline_evaluator.py",
                "--predictor-mode", model_name,
                "--policies", "entropy",
                "--query-budget", "8",
                "--floor", "1e-5"
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Read the report and extract the score for ONLY the holdout round
            with open("data/reports/offline_evaluator_report.json", "r") as f:
                report = json.load(f)
                
            holdout_scores = []
            for row in report["results"]:
                if row["policy"] == "entropy" and row["round_id"] == holdout_id:
                    holdout_scores.append(row["final_score"])
                    
            mean_score = np.mean(holdout_scores) if holdout_scores else 0.0
            cv_scores[model_name].append(mean_score)
            print(f"   Holdout Score: {mean_score:.2f}")

    print("\n================ FINAL K-FOLD CV RESULTS (TRUE LIVE PERFORMANCE) ================")
    for model_name in cv_scores:
        scores = cv_scores[model_name]
        print(f"{model_name:<15} | Mean Score: {np.mean(scores):.2f} | Folds: {[round(s, 2) for s in scores]}")

if __name__ == "__main__":
    main()
