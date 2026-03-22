import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pathlib import Path
from typing import Any

from .scoring import apply_probability_floor
from .types import grid_value_to_class_index, NUM_CLASSES

class MessagePassingLayer(nn.Module):
    """
    A Graph Attention Network (GAT) message passing layer for a 4-connected grid.
    Learns dynamic edge weights so that messages traverse correctly (e.g. blocking 
    messages across mountains, or flowing freely along coastlines).
    """
    def __init__(self, in_features, out_features):
        super().__init__()
        self.node_conv = nn.Conv2d(in_features, out_features, 1)
        self.edge_conv = nn.Conv2d(in_features, out_features, 1)
        
        # Shared attention mechanism (to keep parameters low but effective)
        # It looks at the concatenation of (node_i, node_j) to determine the weight
        self.att_conv = nn.Sequential(
            nn.Conv2d(in_features * 2, 16, 1),
            nn.LeakyReLU(0.2),
            nn.Conv2d(16, 1, 1),
            nn.Sigmoid()
        )
        
        self.update_conv = nn.Conv2d(out_features * 2, out_features, 1)
        self.norm = nn.GroupNorm(1, out_features) # Equivalent to LayerNorm for Conv2d

    def forward(self, x):
        B, C, H, W = x.shape
        
        node_features = self.node_conv(x)
        edge_features = self.edge_conv(x)
        
        # Shift original features to get neighbor states for Attention
        x_up = torch.cat([torch.zeros_like(x[:, :, :1, :]), x[:, :, :-1, :]], dim=2)
        x_down = torch.cat([x[:, :, 1:, :], torch.zeros_like(x[:, :, :1, :])], dim=2)
        x_left = torch.cat([torch.zeros_like(x[:, :, :, :1]), x[:, :, :, :-1]], dim=3)
        x_right = torch.cat([x[:, :, :, 1:], torch.zeros_like(x[:, :, :, :1])], dim=3)
        
        # Shift edge features (the actual messages being sent)
        msg_up = torch.cat([torch.zeros_like(edge_features[:, :, :1, :]), edge_features[:, :, :-1, :]], dim=2)
        msg_down = torch.cat([edge_features[:, :, 1:, :], torch.zeros_like(edge_features[:, :, :1, :])], dim=2)
        msg_left = torch.cat([torch.zeros_like(edge_features[:, :, :, :1]), edge_features[:, :, :, :-1]], dim=3)
        msg_right = torch.cat([edge_features[:, :, :, 1:], torch.zeros_like(edge_features[:, :, :, :1])], dim=3)
        
        # Calculate dynamic edge weights (Attention)
        alpha_up = self.att_conv(torch.cat([x, x_up], dim=1))
        alpha_down = self.att_conv(torch.cat([x, x_down], dim=1))
        alpha_left = self.att_conv(torch.cat([x, x_left], dim=1))
        alpha_right = self.att_conv(torch.cat([x, x_right], dim=1))
        
        # Optionally normalize alpha? For now, independent sigmoid gating works well.
        
        # Aggregate weighted messages
        aggr_messages = (msg_up * alpha_up) + (msg_down * alpha_down) +                         (msg_left * alpha_left) + (msg_right * alpha_right)
        
        combined = torch.cat([node_features, aggr_messages], dim=1)
        
        new_nodes = self.update_conv(combined)
        new_nodes = F.relu(self.norm(new_nodes))
        
        # Residual connection
        if x.shape[1] == new_nodes.shape[1]:
            new_nodes = new_nodes + x
            
        return new_nodes

class GridGNN(nn.Module):
    def __init__(self, in_channels=16, hidden_channels=64, out_channels=6, num_layers=8):
        super().__init__()
        self.proj_in = nn.Conv2d(in_channels, hidden_channels, kernel_size=1)
        
        self.mp_layers = nn.ModuleList([
            MessagePassingLayer(hidden_channels, hidden_channels) for _ in range(num_layers)
        ])
        
        self.proj_out = nn.Sequential(
            nn.Conv2d(hidden_channels * 2, hidden_channels, kernel_size=1),
            nn.ReLU(),
            nn.Conv2d(hidden_channels, out_channels, kernel_size=1)
        )
        
    def forward(self, x):
        h = self.proj_in(x)
        for layer in self.mp_layers:
            h = layer(h)
            
        # Global Readout + Broadcast
        global_context = h.mean(dim=(2, 3), keepdim=True)
        h_combined = torch.cat([h, global_context.expand_as(h)], dim=1)
        
        out = self.proj_out(h_combined)
        return torch.log_softmax(out, dim=1)

_GNN_MODEL = None

def _load_gnn(model_path: Path) -> GridGNN:
    global _GNN_MODEL
    if _GNN_MODEL is None:
        model = GridGNN(in_channels=16, out_channels=6)
        if model_path.is_file():
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
        model.eval()
        _GNN_MODEL = model
    return _GNN_MODEL

def build_prediction_tensor_gnn(
    initial_grid: list[list[int]],
    observations: list[dict[str, Any]],
    floor: float = 0.01,
    model_path: Path | None = None,
) -> np.ndarray:
    """
    Drop-in replacement for UNet/Spatial predictors. 
    Models the map natively as a graph to let features traverse paths 
    organically rather than via receptive fields.
    """
    if model_path is None:
        model_path = Path("data/reports/gnn_predictor.pth")
    
    grid = np.asarray(initial_grid, dtype=np.int64)
    h, w = grid.shape
    
    mapping = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 10: 6, 11: 7}
    channels = 8
    x_base = np.zeros((channels, h, w), dtype=np.float32)
    for y in range(h):
        for x_idx in range(w):
            v = grid[y, x_idx]
            c = mapping.get(int(v), 0)
            x_base[c, y, x_idx] = 1.0
            
    # Distance to Coast channel
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
    
    # Observations Channels
    obs_mask = np.zeros((1, h, w), dtype=np.float32)
    obs_channels = np.zeros((6, h, w), dtype=np.float32)
    
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
            
        sums = obs_channels.sum(axis=0, keepdims=True)
        safe_sums = np.where(sums <= 0, 1.0, sums)
        obs_channels = obs_channels / safe_sums
    
    x_final = np.concatenate([x_base, dist[np.newaxis, :, :], obs_channels, obs_mask], axis=0)
    tensor_x = torch.from_numpy(x_final).unsqueeze(0)
    
    model = _load_gnn(model_path)
    with torch.no_grad():
        log_pred = model(tensor_x)
        pred = torch.exp(log_pred).squeeze(0).numpy()
        
    pred = pred.transpose((1, 2, 0))
    
    # Process observations post-network (Ensemble)
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
            # Lean more heavily on observed truth
            pred[valid] = 0.5 * local_probs + 0.5 * pred[valid]

    # Hard constraints (Confirmed facts)
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
    
    sums = pred.sum(axis=-1, keepdims=True)
    pred = pred / np.where(sums <= 0, 1.0, sums)
            
    return apply_probability_floor(pred, floor=floor)