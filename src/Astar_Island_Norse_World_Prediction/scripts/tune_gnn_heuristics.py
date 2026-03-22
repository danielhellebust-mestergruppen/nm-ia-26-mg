import argparse
import json
import math
import numpy as np
import sys
from pathlib import Path
from scipy.ndimage import gaussian_filter
import multiprocessing

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_gnn import build_prediction_tensor_gnn
from src.scoring import weighted_kl

def evaluate_params(args):
    temperature, blur_sigma, ocean_penalty, discount_decay, rounds_dir, queries = args
    
    total_kl = 0.0
    round_count = 0
    
    # We load 3 random rounds for fast evaluation
    for fp in list(rounds_dir.glob("*_seed0_analysis.json"))[:5]:
        round_id = fp.stem.split('_')[0]
        
        # Test on seed 0 and 1
        for seed_idx in range(2):
            round_file = rounds_dir / f"{round_id}_seed{seed_idx}_analysis.json"
            if not round_file.exists(): continue
            
            data = json.loads(round_file.read_text())
            initial_grid = np.asarray(data["initial_grid"])
            gt = np.asarray(data["ground_truth"])
            
            h, w = initial_grid.shape
            observations = []
            viewports = []
            
            vp_candidates = []
            for y in range(0, max(1, h - 15 + 1), 15):
                for x in range(0, max(1, w - 15 + 1), 15):
                    vp_candidates.append((x, y))
            for x in range(0, max(1, w - 15 + 1), 15):
                vp_candidates.append((x, max(0, h - 15)))
            for y in range(0, max(1, h - 15 + 1), 15):
                vp_candidates.append((max(0, w - 15), y))
            vp_candidates.append((max(0, w - 15), max(0, h - 15)))
            vp_candidates = list(set(vp_candidates))
            
            discount = np.ones((h, w))
            
            for step in range(queries):
                pred = build_prediction_tensor_gnn(initial_grid.tolist(), observations=observations, floor=0.01)
                
                if temperature != 1.0:
                    logits = np.log(np.clip(pred, 1e-12, 1.0))
                    logits = logits / temperature
                    pred_exp = np.exp(logits)
                    pred = pred_exp / np.sum(pred_exp, axis=-1, keepdims=True)
                    
                ent = -np.sum(np.clip(pred, 1e-12, 1.0) * np.log(np.clip(pred, 1e-12, 1.0)), axis=-1)
                
                utility = ent * discount
                if ocean_penalty != 1.0:
                    utility[initial_grid == 10] *= ocean_penalty
                    
                if blur_sigma > 0:
                    utility = gaussian_filter(utility, sigma=blur_sigma)
                    
                best_score = -1
                next_vp = None
                for (vx, vy) in vp_candidates:
                    if (vx, vy) in viewports: continue
                    score = np.sum(utility[vy:vy+15, vx:vx+15])
                    if score > best_score:
                        best_score = score
                        next_vp = (vx, vy)
                
                if next_vp is None: break
                
                vx, vy = next_vp
                viewports.append((vx, vy))
                
                gt_vp = gt[vy:vy+15, vx:vx+15]
                obs_grid = np.argmax(gt_vp, axis=-1)
                mapping = {0: 11, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5}
                mapped = np.zeros_like(obs_grid)
                for k, v in mapping.items(): mapped[obs_grid == k] = v
                mapped[initial_grid[vy:vy+15, vx:vx+15] == 10] = 10
                
                observations.append({"viewport": {"x": vx, "y": vy, "w": 15, "h": 15}, "grid": mapped.tolist()})
                
                if discount_decay > 0:
                    y_idx, x_idx = np.indices((h, w))
                    cy, cx = vy + 7.5, vx + 7.5
                    dists = np.sqrt((y_idx - cy)**2 + (x_idx - cx)**2)
                    decay_mask = np.clip(dists / (15.0 * discount_decay), 0, 1)
                    discount *= decay_mask
                discount[vy:vy+15, vx:vx+15] = 0.0

            # Final prediction
            pred = build_prediction_tensor_gnn(initial_grid.tolist(), observations=observations, floor=0.01)
            kl = weighted_kl(gt, pred)
            total_kl += kl
            round_count += 1
            
    return (temperature, blur_sigma, ocean_penalty, discount_decay), total_kl / round_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds-dir", default=Path("data/rounds"), type=Path)
    parser.add_argument("--queries", default=8, type=int)
    args = parser.parse_args()

    temperatures = [0.8, 1.0, 1.2]
    blurs = [0.0, 1.0, 2.0]
    ocean_penalties = [0.0, 0.5, 1.0]
    decays = [0.0, 1.0, 2.0]
    
    jobs = []
    for t in temperatures:
        for b in blurs:
            for o in ocean_penalties:
                for d in decays:
                    jobs.append((t, b, o, d, args.rounds_dir, args.queries))
                    
    print(f"Evaluating {len(jobs)} hyperparameter combinations...")
    
    with multiprocessing.Pool(processes=4) as pool:
        results = pool.map(evaluate_params, jobs)
        
    results.sort(key=lambda x: x[1])
    
    print("\\nTop 5 GNN Configurations (lowest KL is best):")
    for params, kl in results[:5]:
        t, b, o, d = params
        score = 100.0 * math.exp(-3.0 * kl)
        print(f"KL: {kl:.4f} (Score: {score:.2f}) -> Temp: {t}, Blur: {b}, Ocean_Penalty: {o}, Discount_Decay: {d}")
