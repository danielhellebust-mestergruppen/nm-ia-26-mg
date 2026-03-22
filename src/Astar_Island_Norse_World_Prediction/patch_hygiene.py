import glob
import re

def sample_code():
    return """        # Replaced argmax with probabilistic sampling
        cumulative = np.cumsum(gt_vp, axis=-1)
        r = np.random.rand(gt_vp.shape[0], gt_vp.shape[1], 1)
        obs_grid = np.argmax(cumulative > r, axis=-1)"""

for file_path in ["scripts/eval_two_pass.py", "scripts/eval_multipass.py"]:
    try:
        with open(file_path, "r") as f:
            content = f.read()
        content = re.sub(
            r'obs_grid\s*=\s*np\.argmax\(gt_vp,\s*axis=-1\)',
            sample_code(),
            content
        )
        with open(file_path, "w") as f:
            f.write(content)
        print(f"Patched {file_path}")
    except FileNotFoundError:
        print(f"File {file_path} not found")

# Patch run_active_round.py
with open("scripts/run_active_round.py", "r") as f:
    content = f.read()
content = content.replace(
    'choices=["baseline", "spatial", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "time_socio_unet"]',
    'choices=["baseline", "spatial", "spatial_unet", "unet", "convlstm", "unet_spatial", "attn_unet", "attn_unet_spatial", "ensemble", "socio_unet", "time_socio_unet"]'
)
with open("scripts/run_active_round.py", "w") as f:
    f.write(content)
print("Patched run_active_round.py")

# Patch training scripts
import os
for file_path in glob.glob("scripts/train_*_predictor.py"):
    with open(file_path, "r") as f:
        content = f.read()
    
    # Add seed and holdout arguments if not present
    if '--seed' not in content:
        content = content.replace(
            'parser.add_argument("--lr", default=1e-3, type=float)',
            'parser.add_argument("--lr", default=1e-3, type=float)\n    parser.add_argument("--seed", default=42, type=int)\n    parser.add_argument("--holdout-round", default="", type=str)'
        )
    
    # Add seeding logic in main
    seed_logic = """
    import random
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
"""
    if 'torch.manual_seed(args.seed)' not in content:
        content = re.sub(r'(args\s*=\s*parser\.parse_args\(\))', r'\1' + seed_logic, content)
    
    # Patch AstarDataset to accept holdout_round and exclude it
    if 'holdout_round: str = ""' not in content:
        content = re.sub(
            r'def __init__\(self,\s*rounds_dir:\s*Path(?:,\s*replays_dir:\s*Path\s*\|\s*None\s*=\s*None)?\):',
            r'def __init__(self, rounds_dir: Path, replays_dir: Path | None = None, holdout_round: str = ""):',
            content
        )
        content = re.sub(
            r'dataset\s*=\s*AstarDataset\(rounds_dir(?:,\s*Path\(args\.replays_dir\))?\)',
            r'dataset = AstarDataset(rounds_dir, getattr(args, "replays_dir", None) and Path(args.replays_dir), args.holdout_round)',
            content
        )
        
        # Add exclusion logic for analysis files
        if 'if holdout_round and round_id == holdout_round: continue' not in content:
            content = re.sub(
                r'seen_rounds\.add\(fp\.name\.split\(\'_\'\)\[0\]\)',
                r'round_id = fp.name.split("_")[0]\n                if holdout_round and round_id == holdout_round: continue\n                seen_rounds.add(round_id)',
                content
            )
            # Make sure replays exclusion also uses holdout
            content = re.sub(
                r'if round_id in seen_rounds:\s*continue',
                r'if round_id in seen_rounds or (holdout_round and round_id == holdout_round): continue',
                content
            )
            
    # Also patch random_split generator to use seed
    if 'random_split' in content and 'generator=' not in content:
        content = re.sub(
            r'random_split\(([^,]+),\s*\[([^,]+),\s*([^\]]+)\]\)',
            r'random_split(\1, [\2, \3], generator=torch.Generator().manual_seed(args.seed))',
            content
        )

    with open(file_path, "w") as f:
        f.write(content)
    print(f"Patched {file_path}")
