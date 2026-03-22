import re

# Patch predictor_time_socio_unet.py
file_path = "src/predictor_time_socio_unet.py"
with open(file_path, "r") as f:
    content = f.read()

# Update coastal_mask logic
old_dist_logic = """                qy.append(ny)
                qx.append(nx)
                
    dist = dist / max(1.0, float(np.max(dist)))"""

new_dist_logic = """                qy.append(ny)
                qx.append(nx)
                
    coastal_mask = (dist == 1.0)
    dist = dist / max(1.0, float(np.max(dist)))"""

content = content.replace(old_dist_logic, new_dist_logic)

# Update constraints
old_constraints = """    # Post-processing constraints
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 0.98  
    pred[ocean_mask, 2] = 0.01  
    pred[ocean_mask, 4] = 0.01  

    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 0.99  
    pred[mountain_mask, 0] = 0.01  
    
    sums = pred.sum(axis=-1, keepdims=True)"""

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
    
    sums = pred.sum(axis=-1, keepdims=True)"""

content = content.replace(old_constraints, new_constraints)

# Force 1e-5 floor
content = content.replace("return apply_probability_floor(pred, floor=floor)", "return apply_probability_floor(pred, floor=1e-5)")

with open(file_path, "w") as f:
    f.write(content)

# Patch scripts/train_time_socio_unet_predictor.py
file_path_train = "scripts/train_time_socio_unet_predictor.py"
with open(file_path_train, "r") as f:
    content_train = f.read()

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
                # Replays and analysis files might have different structures, but we prefer analysis for gt
                self.samples.append((grid, gt, data.get("frames", [])))
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
                    self.samples.append((initial_grid, gt, frames))
                except:
                    continue

    def __len__(self): return len(self.samples)"""

old_init_pattern = r'class AstarDataset\(Dataset\):.*?def __len__\(self\):[^\n]*'
content_train = re.sub(old_init_pattern, new_dataset, content_train, flags=re.DOTALL)

# Update __getitem__ to handle frames
content_train = content_train.replace('grid, gt = self.samples[idx]', 'grid, gt, frames = self.samples[idx]')

if "parser.add_argument(\"--replays-dir\"" not in content_train:
    content_train = content_train.replace(
        'parser.add_argument("--rounds-dir", default="data/rounds", type=str)',
        'parser.add_argument("--rounds-dir", default="data/rounds", type=str)\n    parser.add_argument("--replays-dir", default="data/replays", type=str)'
    )
    content_train = content_train.replace(
        'dataset = AstarDataset(rounds_dir)',
        'dataset = AstarDataset(rounds_dir, Path(args.replays_dir))'
    )

with open(file_path_train, "w") as f:
    f.write(content_train)
