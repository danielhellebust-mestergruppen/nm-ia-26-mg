#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import random

class AstarDataset(Dataset):
    def __init__(self, rounds_dir: Path, replays_dir: Path | None = None, holdout_round: str = ""):
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
                round_id = fp.name.split("_")[0]
                if holdout_round and round_id == holdout_round: continue
                seen_rounds.add(round_id)
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
                    self.samples.append((initial_grid, gt))
                except:
                    continue

    def __len__(self): return len(self.samples)
        
    def __getitem__(self, idx):
        grid, gt = self.samples[idx]
        
        # 1. Data Augmentation
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
        
        # 2. Base Grid One-Hot
        mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
        channels = 8
        x = np.zeros((channels, h, w), dtype=np.float32)
        for y in range(h):
            for x_idx in range(w):
                v = grid[y, x_idx]
                c = mapping.get(int(v), 0)
                x[c, y, x_idx] = 1.0
                
        # 3. Distance to Coast channel
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
        
        x_final = np.concatenate([x, dist[np.newaxis, :, :]], axis=0)
        gt_ch = gt.transpose((2, 0, 1))
        
        return torch.from_numpy(x_final), torch.from_numpy(gt_ch)

class DoubleConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
    def forward(self, x):
        return self.net(x)

class SimpleUNet(nn.Module):
    def __init__(self, in_channels=9, out_channels=6):
        super().__init__()
        # Downsample
        self.conv1 = DoubleConv(in_channels, 64)
        self.pool1 = nn.MaxPool2d(2)
        self.conv2 = DoubleConv(64, 128)
        self.pool2 = nn.MaxPool2d(2)
        
        # Bottleneck
        self.bottleneck = DoubleConv(128, 256)
        
        # Upsample
        self.up1 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.conv3 = DoubleConv(256, 128)
        self.up2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.conv4 = DoubleConv(128, 64)
        
        # Output
        self.out_conv = nn.Conv2d(64, out_channels, kernel_size=1)
        
    def forward(self, x):
        # Input: (B, 9, 40, 40)
        c1 = self.conv1(x)       
        p1 = self.pool1(c1)      
        
        c2 = self.conv2(p1)      
        p2 = self.pool2(c2)      
        
        bn = self.bottleneck(p2) 
        
        u1 = self.up1(bn)        
        cat1 = torch.cat([u1, c2], dim=1) 
        c3 = self.conv3(cat1)    
        
        u2 = self.up2(c3)        
        cat2 = torch.cat([u2, c1], dim=1) 
        c4 = self.conv4(cat2)    
        
        out = self.out_conv(c4)  
        return torch.log_softmax(out, dim=1)

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
    parser.add_argument("--out-model", default="data/reports/unet_predictor.pth", type=str)
    parser.add_argument("--epochs", default=150, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--lr", default=1e-3, type=float)
    parser.add_argument("--seed", default=42, type=int)
    parser.add_argument("--holdout-round", default="", type=str)
    args = parser.parse_args()
    import random
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    
    rounds_dir = Path(args.rounds_dir)
    dataset = AstarDataset(rounds_dir, getattr(args, "replays_dir", None) and Path(args.replays_dir), args.holdout_round)
    if len(dataset) == 0:
        print("No samples found.")
        return
        
    print(f"Loaded {len(dataset)} base samples for training. With augmentation, effective size is ~8x.")
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    
    model = SimpleUNet()
    optimizer = optim.Adam(model.parameters(), lr=args.lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=1e-5)
    
    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        for x, y in dataloader:
            optimizer.zero_grad()
            log_pred = model(x)
            loss = entropy_weighted_kl(log_pred, y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * x.size(0)
            
        scheduler.step()
        epoch_loss = total_loss / len(dataset)
        if (epoch+1) % 10 == 0:
            score_approx = max(0, min(100, 100 * np.exp(-3 * epoch_loss)))
            print(f"Epoch {epoch+1:3d}/{args.epochs} | WKL Loss: {epoch_loss:.4f} | Approx Score: {score_approx:.2f}/100")
            
    out_path = Path(args.out_model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), out_path)
    print(f"\\nSaved trained UNet to {out_path}")

if __name__ == "__main__":
    main()