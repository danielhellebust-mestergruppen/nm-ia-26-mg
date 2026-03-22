#!/usr/bin/env python3
import os
import sys
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.api_client import AstarApiClient
from src.env_utils import load_dotenv_file
from src.predictor_baseline import build_prediction_tensor
from src.scoring import kl_divergence, entropy

def main():
    load_dotenv_file(ROOT / ".env")
    token = os.environ.get("AINM_BEARER_TOKEN", "")
    base_url = os.environ.get("AINM_BASE_URL", "https://api.ainm.no/astar-island")
    
    client = AstarApiClient(bearer_token=token, base_url=base_url)
    rounds = client.list_rounds()
    active_round = next((r for r in rounds if r.get("status") == "active"), None)
    
    if not active_round:
        print("No active round found.")
        return
        
    round_id = active_round["id"]
    detail = client.get_round(round_id)
    
    models = ["baseline", "spatial", "convlstm", "unet", "attn_unet"]
    
    print(f"--- Round 9 Model Disagreement Analysis ---")
    
    for seed_idx in range(5):
        grid = detail["initial_states"][seed_idx]["grid"]
        preds = {}
        
        # 1. Generate 0-query predictions for all models
        for mode in models:
            preds[mode] = build_prediction_tensor(grid, [], predictor_mode=mode)
            
        # 2. Calculate Inherent Uncertainty (Entropy) for each model
        print(f"\nSeed {seed_idx}:")
        print(f"  Mean Entropy (Aleatoric Uncertainty):")
        for mode in models:
            mean_ent = np.mean(entropy(preds[mode]))
            print(f"    - {mode.ljust(12)}: {mean_ent:.4f}")
            
        # 3. Calculate Model Disagreement (Epistemic Uncertainty) against our best model (attn_unet)
        print(f"  Mean KL Divergence (Disagreement vs. attn_unet):")
        for mode in models:
            if mode == "attn_unet": continue
            # How much does the other model diverge from what the attn_unet believes is true?
            mean_kl = np.mean(kl_divergence(preds["attn_unet"], preds[mode]))
            print(f"    - {mode.ljust(12)}: {mean_kl:.4f}")

if __name__ == "__main__":
    main()
