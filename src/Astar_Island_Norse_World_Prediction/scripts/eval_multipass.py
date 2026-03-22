import json
import numpy as np
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from src.predictor_attention_unet import build_prediction_tensor_attn_unet
from scripts.recommend_query_allocation import _seed_uncertainty, _allocate
from src.scoring import score_prediction, round_score
from scripts.offline_evaluator import _entropy_map

rounds_dir = ROOT / "data" / "rounds"
samples_by_round = {}
for fp in sorted(rounds_dir.glob("*_analysis.json")):
    data = json.loads(fp.read_text())
    rid = data["round_id"]
    if rid not in samples_by_round:
        samples_by_round[rid] = []
    samples_by_round[rid].append(data)

def simulate_queries(initial_grid, ground_truth, num_queries, existing_obs=None, policy="entropy"):
    h, w = len(initial_grid), len(initial_grid[0])
    obs = list(existing_obs) if existing_obs else []
    viewports = [(o["viewport"]["x"], o["viewport"]["y"]) for o in obs]
    
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
    
    pred = build_prediction_tensor_attn_unet(initial_grid, obs)
    for _ in range(num_queries):
        if policy == "entropy":
            utility = _entropy_map(pred)
        elif policy == "volatility":
            # Focus on active civilization classes: Settlement, Port, Ruin
            utility = np.sum(pred[..., 1:4], axis=-1)
        elif policy == "hybrid":
            ent = _entropy_map(pred)
            vol = np.sum(pred[..., 1:4], axis=-1)
            utility = 0.5 * ent + 0.5 * vol
        elif policy == "random":
            utility = np.random.rand(h, w)
        else:
            utility = _entropy_map(pred)
            
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
        pred = build_prediction_tensor_attn_unet(initial_grid, obs)
        
    return pred, obs

def evaluate_multipass(pass_plan, policy1="entropy", policy2="entropy"):
    total_score = []
    
    for rid, seeds in samples_by_round.items():
        if len(seeds) != 5: continue
        seeds = sorted(seeds, key=lambda x: x["seed_index"])
        
        current_obs = [[] for _ in range(5)]
        current_preds = [None for _ in range(5)]
        budget_remaining = 50
        
        for pass_idx, alloc_type in enumerate(pass_plan):
            current_policy = policy1 if pass_idx == 0 else policy2
            if isinstance(alloc_type, int):
                # Allocate a fixed number of queries per seed uniformly
                per_seed = alloc_type
                for i, seed_data in enumerate(seeds):
                    pred, obs = simulate_queries(seed_data["initial_grid"], seed_data["ground_truth"], per_seed, existing_obs=current_obs[i], policy=current_policy)
                    current_preds[i] = pred
                    current_obs[i] = obs
                budget_remaining -= per_seed * 5
            elif alloc_type == "smart":
                # Smart allocate remaining budget
                scores_for_alloc = []
                for i, seed_data in enumerate(seeds):
                    pred_u = _seed_uncertainty(current_preds[i])
                    disagreements = []
                    for o in current_obs[i]:
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
                                disagreements.append(1.0 - current_preds[i][vy+cy, cx+vx, c])
                    disag = np.mean(disagreements) if disagreements else 0.0
                    combined = 0.40 * pred_u + 0.40 * disag
                    scores_for_alloc.append(combined)
                
                plan = _allocate(budget_remaining, scores_for_alloc, max_focus_seeds=3, min_per_seed=1)
                
                for i, seed_data in enumerate(seeds):
                    pred, obs = simulate_queries(seed_data["initial_grid"], seed_data["ground_truth"], plan[i], existing_obs=current_obs[i], policy=current_policy)
                    current_preds[i] = pred
                    current_obs[i] = obs
                budget_remaining = 0
                
        round_scores = []
        for i, seed_data in enumerate(seeds):
            round_scores.append(score_prediction(np.asarray(seed_data["ground_truth"]), current_preds[i]))
        total_score.append(round_score(round_scores))
        
    return np.mean(total_score)

strategies = {
    "Two-Pass (1 recon) [Grid -> Entropy]": ([1, "smart"], "grid", "entropy"),
    "Two-Pass (1 recon) [Random -> Entropy]": ([1, "smart"], "random", "entropy"),
    "Two-Pass (1 recon) [Volatility -> Entropy]": ([1, "smart"], "volatility", "entropy"),
    "Two-Pass (1 recon) [Hybrid -> Entropy]": ([1, "smart"], "hybrid", "entropy"),
}

for name, (plan, p1, p2) in strategies.items():
    print(f"Evaluating {name}... ", end="", flush=True)
    score = evaluate_multipass(plan, policy1=p1, policy2=p2)
    print(f"Score: {score:.2f}")