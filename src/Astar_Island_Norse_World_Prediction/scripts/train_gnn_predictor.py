#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import numpy as np
import torch
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import random

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_gnn import GridGNN
from src.types import grid_value_to_class_index
class AstarDataset(Dataset):
    def __init__(self, rounds_dir: Path, replays_dir: Path | None = None, holdout_round: str = ""):
        self.samples = []

        # 1. Load from analysis files (your own completed rounds)
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
                round_id = fp.name.split("_")[0]
                if holdout_round and round_id == holdout_round: continue
                seen_rounds.add(round_id)
            except:
                continue

        # 2. Load from raw replays (The massive historical dataset)
        if replays_dir and replays_dir.exists():
            from src.types import grid_value_to_class_index, NUM_CLASSES
            for fp in sorted(replays_dir.glob("*.json")):
                round_id = fp.name.split('_')[0]
                # Skip if already loaded from analysis to avoid duplicates
                if round_id in seen_rounds or (holdout_round and round_id == holdout_round): continue

                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    frames = data.get("frames", [])
                    if not frames: continue

                    # initial_grid is frame 0
                    initial_grid = np.asarray(frames[0]["grid"], dtype=np.int64)
                    # final ground truth is the last frame
                    final_grid = np.asarray(frames[-1]["grid"], dtype=np.int64)

                    # Convert final_grid to the 6-channel probability format expected by the model
                    h, w = final_grid.shape
                    gt = np.zeros((h, w, NUM_CLASSES), dtype=np.float32)
                    for y in range(h):
                        for x in range(w):
                            cls_idx = grid_value_to_class_index(final_grid[y, x])
                            gt[y, x, cls_idx] = 1.0

                    self.samples.append((initial_grid, gt))
                except:
                    continue

    def __len__(self):
        return len(self.samples)
        
    def __getitem__(self, idx):
        grid, gt = self.samples[idx]
        
        # 1. Data Augmentation (Rotation/Flip)
        k = random.randint(0, 3)
        flip = random.choice([True, False])
        
        grid = np.rot90(grid, k)
        gt = np.rot90(gt, k, axes=(0, 1))
        if flip:
            grid = np.fliplr(grid)
            gt = np.fliplr(gt)
            
        grid = grid.copy()
        gt = gt.copy()
        h, w = grid.shape
        
        # 2. Base Grid One-Hot (8 channels)
        mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
        channels = 8
        x_base = np.zeros((channels, h, w), dtype=np.float32)
        for y in range(h):
            for x_idx in range(w):
                v = grid[y, x_idx]
                c = mapping.get(int(v), 0)
                x_base[c, y, x_idx] = 1.0
                
        # 3. Distance to Coast (1 channel)
        ocean_mask = (grid == 10)
        dist = np.full((h, w), 100, dtype=np.float32)
        ys, xs = np.where(ocean_mask)
        qy, qx = list(ys), list(xs)
        for yy, xx in zip(ys, xs):
            dist[yy, xx] = 0
            
        head = 0
        while head < len(qy):
            cy, cx = qy[head], qx[head]
            head += 1
            d = dist[cy, cx] + 1
            for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
                ny, nx = cy+dy, cx+dx
                if 0 <= ny < h and 0 <= nx < w and dist[ny, nx] > d:
                    dist[ny, nx] = d
                    qy.append(ny)
                    qx.append(nx)
        
        dist = dist / max(1.0, float(np.max(dist)))
        
        # 4. Simulate Partial Observations (7 channels)
        obs_mask = np.zeros((1, h, w), dtype=np.float32)
        obs_channels = np.zeros((6, h, w), dtype=np.float32)
        
        # Randomly choose number of observations (0 to 12)
        num_obs = random.randint(0, 12)
        for _ in range(num_obs):
            # Random viewport
            vx = random.randint(0, w - 15)
            vy = random.randint(0, h - 15)
            
            # Observe ground truth classes
            gt_vp = gt[vy:vy+15, vx:vx+15]
            obs_idx = np.argmax(gt_vp, axis=-1)
            
            for cy in range(15):
                for cx in range(15):
                    c = obs_idx[cy, cx]
                    obs_channels[c, vy+cy, vx+cx] = 1.0
                    obs_mask[0, vy+cy, vx+cx] = 1.0
        
        x_final = np.concatenate([
            x_base, 
            dist[np.newaxis, :, :], 
            obs_channels, 
            obs_mask
        ], axis=0) # 16 channels total
        
        gt_ch = gt.transpose((2, 0, 1))
        
        return torch.from_numpy(x_final), torch.from_numpy(gt_ch)

def entropy_weighted_kl(log_pred, target, eps=1e-12):
    p = torch.clamp(target, eps, 1.0)
    entropy = -torch.sum(p * torch.log(p), dim=1, keepdim=True)
    kl = torch.sum(p * (torch.log(p) - log_pred), dim=1, keepdim=True)
    wkl = torch.sum(entropy * kl) / torch.clamp(torch.sum(entropy), min=1e-15)
    return wkl

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds-dir", default="data/rounds", type=str)
    parser.add_argument("--replays-dir", default="data/replays", type=str)
    parser.add_argument("--out-model", default="data/reports/gnn_predictor.pth", type=str)
    parser.add_argument("--epochs", default=100, type=int)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--lr", default=1e-3, type=float)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--holdout-round", default="", type=str)
    parser.add_argument("--val-split", default=0.1, type=float)
    args = parser.parse_args()
    import random
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    
    rounds_dir = Path(args.rounds_dir)
    replays_dir = Path(args.replays_dir)
    full_dataset = AstarDataset(rounds_dir, replays_dir)
    if len(full_dataset) == 0:
        print("No samples found.")
        return
        
    val_size = int(len(full_dataset) * args.val_split)
    train_size = len(full_dataset) - val_size
    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size], generator=torch.Generator().manual_seed(args.seed))
    
    print(f"Loaded {len(full_dataset)} samples. Train: {train_size}, Val: {val_size}")
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = GridGNN(in_channels=16).to(device)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    
    best_val_loss = float('inf')
    
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            log_pred = model(x)
            loss = entropy_weighted_kl(log_pred, y)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * x.size(0)
            
        scheduler.step()
        train_loss /= train_size
        
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                log_pred = model(x)
                loss = entropy_weighted_kl(log_pred, y)
                val_loss += loss.item() * x.size(0)
        
        if val_size > 0:
            val_loss /= val_size
        else:
            val_loss = 0.0
            
        if (epoch+1) % 5 == 0 or epoch == 0:
            score_approx = max(0, min(100, 100 * np.exp(-3 * val_loss))) if val_size > 0 else 0
            print(f"Epoch {epoch+1:3d}/{args.epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Score Approx: {score_approx:.2f}")
            
        if val_loss < best_val_loss or val_size == 0:
            best_val_loss = val_loss
            out_path = Path(args.out_model)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), out_path)
            
    print(f"\\nTraining complete. Best Val Loss: {best_val_loss:.4f}")
    print(f"Saved best GNN to {args.out_model}")

if __name__ == "__main__":
    main()
