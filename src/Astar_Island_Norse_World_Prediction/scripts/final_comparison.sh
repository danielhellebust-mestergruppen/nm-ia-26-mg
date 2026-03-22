#!/bin/bash
echo "--- ZERO QUERIES (BLIND PREDICTION) ---"
for mode in baseline spatial unet convlstm attn_unet; do
  echo -n "$mode: "
  .venv/bin/python scripts/offline_evaluator.py --predictor-mode $mode --policies grid --query-budget 0 --limit-samples 40 | grep "mean_final_score" | awk '{print $2}' | tr -d ','
done

echo ""
echo "--- 8 QUERIES (ENTROPY POLICY) ---"
for mode in baseline spatial unet_spatial attn_unet_spatial; do
  echo -n "$mode: "
  .venv/bin/python scripts/offline_evaluator.py --predictor-mode $mode --policies entropy --query-budget 8 --limit-samples 40 | grep "mean_final_score" | awk '{print $2}' | tr -d ','
done
