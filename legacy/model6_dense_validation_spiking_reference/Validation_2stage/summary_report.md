# Model6 dense-point validation and local spiking analysis

Output folder: `/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking`

Source validation folder: `/Volumes/Dmitry_work/borevitz_projects/Data/soilmoisture_points_validation`

Git branch: `EMT`

## Executive summary

The analysis is implemented in two stages.

1. **Dense unseen-site validation:** model6 was evaluated against the high-density
   point dataset without using those points for model fitting. The validation
   rasters and tables map where the model transfers well or poorly across the
   site. Bias diagnostics use the model's own inputs — terrain, SLGA soil,
   SMIPS lookbacks, antecedent weather and seasonality — rather than the
   auxiliary terrain columns in the field CSV.
2. **Local-data spiking sensitivity:** local observations were supplied in
   increasing amounts to residual-calibration experiments to quantify how much
   local information improves predictions at held-out locations or later dates.

## Stage 1 — unseen dense-point validation

Pooled model6 skill against the dense point dataset:

| metric | value |
|---|---:|
| NSE / R² | 0.023 |
| Pearson r | 0.238 |
| RMSE | 6.477 |
| ubRMSE | 6.453 |
| bias | -0.558 |
| n | 560 |

Per-point summary:

- positive NSE/R² points: 43/79
- very poor NSE/R² points (≤ -1): 13/79
- median |bias|: 2.26 %

### Best points by NSE/R²

| point | nse | r | bias | rmse | lon | lat | quality_class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 6e | 0.457 | 0.811 | 0.560 | 2.785 | 148.921 | -35.104 | positive |
| 20o | 0.448 | 0.813 | 0.377 | 4.118 | 148.933 | -35.088 | positive |
| 37o | 0.412 | 0.738 | -1.199 | 4.951 | 148.933 | -35.087 | positive |
| 4e | 0.384 | 0.773 | -0.414 | 4.337 | 148.926 | -35.094 | positive |
| 36e | 0.369 | 0.707 | -0.096 | 5.084 | 148.934 | -35.087 | positive |
| 32e | 0.354 | 0.769 | 0.329 | 5.170 | 148.921 | -35.105 | positive |
| 8e | 0.335 | 0.771 | 0.423 | 6.999 | 148.941 | -35.088 | positive |
| 17o | 0.297 | 0.595 | 0.264 | 4.905 | 148.931 | -35.088 | positive |
| 29e | 0.286 | 0.754 | -0.887 | 3.735 | 148.931 | -35.096 | positive |
| 22e | 0.284 | 0.751 | 1.146 | 5.604 | 148.927 | -35.097 | positive |

### Worst points by NSE/R²

| point | nse | r | bias | rmse | lon | lat | quality_class |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 13o | -3.114 | 0.705 | -11.072 | 12.370 | 148.937 | -35.094 | very_poor |
| 15o | -2.568 | 0.461 | -6.294 | 7.130 | 148.931 | -35.097 | very_poor |
| 25o | -2.172 | 0.753 | -10.440 | 11.588 | 148.924 | -35.087 | very_poor |
| 18e | -1.838 | 0.592 | -10.191 | 12.121 | 148.932 | -35.094 | very_poor |
| 12o | -1.820 | 0.664 | -6.786 | 7.702 | 148.931 | -35.106 | very_poor |
| 33o | -1.592 | 0.706 | -7.889 | 9.039 | 148.928 | -35.106 | very_poor |
| 24o | -1.520 | 0.759 | 6.508 | 7.347 | 148.933 | -35.099 | very_poor |
| 35o | -1.475 | 0.307 | 5.953 | 7.663 | 148.932 | -35.098 | very_poor |
| 37e | -1.415 | 0.598 | 7.031 | 8.371 | 148.941 | -35.088 | very_poor |
| 19o | -1.316 | 0.345 | -7.119 | 9.048 | 148.926 | -35.100 | very_poor |

### Strongest model-input associations with point NSE/R²

| model_input | pearson_r | spearman_r | n_points |
| --- | --- | --- | --- |
| twi | -0.330 | -0.303 | 77 |
| northness | -0.324 | -0.355 | 77 |
| smips_365d | -0.318 | -0.334 | 77 |
| slope | 0.306 | 0.315 | 77 |
| soil_bdw | 0.282 | 0.265 | 77 |
| smips_anom | 0.264 | 0.354 | 77 |
| hli | -0.257 | -0.156 | 77 |
| soil_clay | 0.223 | 0.181 | 77 |
| eastness | -0.194 | -0.034 | 77 |
| smips_7d | -0.169 | -0.170 | 77 |

### Antecedent meteorology associations with point NSE/R²

| model_input | pearson_r | spearman_r | n_points |
| --- | --- | --- | --- |
| ppet_365 | 0.133 | 0.183 | 77 |
| rain_365_anom | 0.125 | 0.180 | 77 |
| rain_365 | 0.125 | 0.181 | 77 |
| rain_7 | 0.104 | 0.328 | 77 |
| vpd_30 | 0.038 | -0.129 | 77 |
| rain_30 | 0.025 | 0.170 | 77 |
| ppet_30 | -0.022 | 0.123 | 77 |

### Antecedent meteorology associations with bias and |bias|

| model_input | quality_metric | pearson_r | spearman_r | n_points |
| --- | --- | --- | --- | --- |
| ppet_365 | abs_bias | -0.183 | -0.125 | 77 |
| rain_365 | abs_bias | -0.172 | -0.118 | 77 |
| rain_365_anom | abs_bias | -0.164 | -0.116 | 77 |
| rain_7 | abs_bias | -0.052 | -0.191 | 77 |
| vpd_30 | abs_bias | -0.052 | 0.026 | 77 |
| ppet_30 | abs_bias | 0.034 | 0.002 | 77 |
| rain_30 | abs_bias | -0.030 | -0.080 | 77 |
| ppet_365 | bias | -0.217 | -0.194 | 77 |
| rain_365 | bias | -0.215 | -0.190 | 77 |
| rain_365_anom | bias | -0.203 | -0.195 | 77 |
| rain_30 | bias | -0.117 | -0.115 | 77 |
| vpd_30 | bias | 0.106 | 0.109 | 77 |
| ppet_30 | bias | -0.097 | -0.051 | 77 |
| rain_7 | bias | -0.011 | 0.034 | 77 |

Interpretation: this is an exploratory bias screen. Strong associations indicate
where model6 may be systematically over- or under-performing in its own input
space, but they are not causal by themselves.

## Stage 2 — sensitivity to local training-data spiking

Two local spiking experiments were run:

1. **Spatial spiking:** for each target point, the target point was held out.
   Increasing numbers of other local points were supplied as calibration data.
   Points were selected by four strategies: nearest in space, most similar in
   model-input terrain/soil space, stratified coverage of model-input space, and
   random selection.
2. **Temporal self-spiking:** for each point, the first few observations at that
   same location were supplied as calibration data and later dates were held out.

The implemented spiking mechanism is residual calibration of the shipped model6
predictions, not full OzNet+local retraining, because the canonical OzNet
training table was not present in this checkout. The feature table produced here
can be appended to a rebuilt OzNet table for a full retraining experiment.

### Best spatial spiking settings by median ΔNSE/R²

| strategy | method | spike_points | median_delta_nse | median_delta_rmse | median_delta_abs_bias | positive_nse_fits |
| --- | --- | --- | --- | --- | --- | --- |
| terrain_stratified | ridge_residual | 40 | 0.695 | -2.771 | -0.586 | 63 |
| terrain_similar | ridge_residual | 40 | 0.695 | -2.770 | -0.504 | 63 |
| nearest | ridge_residual | 40 | 0.678 | -2.848 | -0.280 | 64 |
| nearest | ridge_residual | 20 | 0.663 | -2.714 | 0.107 | 61 |
| terrain_similar | ridge_residual | 20 | 0.657 | -2.572 | -0.352 | 65 |
| random | ridge_residual | 40 | 0.638 | -2.604 | -0.163 | 648 |
| nearest | ridge_residual | 5 | 0.606 | -2.320 | 0.591 | 57 |
| nearest | ridge_residual | 3 | 0.604 | -2.475 | 0.100 | 59 |
| nearest | ridge_residual | 10 | 0.599 | -2.187 | 0.478 | 58 |
| terrain_similar | ridge_residual | 3 | 0.579 | -2.543 | 0.128 | 57 |
| terrain_stratified | ridge_residual | 20 | 0.571 | -2.285 | 0.467 | 62 |
| random | ridge_residual | 20 | 0.564 | -2.163 | 0.233 | 591 |

For random selection, `positive_nse_fits` counts repeated target/replicate fits;
for deterministic strategies, it is equivalent to the number of target points.
The ridge residual corrector is useful for sensitivity testing but can be
unstable with very small temporal spike counts; the bias-only corrector is the
more conservative low-data benchmark.

### Best temporal self-spiking settings by median ΔNSE/R²

| method | training_dates | median_delta_nse | median_delta_rmse | median_delta_abs_bias | positive_nse_points |
| --- | --- | --- | --- | --- | --- |
| ridge_residual | 5 | 2.485 | -1.214 | -1.372 | 15 |
| bias_only | 5 | 0.574 | -0.286 | -0.636 | 3 |
| bias_only | 4 | 0.322 | -0.507 | -0.655 | 26 |
| bias_only | 3 | 0.085 | -0.129 | -0.386 | 15 |
| bias_only | 2 | -0.016 | 0.066 | 0.404 | 50 |
| bias_only | 1 | -1.613 | 3.614 | 5.120 | 5 |
| ridge_residual | 1 | -1.613 | 3.614 | 5.120 | 5 |
| ridge_residual | 4 | -9.937 | 5.901 | 6.421 | 1 |

## Research novelty

High-novelty components:

- The dense point dataset supports sub-grid validation of a downscaled soil
  moisture product, rather than only sparse station validation.
- Mapping NSE/R², bias and RMSE at dense point locations exposes where a
  national gridded model succeeds or fails within a single high-density terrain
  mosaic.
- The local-data spiking curves quantify the marginal value of adding local
  measurements, including whether spatial proximity or model-input similarity is
  the better guide for calibration sampling.
- Temporal self-spiking estimates how many local visits are needed before a
  specific point becomes locally reliable.

Comparable-to-existing-study components:

- Use of held-out independent observations and standard soil-moisture metrics
  such as RMSE, ubRMSE, bias, correlation and NSE/R².
- Use of terrain, soil, coarse soil-moisture products and antecedent weather as
  predictors for statistical downscaling.
- Cross-validation concepts that hold out space or time to assess transfer.

## Full utilisation of the dense spatial point dataset

The dataset is used as:

1. an independent validation target;
2. a spatial bias map of point-wise model quality;
3. a model-input-space diagnostic for terrain/soil/antecedent bias;
4. a source of controlled local calibration spikes;
5. a basis for learning curves that estimate the minimum local sampling density
   needed to improve prediction at specific locations.

## Caveat

Model6 was trained on OzNet root-zone soil moisture, while the dense point CSV
appears to represent shallower measurements. Treat these results as an external
terrain-transfer and calibration-sensitivity diagnostic unless measurement depth
is reconciled.
