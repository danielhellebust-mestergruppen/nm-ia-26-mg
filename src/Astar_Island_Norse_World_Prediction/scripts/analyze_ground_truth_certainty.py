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
    
    if not sorted_round_nums:
        print("No ground truth data found.")
        return
        
    last_3_nums = sorted_round_nums[-3:]
    older_nums = sorted_round_nums[:-3]
    
    def analyze_group(nums, name):
        all_gts = []
        for rn in nums:
            all_gts.extend(rounds[rn])
            
        if not all_gts:
            print(f"No data for group {name}")
            return
            
        gts = np.stack(all_gts) # shape (N, H, W, C)
        
        # Certainty metrics
        # 1. Mean max probability per cell
        max_probs = np.max(gts, axis=-1)
        mean_max_prob = np.mean(max_probs)
        
        # 2. Mean entropy per cell
        eps = 1e-12
        p = np.clip(gts, eps, 1.0)
        # Assuming 6 classes
        entropy = -np.sum(p * np.log(p), axis=-1) / np.log(6.0) 
        mean_entropy = np.mean(entropy)
        
        # 3. Fraction of highly certain cells
        high_cert_frac = np.mean(max_probs > 0.95)
        
        # 4. Fraction of highly uncertain cells
        low_cert_frac = np.mean(max_probs < 0.5)

        print(f"--- Group: {name} (Rounds {nums}) ---")
        print(f"Total Maps: {len(all_gts)}")
        print(f"Mean Max Probability: {mean_max_prob:.4f} (Higher is more certain)")
        print(f"Mean Normalized Entropy: {mean_entropy:.4f} (Lower is more certain)")
        print(f"Fraction of cells highly certain (>0.95): {high_cert_frac:.4f}")
        print(f"Fraction of cells highly uncertain (<0.50): {low_cert_frac:.4f}\\n")
        
    analyze_group(older_nums, "Older Rounds")
    analyze_group(last_3_nums, "Last 3 Rounds")

if __name__ == "__main__":
    main()
