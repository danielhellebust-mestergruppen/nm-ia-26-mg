import re
from pathlib import Path

# Function to patch a dataset
def patch_dataset(file_path):
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

    # Replace the __init__ and __len__ part
    old_init_pattern = r'class AstarDataset\(Dataset\):.*?def __len__\(self\):[^\n]*'
    content = re.sub(old_init_pattern, new_dataset, content, flags=re.DOTALL)
    
    # Update main argument parsing to include replays_dir
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

patch_dataset("scripts/train_attention_unet_predictor.py")
patch_dataset("scripts/train_unet_predictor.py")
