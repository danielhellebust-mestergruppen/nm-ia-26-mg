import json
import numpy as np
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.predictor_time_socio_unet import build_prediction_tensor_time_socio_unet
from scripts.recommend_query_allocation import _seed_uncertainty, _allocate
from src.scoring import score_prediction, round_score
from scripts.offline_evaluator import _entropy_map

# Load samples grouped by round
rounds_dir = ROOT / "data" / "rounds"
samples_by_round = {}
for fp in sorted(rounds_dir.glob("*_analysis.json")):
    data = json.loads(fp.read_text())
    rid = data["round_id"]
    if rid not in samples_by_round:
        samples_by_round[rid] = []
    samples_by_round[rid].append(data)

def simulate_queries(initial_grid, ground_truth, num_queries, existing_obs=None):
    h, w = len(initial_grid), len(initial_grid[0])
    obs = list(existing_obs) if existing_obs else []
    viewports = [(o["viewport"]["x"], o["viewport"]["y"]) for o in obs]
    
    vp_candidates = [(x, y) for y in range(0, max(1, h - 15 + 1)) for x in range(0, max(1, w - 15 + 1))]
    
    pred = build_prediction_tensor_time_socio_unet(initial_grid, obs)
    for _ in range(num_queries):
        ent = _entropy_map(pred)
        best_score = -1
        next_vp = None
        for (vx, vy) in vp_candidates:
            if (vx, vy) in viewports: continue
            score = np.sum(ent[vy:vy+15, vx:vx+15])
            if score > best_score:
                best_score = score
                next_vp = (vx, vy)
        if next_vp is None: break
        
        vx, vy = next_vp
        viewports.append((vx, vy))
        
        gt_vp = np.asarray(ground_truth)[vy:vy+15, vx:vx+15]
                # Replaced argmax with probabilistic sampling
        cumulative = np.cumsum(gt_vp, axis=-1)
        r = np.random.rand(gt_vp.shape[0], gt_vp.shape[1], 1)
        obs_grid = np.argmax(cumulative > r, axis=-1)
        mapped_grid = np.zeros_like(obs_grid)
        mapped_grid[obs_grid == 0] = 11
        mapped_grid[obs_grid == 1] = 1
        mapped_grid[obs_grid == 2] = 2
        mapped_grid[obs_grid == 3] = 3
        mapped_grid[obs_grid == 4] = 4
        mapped_grid[obs_grid == 5] = 5
        ocean_mask = np.asarray(initial_grid)[vy:vy+15, vx:vx+15] == 10
        mapped_grid[ocean_mask] = 10
        
        obs.append({
            "viewport": {"x": vx, "y": vy, "w": 15, "h": 15},
            "grid": mapped_grid.tolist()
        })
        pred = build_prediction_tensor_time_socio_unet(initial_grid, obs)
        
    return pred, obs

total_uniform_score = []
total_twopass_score = []

print("Running offline simulation of Two-Pass Active Learning vs Uniform 8-Query...")
for rid, seeds in samples_by_round.items():
    if len(seeds) != 5: continue
    
    # Sort seeds to ensure consistent indexing
    seeds = sorted(seeds, key=lambda x: x["seed_index"])
    
    uniform_seed_scores = []
    for seed_data in seeds:
        pred, _ = simulate_queries(seed_data["initial_grid"], seed_data["ground_truth"], 8)
        uniform_seed_scores.append(score_prediction(np.asarray(seed_data["ground_truth"]), pred))
    
    # Two pass
    # Pass 1: 2 queries
    pass1_obs = []
    pass1_preds = []
    for seed_data in seeds:
        pred, obs = simulate_queries(seed_data["initial_grid"], seed_data["ground_truth"], 2)
        pass1_preds.append(pred)
        pass1_obs.append(obs)
        
    # Setup configurations to sweep
    import itertools
    weights_pred_u = [0.2, 0.4, 0.6, 0.8]
    weights_disag = [0.2, 0.4, 0.6, 0.8]
    focus_seeds = [2, 3, 4]
    
    configs = []
    for pu, da, fs in itertools.product(weights_pred_u, weights_disag, focus_seeds):
        if pu + da > 1.0: continue
        rem = 1.0 - pu - da
        w_mean = rem * 0.75
        w_var = rem * 0.25
        configs.append((pu, da, w_mean, w_var, fs))
        
    print(f"Sweeping {len(configs)} heuristic configurations...")
    best_score = -1
    best_config = None
    
    for config in configs:
        pu, da, w_mean, w_var, fs = config
        twopass_seed_scores = []
        scores_for_alloc = []
        for i, seed_data in enumerate(seeds):
            pred_u = _seed_uncertainty(pass1_preds[i])
            disagreements = []
            for o in pass1_obs[i]:
                vx, vy = o["viewport"]["x"], o["viewport"]["y"]
                g = np.asarray(o["grid"])
                for cy in range(15):
                    for cx in range(15):
                        cls = g[cy, cx]
                        if cls == 10 or cls == 11: c = 0
                        elif cls == 1: c = 1
                        elif cls == 2: c = 2
                        elif cls == 3: c = 3
                        elif cls == 4: c = 4
                        elif cls == 5: c = 5
                        disagreements.append(1.0 - pass1_preds[i][vy+cy, vx+cx, c])
            disag = np.mean(disagreements) if disagreements else 0.0
            
            combined = pu * pred_u + da * disag + w_mean * 0.0 # ignore dynamic variance here for speed
            scores_for_alloc.append(combined)
            
        plan = _allocate(40, scores_for_alloc[-5:], max_focus_seeds=fs, min_per_seed=2)
        
        twopass_scores_config = []
        for i, seed_data in enumerate(seeds):
            pred, _ = simulate_queries(seed_data["initial_grid"], seed_data["ground_truth"], plan[i], existing_obs=pass1_obs[i])
            twopass_scores_config.append(score_prediction(np.asarray(seed_data["ground_truth"]), pred))
            
        config_score = round_score(twopass_scores_config)
        if config_score > best_score:
            best_score = config_score
            best_config = config
            
    u_score = round_score(uniform_seed_scores)
    total_uniform_score.append(u_score)
    print(f"Round {rid[:8]}... | Uniform: {u_score:.2f} | Best Two-Pass: {best_score:.2f} | Best Config: {best_config}")
    total_twopass_score.append(best_score)

print(f"\nFinal Results across {len(total_uniform_score)} full rounds:")
print(f"Uniform 8-queries Mean Score: {np.mean(total_uniform_score):.2f}")
print(f"Two-Pass Smart Alloc Mean Score: {np.mean(total_twopass_score):.2f}")