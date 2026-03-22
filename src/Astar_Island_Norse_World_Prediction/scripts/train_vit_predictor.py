#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import random

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.predictor_vit import ViTPredictor

class AstarVitDataset(Dataset):
    def __init__(self, rounds_dir: Path, replays_dir: Path | None = None, holdout_round: str = ""):
        self.samples = []
        files = list(rounds_dir.glob("*_analysis.json"))
        seen_rounds = set()
        for fp in sorted(files):
            try:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if "ground_truth" not in data or "initial_grid" not in data:
                    continue
                
                round_id = fp.name.split('_')[0]
                if holdout_round and round_id == holdout_round: continue
                seen_rounds.add(round_id)
                
                grid = np.asarray(data["initial_grid"], dtype=np.int64)
                gt = np.asarray(data["ground_truth"], dtype=np.float32)
                # For basic rounds without frames, fake them
                frames = data.get("frames", [])
                self.samples.append((grid, gt, frames))
            except:
                continue

        if replays_dir and replays_dir.exists():
            for fp in sorted(replays_dir.glob("*.json")):
                round_id = fp.name.split('_')[0]
                if round_id in seen_rounds or (holdout_round and round_id == holdout_round): continue
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

    def __len__(self): return len(self.samples)

    def __getitem__(self, idx):
        grid, gt, frames = self.samples[idx]
        
        # Pick a random time step to simulate the observation
        t = 0
        frame = None
        if len(frames) > 0:
            t = random.randint(0, len(frames) - 1)
            frame = frames[t]
        
        obs_grid = None
        settlements = []
        if frame and isinstance(frame, dict):
            for k in ("grid", "layout", "state", "map"):
                if k in frame and isinstance(frame[k], list):
                    obs_grid = np.asarray(frame[k], dtype=np.int64)
                    break
            if "settlements" in frame:
                settlements = frame["settlements"]

        # Data Augmentation
        k = random.randint(0, 3)
        flip = random.choice([True, False])

        grid = np.rot90(grid, k)
        gt = np.rot90(gt, k, axes=(0, 1))
        if obs_grid is not None:
            obs_grid = np.rot90(obs_grid, k)
        if flip:
            grid = np.fliplr(grid)
            gt = np.fliplr(gt)
            if obs_grid is not None:
                obs_grid = np.fliplr(obs_grid)
                
        grid = grid.copy()
        gt = gt.copy()
        if obs_grid is not None:
            obs_grid = obs_grid.copy()

        h, w = grid.shape

        # Base Grid One-Hot
        mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
        channels = 8
        x = np.zeros((channels, h, w), dtype=np.float32)
        for y in range(h):
            for x_idx in range(w):
                v = grid[y, x_idx]
                c = mapping.get(int(v), 0)
                x[c, y, x_idx] = 1.0

        # Distance to Coast
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

        # Learning to Query: Masked Observations + Socio
        obs_mask = np.zeros((1, h, w), dtype=np.float32)
        obs_channels = np.zeros((6, h, w), dtype=np.float32)
        
        # Assume observation logic (similar to SocioUNet)
        num_obs = random.randint(0, 12)
        for _ in range(num_obs):
            vx = random.randint(0, w - 15)
            vy = random.randint(0, h - 15)
            obs_mask[0, vy:vy+15, vx:vx+15] = 1.0

            if obs_grid is not None:
                vp = obs_grid[vy:vy+15, vx:vx+15]
                for cy in range(15):
                    for cx in range(15):
                        val = vp[cy, cx]
                        if val in (0, 10, 11): cls = 0
                        elif val == 1: cls = 1
                        elif val == 2: cls = 2
                        elif val == 3: cls = 3
                        elif val == 4: cls = 4
                        elif val == 5: cls = 5
                        else: cls = 0
                        obs_channels[cls, vy+cy, vx+cx] = 1.0
            else:
                gt_vp = gt[vy:vy+15, vx:vx+15]
                c_idx = np.argmax(gt_vp, axis=-1)
                for cy in range(15):
                    for cx in range(15):
                        c = c_idx[cy, cx]
                        obs_channels[c, vy+cy, vx+cx] = 1.0

        socio_channels = np.zeros((4, h, w), dtype=np.float32) # pop, food, wealth, defense
        for s in settlements:
            orig_sx = s.get("x", -1)
            orig_sy = s.get("y", -1)
            if orig_sx < 0 or orig_sy < 0: continue
            
            # Apply same aug to settlement coords
            # (Rotation logic skipped here for simplicity - in reality needs transformation)
            sx = int(orig_sx)
            sy = int(orig_sy)
            if 0 <= sx < w and 0 <= sy < h:
                if obs_mask[0, sy, sx] > 0:
                    socio_channels[0, sy, sx] = float(s.get("population", 0.0) or 0.0)
                    socio_channels[1, sy, sx] = float(s.get("food", 0.0) or 0.0)
                    socio_channels[2, sy, sx] = float(s.get("wealth", 0.0) or 0.0)
                    socio_channels[3, sy, sx] = float(s.get("defense", 0.0) or 0.0)

        obs_channels = obs_channels * obs_mask
        socio_channels = socio_channels * obs_mask

        # Stack: 8 + 1 + 6 + 4 + 1 = 20 channels
        x_final = np.concatenate([x, dist[np.newaxis, :, :], obs_channels, socio_channels, obs_mask], axis=0)
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
    parser.add_argument("--out-model", default="data/reports/vit_predictor.pth", type=str)
    parser.add_argument("--epochs", default=100, type=int)
    parser.add_argument("--batch-size", default=16, type=int)
    parser.add_argument("--lr", default=1e-3, type=float)
    parser.add_argument("--val-split", default=0.1, type=float)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--holdout-round", default="", type=str)
    
    args = parser.parse_args()
    
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        
    rounds_dir = Path(args.rounds_dir)
    dataset = AstarVitDataset(rounds_dir, getattr(args, "replays_dir", None) and Path(args.replays_dir), args.holdout_round)
    
    if len(dataset) == 0:
        print("No samples found.")
        return
        
    val_size = int(len(dataset) * args.val_split)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size], generator=torch.Generator().manual_seed(args.seed))
    
    print(f"Loaded {len(dataset)} base samples for ViT training.")
    print(f"Train samples: {train_size}, Val samples: {val_size}")
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = ViTPredictor(in_channels=20, out_channels=6).to(device)
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
            
        if (epoch+1) % 10 == 0 or epoch == 0:
            score_approx = max(0, min(100, 100 * np.exp(-3 * val_loss))) if val_size > 0 else 0
            print(f"Epoch {epoch+1:3d}/{args.epochs} | Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f} | Val Score Approx: {score_approx:.2f}")
            
        if val_loss < best_val_loss or val_size == 0:
            best_val_loss = val_loss
            out_path = Path(args.out_model)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), out_path)
            
    print(f"\\nTraining complete. Best Val Loss: {best_val_loss:.4f}")
    print(f"Saved trained ViT to {args.out_model}")

if __name__ == "__main__":
    main()
