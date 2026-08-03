# Soil-moisture trained vs untrained map comparison

Output folder: `/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/SM_comparison`

Dates: 2025-04-30, 2025-05-07, 2025-05-21, 2025-05-27, 2025-06-22, 2025-06-26, 2025-07-03, 2025-07-11, 2025-07-17

BBox: `148.918296 -35.108100 148.947784 -35.084795` (`W S E N`, EPSG:4326)

## Definition

- **Untrained**: the shipped model6 prediction maps from the independent validation run.
- **Trained**: a local residual-calibrated map. A `knn` residual
  corrector was fitted using all dense point/date observations and the actual
  model6 input features, then applied to every pixel.

This is a local calibration surface on top of model6, not full OzNet+local model
retraining.

Clip range applied to trained predictions: `0.0` to `60.0`.

## Point-level fit used for the local correction

| metric | untrained model6 | trained `local_residual_knn12` | delta |
|---|---:|---:|---:|
| NSE / R² | 0.023 | 0.648 | 0.625 |
| Pearson r | 0.238 | 0.819 | 0.580 |
| RMSE | 6.477 | 3.890 | -2.587 |
| ubRMSE | 6.453 | 3.890 | -2.563 |
| bias | -0.558 | 0.032 | 0.590 |

Because the correction is fitted to all local point observations, these point
metrics are in-sample and should be read as the strength of local calibration,
not independent validation.

## Outputs

- `untrained_model6/` — copied original model6 GeoTIFFs.
- `trained_local_residual_knn12/` — locally trained/calibrated soil-moisture GeoTIFFs.
- `local_residual_knn12_correction/` — correction surfaces (`trained - untrained`).
- `multiband_local_residual_knn12/` — one three-band GeoTIFF per date: untrained, trained, correction.
- `figures_local_residual_knn12/` — quick-look PNG triptychs for each date.
- `point_predictions_trained_vs_untrained.csv` — point-level before/after predictions.
- `raster_summary.csv` — map-level mean/min/max correction summary.
