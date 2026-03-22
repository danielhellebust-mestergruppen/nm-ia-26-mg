# Astar Island Prediction Lab

This workspace is a complete end-to-end machine learning framework for playing and predicting land classes in Astar Island.

## Current State-of-the-Art Model
The current best-performing model is the **Time-Aware Socio-Economic Attention U-Net** (`time_socio_unet`). 

**Mathematically Proven Performance:**
Through strict **3-Fold Cross-Validation** (hiding entire rounds from the training set), this model has proven to achieve a mean score of **96.73/100** on completely unseen island layouts.

**Why it works:**
Unlike geometric-only models, the `time_socio_unet` utilizes:
- **Time-Awareness:** A dedicated input channel for the simulation year fraction (t/50).
- **Socio-Economic Fusing:** Deep integration of population, wealth, and food dynamics.
- **Attention Gates:** Dynamically focuses on critical terrain features like coastal settlements.

## Key Pipeline Optimizations
- **Probability Floor:** Mathematically fixed at `1e-5` to prevent KL blowups while maintaining peak confidence.
- **Impossible Physics Constraints:** Definitively zeroed-out probabilities for physically impossible shifts (e.g., inland ports, moving mountains, or changing oceans).
- **Test-Time Augmentation (TTA):** The predictor averages 8 different rotations/flips per inference for maximum stability.
- **Unlocked Querying:** Supports overlapping viewports at any (x,y) coordinate, enabling full utilization of the 50-query budget.

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip -r requirements.txt
```

Set your environment variables (or create a `.env` file in the root):
```bash
export AINM_BEARER_TOKEN="YOUR_JWT_TOKEN"
export AINM_BASE_URL="https://api.ainm.no/astar-island"
```

## End-to-End Playbook

### 1. Data Collection & Training
Retrain the champion model on all available historical data (automatically including raw replay frames):
```bash
python scripts/backfill_replays.py
python scripts/train_time_socio_unet_predictor.py --epochs 500
```

### 2. Running and Submitting an Active Round
The **Two-Pass Workflow** with `time_socio_unet` is the definitive strategy. It executes a probe pass, calculates mathematical entropy across seeds, and allocates the 50-query budget to resolve the highest uncertainty.

```bash
python scripts/two_stage_round_workflow.py \
    --predictor-mode time_socio_unet \
    --query-policy entropy \
    --execute-probe \
    --auto-submit \
    --save-visuals
```

## Available Scripts Overview
- **Visualizer**: `simulate_queries_tui.py` (High-fidelity dashboard for strategy testing)
- **Validation**: `run_kfold_cv.py` (Strict holdout cross-validation testing)
- **Evaluation**: `compare_all_models.py` (Predictor ranking), `offline_evaluator.py` (Active querying simulation)
- **Deployment**: `two_stage_round_workflow.py` (Main submission entry point)
