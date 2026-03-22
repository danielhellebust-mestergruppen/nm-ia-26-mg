echo "Running active-query comparison (8 queries, entropy policy) across all models..."
echo "--------------------------------------------------------"
printf "%-15s | %-15s | %-15s\n" "Model" "Active Score" "Delta vs 0-Obs"
echo "--------------------------------------------------------"

MODels="baseline spatial gnn convlstm unet attn_unet time_socio_unet"

for model in $MODels; do
    # Run the evaluator quietly, parsing the JSON report
    python scripts/offline_evaluator.py --predictor-mode $model --policies entropy --query-budget 8 --floor 1e-5 > /dev/null
    
    # Extract the score from the generated report
    SCORE=$(python -c 'import json; print(f"{json.load(open(\"data/reports/offline_evaluator_report.json\"))[\"entropy\"][\"mean_final_score\"]:.2f}")' 2>/dev/null)
    DELTA=$(python -c 'import json; print(f"{json.load(open(\"data/reports/offline_evaluator_report.json\"))[\"entropy\"][\"mean_score_delta\"]:.2f}")' 2>/dev/null)
    
    printf "%-15s | %-15s | %-15s\n" "$model" "$SCORE" "$DELTA"
done
echo "--------------------------------------------------------"
