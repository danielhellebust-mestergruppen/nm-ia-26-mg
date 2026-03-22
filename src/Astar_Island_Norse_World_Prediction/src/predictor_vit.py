import torch
import torch.nn as nn
import numpy as np
from pathlib import Path
from typing import Any

from .scoring import apply_probability_floor
from .types import grid_value_to_class_index, NUM_CLASSES

class PatchEmbedding(nn.Module):
    def __init__(self, in_channels, patch_size, embed_dim, img_size):
        super().__init__()
        self.patch_size = patch_size
        self.num_patches = (img_size // patch_size) ** 2
        self.proj = nn.Conv2d(in_channels, embed_dim, kernel_size=patch_size, stride=patch_size)
        self.pos_embed = nn.Parameter(torch.randn(1, self.num_patches, embed_dim))

    def forward(self, x):
        # x: (B, C, H, W)
        x = self.proj(x) # (B, E, H/P, W/P)
        x = x.flatten(2).transpose(1, 2) # (B, num_patches, E)
        x = x + self.pos_embed
        return x

class ViTPredictor(nn.Module):
    def __init__(self, in_channels=20, out_channels=6, img_size=40, patch_size=4, embed_dim=256, depth=6, num_heads=8):
        super().__init__()
        self.patch_size = patch_size
        self.embed_dim = embed_dim
        self.grid_size = img_size // patch_size
        
        self.patch_embed = PatchEmbedding(in_channels, patch_size, embed_dim, img_size)
        
        encoder_layer = nn.TransformerEncoderLayer(d_model=embed_dim, nhead=num_heads, dim_feedforward=embed_dim*4, batch_first=True, norm_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=depth)
        
        # Decoding back to pixel space
        self.decoder_proj = nn.Linear(embed_dim, patch_size * patch_size * out_channels)

    def forward(self, x):
        B, C, H, W = x.shape
        
        # 1. Extract Patches and Add Position Embeddings
        tokens = self.patch_embed(x) # (B, N, E)
        
        # 2. Global Self-Attention
        tokens = self.transformer(tokens) # (B, N, E)
        
        # 3. Decode back to (B, Out_C, H, W)
        decoded = self.decoder_proj(tokens) # (B, N, P*P*Out_C)
        decoded = decoded.transpose(1, 2).contiguous() # (B, P*P*Out_C, N)
        decoded = decoded.view(B, -1, self.patch_size, self.patch_size, self.grid_size, self.grid_size)
        # B, Out_C, P_H, P_W, G_H, G_W
        decoded = decoded.permute(0, 1, 4, 2, 5, 3).contiguous()
        out = decoded.view(B, -1, H, W)
        
        return torch.log_softmax(out, dim=1)

_VIT_MODEL = None

def _load_vit(model_path: Path) -> ViTPredictor:
    global _VIT_MODEL
    if _VIT_MODEL is None:
        model = ViTPredictor(in_channels=20, out_channels=6)
        if model_path.is_file():
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()
        _VIT_MODEL = model
    return _VIT_MODEL

def build_prediction_tensor_vit(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 1e-5,
    model_path: Path | None = None,
) -> np.ndarray:
    if model_path is None:
        model_path = Path("data/reports/vit_predictor.pth")

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

    obs_mask = np.zeros((1, h, w), dtype=np.float32)
    obs_channels = np.zeros((6, h, w), dtype=np.float32)
    socio_channels = np.zeros((4, h, w), dtype=np.float32)

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
            obs_mask[0, vy:y2, vx:x2] = 1.0

            settlements = obs.get("settlements", [])
            for s in settlements:
                sx = int(s.get("x", -1))
                sy = int(s.get("y", -1))
                if 0 <= sx < w and 0 <= sy < h:
                    socio_channels[0, sy, sx] = float(s.get("population", 0.0) or 0.0)
                    socio_channels[1, sy, sx] = float(s.get("food", 0.0) or 0.0)
                    socio_channels[2, sy, sx] = float(s.get("wealth", 0.0) or 0.0)
                    socio_channels[3, sy, sx] = float(s.get("defense", 0.0) or 0.0)

        sums = obs_channels.sum(axis=0, keepdims=True)
        safe_sums = np.where(sums <= 0, 1.0, sums)
        obs_channels = obs_channels / safe_sums

    x_final = np.concatenate([x, dist[np.newaxis, :, :], obs_channels, socio_channels, obs_mask], axis=0)
    tensor_x = torch.from_numpy(x_final).unsqueeze(0)

    model = _load_vit(model_path)
    
    # TTA Averaging
    predictions = []
    with torch.no_grad():
        for k in range(4):
            for flip in [False, True]:
                x_aug = np.rot90(x, k, axes=(1, 2))
                dist_aug = np.rot90(dist, k)
                obs_channels_aug = np.rot90(obs_channels, k, axes=(1, 2))
                socio_channels_aug = np.rot90(socio_channels, k, axes=(1, 2))
                obs_mask_aug = np.rot90(obs_mask, k, axes=(1, 2))
                
                if flip:
                    x_aug = np.flip(x_aug, axis=2)
                    dist_aug = np.flip(dist_aug, axis=1)
                    obs_channels_aug = np.flip(obs_channels_aug, axis=2)
                    socio_channels_aug = np.flip(socio_channels_aug, axis=2)
                    obs_mask_aug = np.flip(obs_mask_aug, axis=2)
                    
                x_final_aug = np.concatenate([x_aug, dist_aug[np.newaxis, :, :], obs_channels_aug, socio_channels_aug, obs_mask_aug], axis=0)
                tensor_x_aug = torch.from_numpy(x_final_aug.copy()).unsqueeze(0)
                
                log_pred_aug = model(tensor_x_aug)
                pred_aug = torch.exp(log_pred_aug).squeeze(0).numpy()
                pred_aug = pred_aug.transpose((1, 2, 0))
                
                if flip:
                    pred_aug = np.flip(pred_aug, axis=1)
                pred_aug = np.rot90(pred_aug, -k, axes=(0, 1))
                predictions.append(pred_aug)
                
    pred = np.mean(predictions, axis=0)

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
            pred[valid] = 0.5 * local_probs + 0.5 * pred[valid]

    # Post-processing constraints
    pred[ocean_mask] = 0.0
    pred[ocean_mask, 0] = 1.0  
    
    mountain_mask = (grid == 5)
    pred[mountain_mask] = 0.0
    pred[mountain_mask, 5] = 1.0  
    
    inland_mask = (~coastal_mask) & (~ocean_mask)
    pred[inland_mask, 2] = 0.0

    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)

    return apply_probability_floor(pred, floor=1e-5)
