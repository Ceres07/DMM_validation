# Dense-site model6 retrain with more leaves

This folder contains a local retrain of model6-style `HistGradientBoostingRegressor`
on the dense point dataset.

## Selected local model

| parameter | value |
|---|---:|
| max_leaf_nodes | 511 |
| min_samples_leaf | 20 |
| max_iter | 300 |
| max_features | 0.3 |

The leaf sweep found that 127, 255, 511 and unlimited leaves produce effectively
the same held-out score at a fixed `min_samples_leaf`. For this dense device
dataset, the practical limit is sample support per leaf rather than the explicit
leaf cap. I therefore used 511 leaves with `min_samples_leaf=20`: more expressive
than the shipped cap, but still supported by the local sample size.

## Point-level performance

| metric | shipped/untrained model6 | local model6 more-leaves fit | delta |
|---|---:|---:|---:|
| NSE / R² | 0.023 | 0.959 | 0.936 |
| Pearson r | 0.238 | 0.980 | 0.741 |
| RMSE | 6.477 | 1.320 | -5.158 |
| bias | -0.558 | 0.000 | 0.558 |

The final-fit metrics are in-sample. Use the leaf-sweep GroupKFold results below
for a less optimistic held-out estimate.

## Best GroupKFold leaf-sweep settings

| max_leaf_nodes | min_samples_leaf | rmse | ubrmse | bias | r | nse | n |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 127 | 20 | 3.565 | 3.564 | 0.113 | 0.841 | 0.704 | 560 |
| 255 | 20 | 3.565 | 3.564 | 0.113 | 0.841 | 0.704 | 560 |
| 511 | 20 | 3.565 | 3.564 | 0.113 | 0.841 | 0.704 | 560 |
| None | 20 | 3.565 | 3.564 | 0.113 | 0.841 | 0.704 | 560 |
| 127 | 10 | 3.579 | 3.570 | 0.257 | 0.840 | 0.702 | 560 |
| 255 | 10 | 3.579 | 3.570 | 0.257 | 0.840 | 0.702 | 560 |
| 511 | 10 | 3.579 | 3.570 | 0.257 | 0.840 | 0.702 | 560 |
| None | 10 | 3.579 | 3.570 | 0.257 | 0.840 | 0.702 | 560 |
| 127 | 5 | 3.605 | 3.600 | 0.199 | 0.838 | 0.697 | 560 |
| 255 | 5 | 3.605 | 3.600 | 0.199 | 0.838 | 0.697 | 560 |
| 511 | 5 | 3.605 | 3.600 | 0.199 | 0.838 | 0.697 | 560 |
| None | 5 | 3.605 | 3.600 | 0.199 | 0.838 | 0.697 | 560 |

## Outputs

- `model6_more_leaves_dense_points.joblib` — fitted local model.
- `leaf_sweep_groupkfold.csv` — point-group held-out leaf sweep.
- `leaf_sweep_predictions.csv` — out-of-fold predictions for all sweep settings.
- `point_predictions_model6_more_leaves.csv` — point-level shipped vs local predictions.
- `trained_model6_more_leaves/` — direct local retrained prediction GeoTIFFs.
- `trained_minus_untrained/` — local retrain minus shipped model6 GeoTIFFs.
- `multiband/` — three-band GeoTIFFs: shipped model6, retrained model6, difference.
- `figures/` — quick-look PNG triptychs.
- `raster_summary.csv` — map-level mean/min/max differences.

## Caveat

This is a local dense-site retrain against the dense point observations. It is
not a replacement for the national OzNet-trained model unless its transfer skill
is separately validated outside this site.
