import re

# --- Patch predictor_baseline.py ---
with open("src/predictor_baseline.py", "r") as f:
    content = f.read()

# Update floor default
content = content.replace("floor: float = 0.01,", "floor: float = 1e-5,")

# Add hard constraints
old_return = """            # Blend per-cell prior with observed global frequencies.
            pred[y, x] = a_eff * base + (1.0 - a_eff) * observed_priors

    pred = apply_probability_floor(pred, floor=floor)
    return pred"""

new_return = """            # Blend per-cell prior with observed global frequencies.
            pred[y, x] = a_eff * base + (1.0 - a_eff) * observed_priors

    ocean_mask = (grid == 10)
    coastal_mask = np.zeros_like(ocean_mask)
    for y in range(h):
        for x in range(w):
            if _adjacent_to_ocean(grid, y, x):
                coastal_mask[y, x] = True
                
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    pred = apply_probability_floor(pred, floor=floor)
    return pred"""

content = content.replace(old_return, new_return)

with open("src/predictor_baseline.py", "w") as f:
    f.write(content)

# --- Patch predictor_spatial.py ---
with open("src/predictor_spatial.py", "r") as f:
    content = f.read()

# Update floor defaults
content = content.replace("floor: float = 0.01", "floor: float = 1e-5")

old_return2 = """    pred = alpha_map[..., None] * pred + (1.0 - alpha_map[..., None]) * base
    pred = _safe_row_norm(pred)

    return apply_probability_floor(pred, floor=max(cfg.floor, floor))"""

new_return2 = """    pred = alpha_map[..., None] * pred + (1.0 - alpha_map[..., None]) * base
    pred = _safe_row_norm(pred)

    ocean_mask = (init_grid == 10)
    coastal_mask = np.zeros_like(ocean_mask)
    for y in range(h):
        for x in range(w):
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and init_grid[ny, nx] == 10:
                    coastal_mask[y, x] = True
                    break
                    
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    mountain_mask = (init_grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    return apply_probability_floor(pred, floor=max(cfg.floor, floor))"""

content = content.replace(old_return2, new_return2)

with open("src/predictor_spatial.py", "w") as f:
    f.write(content)
