#!/usr/bin/env python3
import json
import numpy as np
from pathlib import Path
import sys
import math
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

# Import all predictors
from src.predictor_baseline import build_prediction_tensor
from src.predictor_spatial import build_prediction_tensor_spatial
from src.predictor_unet import build_prediction_tensor_unet
try:
    from src.predictor_attention_unet import build_prediction_tensor_attn_unet
except ImportError:
    build_prediction_tensor_attn_unet = None

try:
    from src.predictor_convlstm import build_prediction_tensor_convlstm
except ImportError:
    build_prediction_tensor_convlstm = None

try:
    from src.predictor_time_socio_unet import build_prediction_tensor_time_socio_unet
except ImportError:
    build_prediction_tensor_time_socio_unet = None

try:
    from src.predictor_socio_unet import build_prediction_tensor_socio_unet
except ImportError:
    build_prediction_tensor_socio_unet = None

try:
    from src.predictor_time_socio_deep_unet import build_prediction_tensor_time_socio_deep_unet
except ImportError:
    build_prediction_tensor_time_socio_deep_unet = None

try:
    from src.predictor_vit import build_prediction_tensor_vit
except ImportError:
    build_prediction_tensor_vit = None
    
from src.predictor_gnn import build_prediction_tensor_gnn
from src.scoring import weighted_kl, score_from_weighted_kl

def main():
    rounds_dir = Path("data/rounds")
    files = list(rounds_dir.glob("*_analysis.json"))
    
    if not files:
        print("No rounds found for comparison.")
        return

    print(f"Comparing predictors across {len(files)} completed rounds/seeds...")
    
    scores = defaultdict(list)
    kls = defaultdict(list)
    
    for fp in sorted(files):
        data = json.loads(fp.read_text(encoding="utf-8"))
        if "ground_truth" not in data or "initial_grid" not in data:
            continue
            
        initial_grid = data["initial_grid"]
        gt = np.asarray(data["ground_truth"])
        
        # We test Zero-Observation prediction (Pure prior modeling)
        # 1. Baseline
        pred_base = build_prediction_tensor(initial_grid, [])
        scores["Baseline"].append(score_from_weighted_kl(weighted_kl(gt, pred_base)))
        kls["Baseline"].append(weighted_kl(gt, pred_base))
        
        # 2. Spatial
        pred_spat = build_prediction_tensor_spatial(initial_grid, [])
        scores["Spatial"].append(score_from_weighted_kl(weighted_kl(gt, pred_spat)))
        kls["Spatial"].append(weighted_kl(gt, pred_spat))
        
        # 3. Standard UNet
        pred_unet = build_prediction_tensor_unet(initial_grid, [])
        scores["UNet"].append(score_from_weighted_kl(weighted_kl(gt, pred_unet)))
        kls["UNet"].append(weighted_kl(gt, pred_unet))
        
        # 4. Attention UNet
        if build_prediction_tensor_attn_unet:
            pred_attn = build_prediction_tensor_attn_unet(initial_grid, [])
            scores["Attn-UNet"].append(score_from_weighted_kl(weighted_kl(gt, pred_attn)))
            kls["Attn-UNet"].append(weighted_kl(gt, pred_attn))
            
        # 5. GNN (Graph Neural Network)
        pred_gnn = build_prediction_tensor_gnn(initial_grid, [])
        scores["GNN"].append(score_from_weighted_kl(weighted_kl(gt, pred_gnn)))
        kls["GNN"].append(weighted_kl(gt, pred_gnn))
        
        # 6. ConvLSTM
        if build_prediction_tensor_convlstm:
            pred_convlstm = build_prediction_tensor_convlstm(initial_grid, [])
            scores["ConvLSTM"].append(score_from_weighted_kl(weighted_kl(gt, pred_convlstm)))
            kls["ConvLSTM"].append(weighted_kl(gt, pred_convlstm))
            
        # 6.5 Time-Socio UNet
        if build_prediction_tensor_time_socio_unet:
            pred_time = build_prediction_tensor_time_socio_unet(initial_grid, [])
            scores["Time-Socio"].append(score_from_weighted_kl(weighted_kl(gt, pred_time)))
            kls["Time-Socio"].append(weighted_kl(gt, pred_time))

        # 6.75 Socio UNet
        if build_prediction_tensor_socio_unet:
            pred_socio = build_prediction_tensor_socio_unet(initial_grid, [])
            scores["Socio-UNet"].append(score_from_weighted_kl(weighted_kl(gt, pred_socio)))
            kls["Socio-UNet"].append(weighted_kl(gt, pred_socio))
            
        # 6.8 Time-Socio Deep UNet
        if build_prediction_tensor_time_socio_deep_unet:
            pred_deep = build_prediction_tensor_time_socio_deep_unet(initial_grid, [])
            scores["Deep-Time-Socio"].append(score_from_weighted_kl(weighted_kl(gt, pred_deep)))
            kls["Deep-Time-Socio"].append(weighted_kl(gt, pred_deep))
        
        # 6.75 ViT
        if build_prediction_tensor_vit:
            pred_vit = build_prediction_tensor_vit(initial_grid, [])
            scores["ViT"].append(score_from_weighted_kl(weighted_kl(gt, pred_vit)))
            kls["ViT"].append(weighted_kl(gt, pred_vit))
            
        # 7. Ensemble (Sweeping ratios)
        if build_prediction_tensor_time_socio_unet:
            for w_gnn in [0.1, 0.2, 0.3, 0.4]:
                pred_ensemble = ((1.0 - w_gnn) * pred_time) + (w_gnn * pred_gnn)
                pred_ensemble = pred_ensemble / pred_ensemble.sum(axis=-1, keepdims=True)
                key = f"Ensemble (GNN {w_gnn:.1f})"
                scores[key].append(score_from_weighted_kl(weighted_kl(gt, pred_ensemble)))
                kls[key].append(weighted_kl(gt, pred_ensemble))

    print("\\n--- FINAL COMPARISON (ZERO OBSERVATIONS) ---")
    print(f"{'Model':<20} | {'Avg Score (/100)':<18} | {'Avg KL Divergence'}")
    print("-" * 60)
    
    models_to_print = ["Baseline", "Spatial", "UNet", "Attn-UNet", "GNN", "ConvLSTM", "Time-Socio", "Deep-Time-Socio", "Socio-UNet", "ViT"] + [f"Ensemble (GNN {w:.1f})" for w in [0.1, 0.2, 0.3, 0.4]]
    for model in models_to_print:
        if model in scores:
            avg_score = np.mean(scores[model])
            avg_kl = np.mean(kls[model])
            print(f"{model:<15} | {avg_score:>18.2f} | {avg_kl:.4f}")

if __name__ == "__main__":
    main()
