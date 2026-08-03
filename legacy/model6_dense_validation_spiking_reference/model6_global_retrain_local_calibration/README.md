# model6 global retrain vs dense local calibration

Generated: 2026-07-24T10:25:23

Output folder: `/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/model6_global_retrain_local_calibration`

Dense input table: `/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/Validation_2stage/stage1_dense_unseen_validation/point_date_model_inputs.csv`

This comparison uses the same dense point/date model-input table for both
baselines:

- **Original global model6**: extracted from `HEAD:data/models/model6.joblib`.
- **Retrained global model6**: current working `data/models/model6.joblib`, fitted
  on the locally rebuilt OzNet training table with a larger leaf cap.
- **Local calibration**: `knn` residual corrector using model6 inputs plus
  the relevant global prediction. The primary less-optimistic score is
  point-group held-out GroupKFold with `5` folds.

SILO configuration for any map-input generation: using existing PaddockTS SILO email/config.

## Short answer

- Global retraining changed dense-site global-only performance: **worsened**.
- After dense local residual calibration, retraining changed point-group held-out
  local calibration performance: **roughly unchanged**.

## Global model parameters

The original global model is still available from git and was copied into
`models/model6_original_from_git_HEAD.joblib`.

| parameter | original global | retrained global |
|---|---:|---:|
| max_leaf_nodes | 127 | 255 |
| min_samples_leaf | 20 | 20 |
| max_iter | 200 | 200 |
| max_features | 0.15 | 0.15 |
| learning_rate | 0.03 | 0.03 |
| l2_regularization | 1.0 | 1.0 |

Existing dense-validation `pred_sm_pct` vs original model re-prediction:

```json
{
  "n_compared": 560,
  "mean_existing_minus_original_reprediction": 0.0006946752841113599,
  "max_abs_existing_minus_original_reprediction": 0.07122492385308377
}
```

## Point-level metrics

Bias follows the EMT convention: prediction minus observation.

| baseline | prediction | rmse | ubrmse | bias | r | nse_r2 | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| original | global | 6.477 | 6.453 | -0.559 | 0.239 | 0.023 | 560 |
| original | local_insample | 3.890 | 3.890 | 0.033 | 0.819 | 0.648 | 560 |
| original | local_groupkfold | 4.166 | 4.166 | 0.029 | 0.777 | 0.596 | 560 |
| retrained | global | 6.578 | 6.550 | -0.600 | 0.214 | -0.007 | 560 |
| retrained | local_insample | 3.889 | 3.889 | 0.035 | 0.819 | 0.648 | 560 |
| retrained | local_groupkfold | 4.188 | 4.188 | 0.029 | 0.773 | 0.592 | 560 |

## Retrained minus original deltas

Positive delta NSE/R² is good; negative delta RMSE/ubRMSE/abs_bias is good.

| comparison | delta_rmse | delta_ubrmse | delta_abs_bias | delta_r | delta_nse_r2 |
| --- | --- | --- | --- | --- | --- |
| retrained - original (global) | 0.101 | 0.097 | 0.041 | -0.025 | -0.031 |
| retrained - original (local_insample) | -0.001 | -0.001 | 0.002 | 0.000 | 0.000 |
| retrained - original (local_groupkfold) | 0.022 | 0.022 | -0.000 | -0.004 | -0.004 |

## Outputs

- `models/` — original-from-git and current retrained model artefact copies plus JSON params.
- `point_calibration/point_predictions_comparison.csv` — dense point predictions for both global baselines and local calibration variants.
- `point_calibration/metrics_summary.csv` — point-level metric table.
- `point_calibration/retrained_minus_original_deltas.csv` — metric deltas.
- `maps/` — GeoTIFF maps for the global and locally calibrated predictions, plus difference rasters.
- `figures/` — quick-look PNG comparison panels per date.
- `map_summary.csv` — map-level mean/min/max for each raster layer.

## Interpretation note

The local in-sample calibration rows tell us how strongly the dense data can
calibrate the site if all local observations are allowed into the residual
surface. The point-group held-out rows are the better test of whether that local
calibration transfers to unseen point locations inside the same dense site.

## Map-level mean differences

| date | global_retrained_minus_original_mean | local_retrained_minus_original_mean | local_gain_original_mean | local_gain_retrained_mean | valid_pixels |
| --- | --- | --- | --- | --- | --- |
| 2025-04-30 | -0.125 | 0.002 | 3.540 | 3.668 | 8693 |
| 2025-05-07 | -0.104 | -0.022 | -0.836 | -0.754 | 8693 |
| 2025-05-21 | -0.098 | -0.106 | -5.238 | -5.246 | 8693 |
| 2025-05-27 | -0.412 | -0.023 | 2.571 | 2.960 | 8693 |
| 2025-06-22 | -0.268 | -0.180 | 0.643 | 0.731 | 8693 |
| 2025-06-26 | 0.013 | 0.030 | 3.066 | 3.083 | 8693 |
| 2025-07-03 | 0.136 | 0.131 | 2.433 | 2.429 | 8693 |
| 2025-07-11 | -0.120 | -0.100 | 2.783 | 2.804 | 8693 |
| 2025-07-17 | 0.074 | 0.053 | 2.305 | 2.284 | 8693 |
