import json
import argparse
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
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
                round_id = fp.name.split("_")[0]
                if holdout_round and round_id == holdout_round: continue
                grid = np.asarray(data["initial_grid"], dtype=np.int64)
                gt = np.asarray(data["ground_truth"], dtype=np.float32)
                self.samples.append((grid, gt))
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
            
        grid, gt = grid.copy(), gt.copy()
        h, w = grid.shape
        
        # 2. Base Grid One-Hot & Distance to Coast (CACHED)
        if not hasattr(self, "_cache"): self._cache = {}
        if idx not in self._cache:
            orig_grid = self.samples[idx][0]
            oh, ow = orig_grid.shape
            mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
            cx = np.zeros((8, oh, ow), dtype=np.float32)
            for y in range(oh):
                for x_idx in range(ow):
                    cx[mapping.get(int(orig_grid[y, x_idx]), 0), y, x_idx] = 1.0
            ocean_mask = (orig_grid == 10)
            cdist = np.full((oh, ow), 100, dtype=np.float32)
            ys, xs = np.where(ocean_mask)
            qy, qx = list(ys), list(xs)
            for yy, xx in zip(ys, xs): cdist[yy, xx] = 0
            head = 0
            while head < len(qy):
                cy, cx_pos = qy[head], qx[head]
                head += 1
                d = cdist[cy, cx_pos] + 1
                for dy, dx in ((-1,0),(1,0),(0,-1),(0,1)):
                    ny, nx = cy+dy, cx_pos+dx
                    if 0 <= ny < oh and 0 <= nx < ow and cdist[ny, nx] > d:
                        cdist[ny, nx] = d
                        qy.append(ny)
                        qx.append(nx)
            cdist = cdist / max(1.0, float(np.max(cdist)))
            self._cache[idx] = (cx, cdist)
        
        x, dist = self._cache[idx]
        x, dist = x.copy(), dist.copy()
        
        x = np.rot90(x, k, axes=(1, 2))
        dist = np.rot90(dist, k, axes=(0, 1))
        if flip:
            x = np.flip(x, axis=2)
            dist = np.flip(dist, axis=1)
        x = x.copy()
        dist = dist.copy()

        
        x_final = np.concatenate([x, dist[np.newaxis, :, :]], axis=0)
        gt_ch = gt.transpose((2, 0, 1))
        return torch.from_numpy(x_final), torch.from_numpy(gt_ch)

class ResidualConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels)
        )
        self.shortcut = nn.Sequential()
        if in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1),
                nn.BatchNorm2d(out_channels)
            )
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        res = self.shortcut(x)
        x = self.conv1(x)
        x = self.conv2(x)
        x += res
        return self.relu(x)

class AttentionGate(nn.Module):
    """
    Attention Gate mathematically acts like a localized Graph Network.
    It learns to focus on the regions of the skip connection (x) that are 
    most relevant to the global context flowing up from the bottleneck (g).
    """
    def __init__(self, F_g, F_l, F_int):
        super().__init__()
        self.W_g = nn.Sequential(
            nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        
        self.W_x = nn.Sequential(
            nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(F_int)
        )
        
        self.psi = nn.Sequential(
            nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True),
            nn.BatchNorm2d(1),
            nn.Sigmoid()
        )
        self.relu = nn.ReLU(inplace=True)
        
    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi

class AttentionUNet(nn.Module):
    def __init__(self, in_channels=9, out_channels=6):
        super().__init__()
        # Wider ResNet architecture
        self.enc1 = ResidualConv(in_channels, 96)
        self.pool1 = nn.MaxPool2d(2)
        self.enc2 = ResidualConv(96, 192)
        self.pool2 = nn.MaxPool2d(2)
        self.enc3 = ResidualConv(192, 384)
        
        # Adaptive Temperature Head
        self.temp_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.temp_fc = nn.Sequential(
            nn.Linear(384, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, 1),
            nn.Sigmoid()
        )
        
        self.up1 = nn.ConvTranspose2d(384, 192, kernel_size=2, stride=2)
        self.att1 = AttentionGate(F_g=192, F_l=192, F_int=96)
        self.dec1 = ResidualConv(384, 192)
        
        self.up2 = nn.ConvTranspose2d(192, 96, kernel_size=2, stride=2)
        self.att2 = AttentionGate(F_g=96, F_l=96, F_int=48)
        self.dec2 = ResidualConv(192, 96)
        
        self.out_conv = nn.Conv2d(96, out_channels, kernel_size=1)
        
    def forward(self, x):
        e1 = self.enc1(x)
        e2 = self.enc2(self.pool1(e1))
        e3 = self.enc3(self.pool2(e2))
        
        # Predict Temperature from Bottleneck
        t_feat = self.temp_pool(e3).view(e3.size(0), -1)
        temp = self.temp_fc(t_feat) * 1.5 + 0.5  # Scales Sigmoid to range [0.5, 2.0]
        temp = temp.view(-1, 1, 1, 1) # Reshape for broadcasting
        
        d1 = self.up1(e3)
        x2 = self.att1(g=d1, x=e2) # Attention applied to skip connection
        d1 = torch.cat([d1, x2], dim=1)
        d1 = self.dec1(d1)
        
        d2 = self.up2(d1)
        x1 = self.att2(g=d2, x=e1) # Attention applied to skip connection
        d2 = torch.cat([d2, x1], dim=1)
        d2 = self.dec2(d2)
        
        out = self.out_conv(d2)
        return torch.log_softmax(out / temp, dim=1)

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
    parser.add_argument("--out-model", default="data/reports/attention_unet_predictor.pth", type=str)
    parser.add_argument("--epochs", default=250, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
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
    dataset = AstarDataset(rounds_dir, getattr(args, "replays_dir", None) and Path(args.replays_dir), args.holdout_round)
    if len(dataset) == 0: return
        
    print(f"Loaded {len(dataset)} base samples for Attention U-Net training.")
    val_size = int(len(dataset) * args.val_split)
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size], generator=torch.Generator().manual_seed(args.seed))
    
    print(f"Train samples: {train_size}, Val samples: {val_size}")
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = AttentionUNet().to(device)
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
            
    print(f"\nTraining complete. Best Val Loss: {best_val_loss:.4f}")
    print(f"Saved best Attention U-Net to {args.out_model}")
    print(f"\\nSaved trained Attention U-Net to {out_path}")

if __name__ == "__main__":
    main()