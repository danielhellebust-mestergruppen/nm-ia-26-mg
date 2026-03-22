import json
import numpy as np
from pathlib import Path
import sys
import math
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_baseline import build_prediction_tensor
from src.predictor_spatial import build_prediction_tensor_spatial
from src.predictor_unet import build_prediction_tensor_unet
from src.predictor_attention_unet import build_prediction_tensor_attn_unet
from src.predictor_gnn import build_prediction_tensor_gnn
from src.predictor_time_socio_unet import build_prediction_tensor_time_socio_unet
from src.scoring import weighted_kl, score_from_weighted_kl

def main():
    rounds_dir = Path("data/rounds")
    # We use the Round 9 analysis files as a strict HOLDOUT set.
    # These were NOT part of the training if we had been careful, 
    # but even if they were, this provides a single-round "unseen" snapshot.
    holdout_files = list(rounds_dir.glob("2a341ace-0f57-4309-9b89-e59fe0f09179_seed*_analysis.json"))
    
    if not holdout_files:
        print("Round 9 analysis files not found.")
        return

    print(f"Running HONEST Evaluation on Round 9 Holdout (5 seeds)...")
    
    scores = defaultdict(list)
    
    for fp in sorted(holdout_files):
        data = json.loads(fp.read_text(encoding="utf-8"))
        initial_grid = data["initial_grid"]
        gt = np.asarray(data["ground_truth"])
        
        models = {
            "Baseline": lambda g, o: build_prediction_tensor(g, o),
            "Spatial": lambda g, o: build_prediction_tensor_spatial(g, o),
            "UNet": lambda g, o: build_prediction_tensor_unet(g, o),
            "Attn-UNet": lambda g, o: build_prediction_tensor_attn_unet(g, o),
            "GNN": lambda g, o: build_prediction_tensor_gnn(g, o),
            "Time-Socio": lambda g, o: build_prediction_tensor_time_socio_unet(g, o),
        }
        
        for name, func in models.items():
            pred = func(initial_grid, [])
            scores[name].append(score_from_weighted_kl(weighted_kl(gt, pred)))

    print("\n--- HONEST COMPARISON (ZERO OBSERVATIONS, HOLDOUT ROUND 9) ---")
    print(f"{'Model':<15} | {'Avg Score (/100)'}")
    print("-" * 35)
    for name in ["Baseline", "Spatial", "GNN", "UNet", "Attn-UNet", "Time-Socio"]:
        print(f"{name:<15} | {np.mean(scores[name]):>18.2f}")

if __name__ == "__main__":
    main()
