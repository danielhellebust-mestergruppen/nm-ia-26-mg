from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from typing import Any
from .scoring import apply_probability_floor
from .types import grid_value_to_class_index, NUM_CLASSES

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

class SocioAttentionUNet(nn.Module):
    def __init__(self, in_channels=20, out_channels=6):
        super().__init__()
        # 20 channels in
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

_SOCIO_UNET_MODEL = None

def _load_socio_unet(model_path: Path) -> SocioAttentionUNet:
    global _SOCIO_UNET_MODEL
    if _SOCIO_UNET_MODEL is None:
        model = SocioAttentionUNet()
        if model_path.is_file():
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()
        _SOCIO_UNET_MODEL = model
    return _SOCIO_UNET_MODEL

def build_prediction_tensor_socio_unet(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 1e-5,
    model_path: Path | None = None,
) -> np.ndarray:
    if model_path is None:
        model_path = Path("data/reports/socio_unet_predictor.pth")
    
    grid = np.asarray(initial_grid, dtype=np.int64)
    h, w = grid.shape
    
    mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
    channels = 8
    x = np.zeros((channels, h, w), dtype=np.float32)
    for y in range(h):
        for x_idx in range(w):
            v = grid[y, x_idx]
            c = mapping.get(int(v), 0)
            x[c, y, x_idx] = 1.0
            
    ocean_mask = (grid == 10)
    dist = np.full((h, w), 100, dtype=np.float32)
    ys, xs = np.where(ocean_mask)
    qy, qx = list(ys), list(xs)
    for yy, xx in zip(ys, xs): dist[yy, xx] = 0
        
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
    
    obs_mask = np.zeros((1, h, w), dtype=np.float32)
    obs_channels = np.zeros((6, h, w), dtype=np.float32)
    socio_channels = np.zeros((4, h, w), dtype=np.float32) # pop, food, wealth, defense
    
    evidence = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)
    counts = np.zeros((h, w), dtype=np.float64)
    
    if observations:
        for obs in observations:
            g = obs.get("grid")
            vp = obs.get("viewport", {})
            if not g: continue
            vx, vy = int(vp.get("x", -1)), int(vp.get("y", -1))
            if vx < 0 or vy < 0: continue
            arr = np.asarray(g, dtype=np.int64)
            vh, vw = arr.shape
            y2, x2 = min(h, vy + vh), min(w, vx + vw)
            if y2 <= vy or x2 <= vx: continue
            arr = arr[: y2 - vy, : x2 - vx]
            
            for cy in range(arr.shape[0]):
                for cx in range(arr.shape[1]):
                    val = arr[cy, cx]
                    cls_idx = grid_value_to_class_index(val)
                    obs_channels[cls_idx, vy+cy, vx+cx] += 1.0
                    evidence[vy+cy, vx+cx, cls_idx] += 1.0
            
            counts[vy:y2, vx:x2] += 1.0
            obs_mask[0, vy:y2, vx:x2] = 1.0
            
            settlements = obs.get("settlements") or []
            for s in settlements:
                sx, sy = int(s.get("x", -1)), int(s.get("y", -1))
                if sx < 0 or sy < 0 or sx >= w or sy >= h: continue
                pop = float(s.get("population", 0.0) or 0.0)
                food = float(s.get("food", 0.0) or 0.0)
                wealth = float(s.get("wealth", 0.0) or 0.0)
                defense = float(s.get("defense", 0.0) or 0.0)
                
                # Apply these directly into the socio channels
                socio_channels[0, sy, sx] = pop
                socio_channels[1, sy, sx] = food
                socio_channels[2, sy, sx] = wealth
                socio_channels[3, sy, sx] = defense

        sums = obs_channels.sum(axis=0, keepdims=True)
        safe_sums = np.where(sums <= 0, 1.0, sums)
        obs_channels = obs_channels / safe_sums

    x_final = np.concatenate([x, dist[np.newaxis, :, :], obs_channels, socio_channels, obs_mask], axis=0)
    tensor_x = torch.from_numpy(x_final).unsqueeze(0)
    
    model = _load_socio_unet(model_path)
    with torch.no_grad():
        log_pred = model(tensor_x)
        pred = torch.exp(log_pred).squeeze(0).numpy()
        
    pred = pred.transpose((1, 2, 0))
    
    valid = counts > 0
    if np.any(valid):
        local_probs = evidence[valid] / counts[valid, None]
        pred[valid] = 0.22 * local_probs + 0.78 * pred[valid]

    # Post-processing constraints
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 0.98  
    pred[ocean_mask, 2] = 0.01  
    pred[ocean_mask, 4] = 0.01  

    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 0.99  
    pred[mountain_mask, 0] = 0.01  
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)
            
    return apply_probability_floor(pred, floor=floor)