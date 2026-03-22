import re
from pathlib import Path

# Patch the training script
file_path = "scripts/train_convlstm_predictor.py"
with open(file_path, "r") as f:
    content = f.read()

new_dataset = """class AstarDataset(Dataset):
    def __init__(self, rounds_dir: Path, replays_dir: Path | None = None):
        self.samples = []
        files = list(rounds_dir.glob("*_analysis.json"))
        seen_rounds = set()
        for fp in sorted(files):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if "ground_truth" not in data or "initial_grid" not in data:
                    continue
                grid = np.asarray(data["initial_grid"], dtype=np.int64)
                gt = np.asarray(data["ground_truth"], dtype=np.float32)
                self.samples.append((grid, gt))
                seen_rounds.add(fp.name.split('_')[0])
            except:
                continue

        if replays_dir and replays_dir.exists():
            for fp in sorted(replays_dir.glob("*.json")):
                round_id = fp.name.split('_')[0]
                if round_id in seen_rounds: continue
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    frames = data.get("frames", [])
                    if not frames: continue
                    initial_grid = np.asarray(frames[0]["grid"], dtype=np.int64)
                    final_grid = np.asarray(frames[-1]["grid"], dtype=np.int64)
                    h, w = final_grid.shape
                    gt = np.zeros((h, w, 6), dtype=np.float32)
                    for y in range(h):
                        for x in range(w):
                            v = final_grid[y, x]
                            if v in (0, 10, 11): cls = 0
                            elif v == 1: cls = 1
                            elif v == 2: cls = 2
                            elif v == 3: cls = 3
                            elif v == 4: cls = 4
                            elif v == 5: cls = 5
                            else: cls = 0
                            gt[y, x, cls] = 1.0
                    self.samples.append((initial_grid, gt))
                except:
                    continue

    def __len__(self): return len(self.samples)"""

old_init_pattern = r'class AstarDataset\(Dataset\):.*?def __len__\(self\):[^\n]*'
content = re.sub(old_init_pattern, new_dataset, content, flags=re.DOTALL)

if "parser.add_argument(\"--replays-dir\"" not in content:
    content = content.replace(
        'parser.add_argument("--rounds-dir", default="data/rounds", type=str)',
        'parser.add_argument("--rounds-dir", default="data/rounds", type=str)\n    parser.add_argument("--replays-dir", default="data/replays", type=str)'
    )
    content = content.replace(
        'dataset = AstarDataset(rounds_dir)',
        'dataset = AstarDataset(rounds_dir, Path(args.replays_dir))'
    )

with open(file_path, "w") as f:
    f.write(content)

# Patch the predictor file
file_path_src = "src/predictor_convlstm.py"
with open(file_path_src, "r") as f:
    content_src = f.read()

# Update floor default
content_src = content_src.replace('floor: float = 1e-5,', 'floor: float = 1e-5,')

# Update coastal_mask logic
old_dist_logic = """                qx.append(nx)
        
    dist = dist / max(1.0, float(np.max(dist)))
    
    x_final = np.concatenate([x, dist[np.newaxis, :, :]], axis=0)"""

new_dist_logic = """                qx.append(nx)
        
    coastal_mask = (dist == 1.0)
    dist = dist / max(1.0, float(np.max(dist)))
    
    x_final = np.concatenate([x, dist[np.newaxis, :, :]], axis=0)"""

content_src = content_src.replace(old_dist_logic, new_dist_logic)

# Update post-processing constraints
old_constraints = """    # Post-processing: Correct CNN edge artifacts and enforce hard constraints for static map features
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 0.98  # Ocean overwhelmingly remains empty/ocean
    pred[ocean_mask, 2] = 0.01  # Tiny chance of a coastal port touching an ocean tile
    pred[ocean_mask, 4] = 0.01  # Tiny chance of forest

    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 0.99  # Mountains are highly static
    pred[mountain_mask, 0] = 0.01  # Tiny chance of becoming empty

    # normalize the updated predictions
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    return apply_probability_floor(pred, floor=floor)"""

new_constraints = """    # Post-processing constraints
    
    # 1. Oceans cannot move (class 0 = Empty)
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    # 2. Mountains cannot move (class 5 = Mountain)
    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    # 3. Ports (class 2) must be adjacent to the ocean
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0

    # normalize the updated predictions
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    return apply_probability_floor(pred, floor=floor)"""

if old_constraints in content_src:
    content_src = content_src.replace(old_constraints, new_constraints)
elif "Post-processing constraints" not in content_src:
    # Use regex
    import re
    p = re.compile(r'    # Post-processing: Correct CNN edge artifacts.*return apply_probability_floor\(pred, floor=1e-5\)', re.DOTALL)
    content_src = p.sub(new_constraints, content_src)
    
    p2 = re.compile(r'    # Post-processing: Correct CNN edge artifacts.*return apply_probability_floor\(pred, floor=floor\)', re.DOTALL)
    content_src = p2.sub(new_constraints, content_src)


with open(file_path_src, "w") as f:
    f.write(content_src)
