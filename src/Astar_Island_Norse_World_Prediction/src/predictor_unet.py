from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
from pathlib import Path
from typing import Any
from .scoring import apply_probability_floor
from .types import grid_value_to_class_index, NUM_CLASSES

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
        self.conv1 = DoubleConv(in_channels, 64)
        self.pool1 = nn.MaxPool2d(2)
        self.conv2 = DoubleConv(64, 128)
        self.pool2 = nn.MaxPool2d(2)
        self.bottleneck = DoubleConv(128, 256)
        self.up1 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.conv3 = DoubleConv(256, 128)
        self.up2 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.conv4 = DoubleConv(128, 64)
        self.out_conv = nn.Conv2d(64, out_channels, kernel_size=1)
        
    def forward(self, x):
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

_UNET_MODEL = None

def _load_unet(model_path: Path) -> SimpleUNet:
    global _UNET_MODEL
    if _UNET_MODEL is None:
        model = SimpleUNet(in_channels=9, out_channels=6)
        if model_path.is_file():
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()
        _UNET_MODEL = model
    return _UNET_MODEL

def build_prediction_tensor_unet(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 0.01,
    model_path: Path | None = None,
) -> np.ndarray:
    if model_path is None:
        model_path = Path("data/reports/unet_predictor.pth")
    
    grid = np.asarray(initial_grid, dtype=np.int64)
    h, w = grid.shape
    
    # 1. Base Grid
    mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
    channels = 8
    x = np.zeros((channels, h, w), dtype=np.float32)
    for y in range(h):
        for x_idx in range(w):
            v = grid[y, x_idx]
            c = mapping.get(int(v), 0)
            x[c, y, x_idx] = 1.0
            
    # 2. Distance to Coast
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
                
    coastal_mask = (dist == 1.0)
    dist = dist / max(1.0, float(np.max(dist)))
    
    x_final = np.concatenate([x, dist[np.newaxis, :, :]], axis=0)
    tensor_x = torch.from_numpy(x_final).unsqueeze(0)
    
    model = _load_unet(model_path)
    with torch.no_grad():
        log_pred = model(tensor_x)
        pred = torch.exp(log_pred).squeeze(0).numpy()
        
    pred = pred.transpose((1, 2, 0))
    
    # Process observations post-network
    if observations:
        evidence = np.zeros((h, w, NUM_CLASSES), dtype=np.float64)
        counts = np.zeros((h, w), dtype=np.float64)
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
                    evidence[vy+cy, vx+cx, cls_idx] += 1.0
            counts[vy:y2, vx:x2] += 1.0
            
        valid = counts > 0
        if np.any(valid):
            local_probs = evidence[valid] / counts[valid, None]
            pred[valid] = 0.22 * local_probs + 0.78 * pred[valid]

    # Post-processing constraints

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

    return apply_probability_floor(pred, floor=floor)
