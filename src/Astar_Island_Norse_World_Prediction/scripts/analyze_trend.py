#!/usr/bin/env python3
import json
from pathlib import Path
import numpy as np

def main():
    rounds_dir = Path("data/rounds")
    round_files = list(rounds_dir.glob("*_analysis.json"))
    
    round_data = []
    for fp in round_files:
        try:
            data = json.loads(fp.read_text())
            if "ground_truth" in data and "round_number" in data:
                round_data.append(data)
        except Exception as e:
            pass
            
    # Group by round number
    rounds = {}
    for d in round_data:
        rn = d["round_number"]
        if rn not in rounds:
            rounds[rn] = []
        rounds[rn].append(np.asarray(d["ground_truth"], dtype=np.float32))
        
    sorted_round_nums = sorted(list(rounds.keys()))
    
    print(f"{'Round':<6} | {'Maps':<5} | {'Mean Max Prob':<15} | {'Mean Entropy':<15} | {'Highly Certain (>0.95)':<20}")
    print("-" * 75)
    
    for rn in sorted_round_nums:
        gts = np.stack(rounds[rn])
        max_probs = np.max(gts, axis=-1)
        mean_max_prob = np.mean(max_probs)
        
        eps = 1e-12
        p = np.clip(gts, eps, 1.0)
        entropy = -np.sum(p * np.log(p), axis=-1) / np.log(6.0) 
        mean_entropy = np.mean(entropy)
        
        high_cert_frac = np.mean(max_probs > 0.95)
        
        print(f"{rn:<6} | {len(rounds[rn]):<5} | {mean_max_prob:<15.4f} | {mean_entropy:<15.4f} | {high_cert_frac:<20.4f}")

if __name__ == "__main__":
    main()
