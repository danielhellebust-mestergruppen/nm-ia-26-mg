import json
import argparse
from pathlib import Path
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import random

class AstarTimeSocioDataset(Dataset):
    def __init__(self, rounds_dir: Path, replays_dir: Path, exclude_rounds: set[str] = None):
        self.samples = []
        exclude_rounds = exclude_rounds or set()
        for fp in sorted(rounds_dir.glob("*_analysis.json")):
            data = json.loads(fp.read_text(encoding="utf-8"))
            if "ground_truth" not in data: continue
            
            round_id = data["round_id"]
            if round_id in exclude_rounds: continue
            
            seed_idx = data["seed_index"]
            
            replay_fp = replays_dir / f"{round_id}_seed{seed_idx}.json"
            if not replay_fp.is_file(): continue
            
            try:
                replay_data = json.loads(replay_fp.read_text(encoding="utf-8"))
            except Exception:
                continue
                
            frames = None
            if isinstance(replay_data, dict) and "frames" in replay_data:
                frames = replay_data["frames"]
            elif isinstance(replay_data, dict) and "data" in replay_data and "frames" in replay_data["data"]:
                frames = replay_data["data"]["frames"]
            elif isinstance(replay_data, list):
                frames = replay_data
                
            if not frames or len(frames) < 50: continue
            
            grid = np.asarray(data["initial_grid"], dtype=np.int64)
            gt = np.asarray(data["ground_truth"], dtype=np.float32)
            
            if gt.shape[-1] != 6: continue
            
            self.samples.append((grid, gt, frames))
            
    def __len__(self): return len(self.samples)
        
    def __getitem__(self, idx):
        grid, gt, frames = self.samples[idx]
        
        # Pick a random time step to simulate the observation
        # frames is 0 to 50 usually. Pick t in [0, len(frames)-1]
        t = random.randint(0, len(frames) - 1)
        frame = frames[t]
        
        grid_keys = ("grid", "layout", "state", "map")
        obs_grid = None
        if isinstance(frame, dict):
            for k in grid_keys:
                if k in frame and isinstance(frame[k], list):
                    obs_grid = frame[k]
                    break
        elif isinstance(frame, list) and isinstance(frame[0], list):
            obs_grid = frame
            
        if obs_grid is None:
            obs_grid = grid.copy() # fallback
        else:
            obs_grid = np.asarray(obs_grid, dtype=np.int64)
            
        settlements = frame.get("settlements", []) if isinstance(frame, dict) else []
        
        # 1. Data Augmentation
        k = random.randint(0, 3)
        flip = random.choice([True, False])
        grid = np.rot90(grid, k)
        obs_grid = np.rot90(obs_grid, k)
        gt = np.rot90(gt, k, axes=(0, 1))
        
        h, w = grid.shape
        
        # Build spatial socio-economic channels from settlements
        socio_channels = np.zeros((4, h, w), dtype=np.float32) # pop, food, wealth, defense
        for s in settlements:
            sx, sy = int(s.get("x", -1)), int(s.get("y", -1))
            if sx < 0 or sy < 0 or sx >= w or sy >= h: continue
            
            pop = float(s.get("population", 0.0) or 0.0)
            food = float(s.get("food", 0.0) or 0.0)
            wealth = float(s.get("wealth", 0.0) or 0.0)
            defense = float(s.get("defense", 0.0) or 0.0)
            
            if k == 1: sx, sy = sy, w - 1 - sx
            elif k == 2: sx, sy = w - 1 - sx, h - 1 - sy
            elif k == 3: sx, sy = w - 1 - sy, sx
            
            if flip: sx = w - 1 - sx
                
            if 0 <= sx < w and 0 <= sy < h:
                socio_channels[0, sy, sx] = pop
                socio_channels[1, sy, sx] = food
                socio_channels[2, sy, sx] = wealth
                socio_channels[3, sy, sx] = defense
            
        if flip:
            grid = np.fliplr(grid)
            obs_grid = np.fliplr(obs_grid)
            gt = np.fliplr(gt)
            
        grid, gt, obs_grid = grid.copy(), gt.copy(), obs_grid.copy()
        
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

        
        # 4. The Time Channel!
        # Represented as t / 50.0 (the max time steps)
        time_frac = min(1.0, t / 50.0)
        time_channel = np.full((1, h, w), time_frac, dtype=np.float32)
        
        # 5. Learning to Query: Masked Observations + Socio
        obs_mask = np.zeros((1, h, w), dtype=np.float32)
        obs_channels = np.zeros((6, h, w), dtype=np.float32)
        
        # In a real game, we might have multiple viewports over time.
        # Let's randomly reveal 0 to 8 viewports.
        num_vps = random.randint(0, 8)
        for _ in range(num_vps):
            vy = random.randint(0, max(0, h - 15))
            vx = random.randint(0, max(0, w - 15))
            obs_mask[0, vy:vy+15, vx:vx+15] = 1.0
            
        for y in range(h):
            for x_idx in range(w):
                v = obs_grid[y, x_idx]
                if v in (0, 10, 11): c = 0
                elif v == 1: c = 1
                elif v == 2: c = 2
                elif v == 3: c = 3
                elif v == 4: c = 4
                elif v == 5: c = 5
                else: c = 0
                obs_channels[c, y, x_idx] = 1.0
                
        obs_channels = obs_channels * obs_mask
        socio_channels = socio_channels * obs_mask
        
        # Stack: 8 (base) + 1 (dist) + 1 (time) + 6 (obs terrain) + 4 (socio) + 1 (mask) = 21 channels!
        x_final = np.concatenate([x, dist[np.newaxis, :, :], time_channel, obs_channels, socio_channels, obs_mask], axis=0)
        gt_ch = gt.transpose((2, 0, 1))
        return torch.from_numpy(x_final), torch.from_numpy(gt_ch)

class ResidualConv(nn.Module):
    def __init__(self, in_channels, out_channels, dropout_prob=0.2):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(p=dropout_prob)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.Dropout2d(p=dropout_prob)
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
    def __init__(self, F_g, F_l, F_int):
        super().__init__()
        self.W_g = nn.Sequential(nn.Conv2d(F_g, F_int, kernel_size=1, stride=1, padding=0, bias=True), nn.BatchNorm2d(F_int))
        self.W_x = nn.Sequential(nn.Conv2d(F_l, F_int, kernel_size=1, stride=1, padding=0, bias=True), nn.BatchNorm2d(F_int))
        self.psi = nn.Sequential(nn.Conv2d(F_int, 1, kernel_size=1, stride=1, padding=0, bias=True), nn.BatchNorm2d(1), nn.Sigmoid())
        self.relu = nn.ReLU(inplace=True)
        
    def forward(self, g, x):
        g1 = self.W_g(g)
        x1 = self.W_x(x)
        psi = self.relu(g1 + x1)
        psi = self.psi(psi)
        return x * psi

class TimeSocioAttentionUNet(nn.Module):
    def __init__(self, in_channels=21, out_channels=6):
        super().__init__()
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
        x2 = self.att1(g=d1, x=e2)
        d1 = torch.cat([d1, x2], dim=1)
        d1 = self.dec1(d1)
        
        d2 = self.up2(d1)
        x1 = self.att2(g=d2, x=e1)
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
    parser.add_argument("--out-model", default="data/reports/time_socio_unet_predictor.pth", type=str)
    parser.add_argument("--epochs", default=250, type=int)
    parser.add_argument("--batch-size", default=8, type=int)
    parser.add_argument("--lr", default=1e-3, type=float)
    parser.add_argument("--seed", default=42, type=int, help="Random seed for reproducibility")
    parser.add_argument("--exclude-rounds", default="", type=str, help="Comma separated round IDs to exclude from training")
    args = parser.parse_args()
    
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    
    rounds_dir = Path(args.rounds_dir)
    replays_dir = Path(args.replays_dir)
    exclude = set(r.strip() for r in args.exclude_rounds.split(",") if r.strip())
    dataset = AstarTimeSocioDataset(rounds_dir, replays_dir, exclude_rounds=exclude)
    if len(dataset) == 0: 
        print("No samples found.")
        return
        
    print(f"Loaded {len(dataset)} base samples for Time-Aware Socio-Economic Attention U-Net training.")
    dataloader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True)
    
    model = TimeSocioAttentionUNet()
    optimizer = optim.Adam(model.parameters(), lr=args.lr, weight_decay=1e-4)
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
    print(f"\\nSaved trained Time-Aware Socio-Economic U-Net to {out_path}")

if __name__ == "__main__":
    main()
