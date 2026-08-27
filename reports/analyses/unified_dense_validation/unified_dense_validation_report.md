# Unified dense-point validation and local-spiking report

This report resets the earlier ad hoc three-site sparse local-calibration work
into the two-stage protocol described in
`docs/Downscaling moisture validation plan.pdf`.

The two stages are deliberately kept separate:

1. **Stage 1 — independent validation:** all dense point/date observations are
   used only as external validation. No local measurements are supplied to the
   models or calibration layers.
2. **Stage 2 — local-spiking sensitivity:** small controlled subsets of local
   points are used as calibration spikes, and validation is performed on held-out
   points/dates. The strict `spatiotemporal_block` is treated as the primary
   transfer test.

## Data inventory

| site       | source_table                                                                                                                                        | rows      | models                   | points_unique | dates   | date_min   | date_max   | seasons                     | eligible_points_stage2 | smips_columns_present | note                                                                                                                                                                                                                                                                                                                                                                   |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------ | ------------- | ------- | ---------- | ---------- | --------------------------- | ---------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Esdale     | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv                         | 1120.000  | model6_rf,model8_process | 79.000        | 9.000   | 2025-04-30 | 2025-07-17 | autumn,winter               | 76.000                 | yes                   | Autumn/winter 2025 dense campaign. Strongest spatial/terrain coverage among the modern validation points, but only nine sampling dates are present.                                                                                                                                                                                                                    |
| Tarrawarra | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv | 4308.000  | model6_rf,model8_process | 178.000       | 19.000  | 1995-09-25 | 1996-11-29 | autumn,spring,summer,winter | 168.000                | yes                   | Very dense 1995/96 campaign. Raw sub-cell campaign points are aggregated to the model prediction grid cell by date before validation, so the validation unit matches the raster support. The existing model6 run has a known SMIPS-zero caveat, so model6 skill here should be read partly as a missing coarse-anchor ablation rather than a normal model6 prediction. |
| Llara      | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv                     | 58494.000 | model6_rf,model8_process | 32.000        | 955.000 | 2021-10-19 | 2024-06-30 | autumn,spring,summer,winter | 32.000                 | yes                   | Thirty-two profile-mean probes across two paddocks from 2021–2024. Strongest temporal/seasonal coverage. Point-level SMIPS-derived columns are present, but full gridded Llara model GeoTIFFs are not currently cached.                                                                                                                                                |

Important caveats:

- Tarrawarra is retained because it is uniquely dense, but raw campaign points
  have been aggregated to the model prediction grid cell by date so that the
  validation support matches the raster support. The existing model6 run also
  has a known SMIPS-zero caveat. Treat Tarrawarra model6 as partly a
  missing-coarse-anchor stress test.
- Llara has SMIPS-derived point-level predictors in the validation tables, but
  full gridded model6/model8 GeoTIFF prediction maps are not currently cached.
  Llara map outputs therefore focus on point-level validation and interpolated
  point-quality surfaces, not full raster-native model surfaces.
- The PDF says Esdale has 540 points; the current model-agnostic prediction
  table contains 79 unique point IDs and 560 model6 rows across nine dates. This
  likely reflects a point-vs-observation wording mismatch and should be checked
  by a human before publication.

## Stage 1 — independent dense-point validation

### Overall model skill

| site       | base_model     | n         | nse    | pearson_r | rmse   | ubrmse | bias    |
| ---------- | -------------- | --------- | ------ | --------- | ------ | ------ | ------- |
| Esdale     | model6_rf      | 560.000   | 0.023  | 0.238     | 6.477  | 6.453  | -0.558  |
| Esdale     | model8_process | 560.000   | 0.031  | 0.462     | 6.452  | 5.884  | 2.645   |
| Llara      | model6_rf      | 29247.000 | 0.036  | 0.267     | 13.927 | 13.744 | -2.249  |
| Llara      | model8_process | 29247.000 | -0.017 | 0.453     | 14.306 | 12.855 | -6.278  |
| Tarrawarra | model6_rf      | 2154.000  | -1.219 | 0.398     | 14.402 | 9.093  | -11.169 |
| Tarrawarra | model8_process | 2154.000  | 0.077  | 0.853     | 9.291  | 6.958  | -6.157  |

### Seasonal skill

| site       | base_model     | season | n        | nse     | pearson_r | rmse   | ubrmse | bias    |
| ---------- | -------------- | ------ | -------- | ------- | --------- | ------ | ------ | ------- |
| Esdale     | model6_rf      | autumn | 308.000  | -0.030  | 0.100     | 7.279  | 7.273  | 0.296   |
| Esdale     | model6_rf      | winter | 252.000  | -0.292  | 0.111     | 5.336  | 5.090  | -1.601  |
| Esdale     | model8_process | autumn | 308.000  | 0.027   | 0.336     | 7.076  | 6.777  | 2.033   |
| Esdale     | model8_process | winter | 252.000  | -0.421  | 0.355     | 5.595  | 4.448  | 3.394   |
| Llara      | model6_rf      | spring | 6208.000 | 0.060   | 0.449     | 17.043 | 15.809 | -6.367  |
| Llara      | model6_rf      | summer | 7658.000 | -0.113  | 0.094     | 12.782 | 12.492 | -2.709  |
| Llara      | model6_rf      | autumn | 8617.000 | -0.074  | 0.093     | 12.132 | 12.122 | 0.483   |
| Llara      | model6_rf      | winter | 6764.000 | -0.008  | 0.183     | 14.128 | 14.055 | -1.431  |
| Llara      | model8_process | spring | 6208.000 | -0.060  | 0.657     | 18.104 | 14.520 | -10.813 |
| Llara      | model8_process | summer | 7658.000 | -0.176  | 0.178     | 13.136 | 11.978 | -5.395  |
| Llara      | model8_process | autumn | 8617.000 | -0.051  | 0.238     | 11.999 | 11.384 | -3.793  |
| Llara      | model8_process | winter | 6764.000 | -0.037  | 0.438     | 14.329 | 12.879 | -6.281  |
| Tarrawarra | model6_rf      | spring | 994.000  | -1.765  | 0.478     | 16.068 | 8.928  | -13.360 |
| Tarrawarra | model6_rf      | summer | 333.000  | 0.135   | 0.380     | 3.260  | 3.256  | -0.168  |
| Tarrawarra | model6_rf      | autumn | 663.000  | -1.886  | 0.474     | 12.975 | 6.953  | -10.955 |
| Tarrawarra | model6_rf      | winter | 164.000  | -38.796 | 0.143     | 21.384 | 3.533  | -21.090 |
| Tarrawarra | model8_process | spring | 994.000  | -0.281  | 0.916     | 10.938 | 6.796  | -8.571  |
| Tarrawarra | model8_process | summer | 333.000  | -0.014  | 0.678     | 3.530  | 2.616  | 2.370   |
| Tarrawarra | model8_process | autumn | 663.000  | 0.020   | 0.829     | 7.562  | 5.284  | -5.409  |
| Tarrawarra | model8_process | winter | 164.000  | -12.251 | 0.137     | 12.339 | 3.375  | -11.869 |

### Dry/wet observed-state bias

| site       | base_model     | obs_moisture_quantile | n        | rmse   | ubrmse | bias    |
| ---------- | -------------- | --------------------- | -------- | ------ | ------ | ------- |
| Esdale     | model6_rf      | dry_q1                | 140.000  | 8.019  | 3.383  | 7.270   |
| Esdale     | model6_rf      | q2                    | 140.000  | 2.941  | 2.727  | 1.100   |
| Esdale     | model6_rf      | q3                    | 140.000  | 3.846  | 2.744  | -2.694  |
| Esdale     | model6_rf      | wet_q4                | 140.000  | 8.949  | 4.190  | -7.907  |
| Esdale     | model8_process | dry_q1                | 140.000  | 9.030  | 3.610  | 8.277   |
| Esdale     | model8_process | q2                    | 140.000  | 5.802  | 3.298  | 4.773   |
| Esdale     | model8_process | q3                    | 140.000  | 3.604  | 3.414  | 1.154   |
| Esdale     | model8_process | wet_q4                | 140.000  | 6.188  | 5.017  | -3.622  |
| Llara      | model6_rf      | dry_q1                | 7312.000 | 13.868 | 6.510  | 12.245  |
| Llara      | model6_rf      | q2                    | 7312.000 | 6.352  | 5.234  | 3.600   |
| Llara      | model6_rf      | q3                    | 7311.000 | 7.724  | 5.749  | -5.159  |
| Llara      | model6_rf      | wet_q4                | 7312.000 | 21.989 | 9.799  | -19.684 |
| Llara      | model8_process | dry_q1                | 7312.000 | 8.559  | 4.605  | 7.215   |
| Llara      | model8_process | q2                    | 7312.000 | 4.166  | 4.164  | 0.119   |
| Llara      | model8_process | q3                    | 7311.000 | 10.343 | 4.967  | -9.072  |
| Llara      | model8_process | wet_q4                | 7312.000 | 24.921 | 8.643  | -23.374 |
| Tarrawarra | model6_rf      | dry_q1                | 539.000  | 2.530  | 2.530  | 0.031   |
| Tarrawarra | model6_rf      | q2                    | 538.000  | 7.624  | 3.154  | -6.941  |
| Tarrawarra | model6_rf      | q3                    | 539.000  | 14.900 | 2.562  | -14.678 |
| Tarrawarra | model6_rf      | wet_q4                | 538.000  | 23.314 | 3.139  | -23.101 |
| Tarrawarra | model8_process | dry_q1                | 539.000  | 3.186  | 2.416  | 2.078   |
| Tarrawarra | model8_process | q2                    | 538.000  | 3.935  | 2.612  | -2.943  |
| Tarrawarra | model8_process | q3                    | 539.000  | 8.903  | 2.545  | -8.531  |
| Tarrawarra | model8_process | wet_q4                | 538.000  | 15.510 | 2.868  | -15.243 |

### Most notable terrain/model-input strata

The table below ranks terrain/model-input strata by the range of bias and RMSE
across low/mid/high strata within each site/model. These are diagnostic
validation covariates rather than a claim that every variable is used by every
model internally.

| site       | base_model     | terrain_var   | n_strata | nse_min | nse_max | rmse_min | rmse_max | bias_min | bias_max | nse_range | rmse_range | bias_range |
| ---------- | -------------- | ------------- | -------- | ------- | ------- | -------- | -------- | -------- | -------- | --------- | ---------- | ---------- |
| Esdale     | model6_rf      | rain_7        | 3.000    | -1.425  | -0.977  | 5.280    | 7.366    | -3.641   | 4.164    | 0.449     | 2.086      | 7.804      |
| Esdale     | model6_rf      | ppet_365      | 3.000    | -0.879  | -0.671  | 5.158    | 7.089    | -2.962   | 3.729    | 0.208     | 1.931      | 6.692      |
| Esdale     | model6_rf      | rain_365      | 3.000    | -0.876  | -0.671  | 5.167    | 7.089    | -2.950   | 3.729    | 0.205     | 1.922      | 6.679      |
| Esdale     | model6_rf      | rain_365_anom | 3.000    | -0.876  | -0.671  | 5.167    | 7.089    | -2.950   | 3.729    | 0.205     | 1.922      | 6.679      |
| Esdale     | model6_rf      | ppet_30       | 3.000    | -0.843  | -0.131  | 4.912    | 7.935    | -2.354   | 1.104    | 0.712     | 3.024      | 3.458      |
| Esdale     | model8_process | rain_7        | 3.000    | -1.452  | -0.334  | 4.337    | 7.340    | -0.346   | 6.016    | 1.118     | 3.003      | 6.363      |
| Esdale     | model8_process | ppet_365      | 3.000    | -0.890  | -0.373  | 4.465    | 7.409    | 0.736    | 5.186    | 0.517     | 2.944      | 4.450      |
| Esdale     | model8_process | rain_365      | 3.000    | -0.901  | -0.354  | 4.429    | 7.409    | 0.779    | 5.186    | 0.547     | 2.980      | 4.407      |
| Esdale     | model8_process | rain_365_anom | 3.000    | -0.901  | -0.354  | 4.429    | 7.409    | 0.779    | 5.186    | 0.547     | 2.980      | 4.407      |
| Esdale     | model8_process | soil_sand     | 3.000    | -0.337  | 0.299   | 5.609    | 7.350    | -0.286   | 4.969    | 0.637     | 1.741      | 5.254      |
| Llara      | model6_rf      | hli           | 3.000    | -0.350  | 0.075   | 11.762   | 15.291   | -7.178   | 5.567    | 0.425     | 3.530      | 12.745     |
| Llara      | model6_rf      | eastness      | 3.000    | -0.282  | 0.123   | 10.961   | 16.856   | -5.622   | 4.642    | 0.405     | 5.894      | 10.265     |
| Llara      | model6_rf      | elevation     | 3.000    | -0.065  | 0.136   | 10.714   | 16.594   | -8.256   | 1.284    | 0.201     | 5.880      | 9.540      |
| Llara      | model6_rf      | soil_bdw      | 3.000    | -0.152  | 0.133   | 13.007   | 15.486   | -7.303   | 5.144    | 0.284     | 2.479      | 12.447     |
| Llara      | model6_rf      | northness     | 3.000    | -0.299  | 0.127   | 12.490   | 15.624   | -6.552   | 3.454    | 0.425     | 3.134      | 10.006     |
| Llara      | model8_process | eastness      | 3.000    | -0.212  | 0.134   | 9.006    | 16.854   | -9.164   | -1.609   | 0.346     | 7.848      | 7.555      |
| Llara      | model8_process | hli           | 3.000    | -0.246  | 0.123   | 9.480    | 16.063   | -9.361   | -0.801   | 0.369     | 6.583      | 8.560      |
| Llara      | model8_process | northness     | 3.000    | -0.290  | 0.092   | 10.445   | 16.679   | -9.652   | -1.261   | 0.382     | 6.233      | 8.392      |
| Llara      | model8_process | soil_bdw      | 3.000    | -0.377  | 0.140   | 11.476   | 16.933   | -10.419  | -1.533   | 0.517     | 5.458      | 8.886      |
| Llara      | model8_process | ppet_365      | 3.000    | -0.112  | -0.033  | 11.117   | 17.929   | -9.513   | -4.294   | 0.079     | 6.813      | 5.218      |
| Tarrawarra | model6_rf      | vpd_30        | 3.000    | -12.817 | 0.029   | 3.065    | 20.770   | -20.004  | -0.775   | 12.847    | 17.705     | 19.229     |
| Tarrawarra | model6_rf      | ppet_30       | 3.000    | -10.701 | -0.282  | 4.302    | 18.120   | -15.923  | -2.047   | 10.419    | 13.818     | 13.876     |
| Tarrawarra | model6_rf      | rain_7        | 3.000    | -7.750  | -0.204  | 8.953    | 19.825   | -18.757  | -4.771   | 7.545     | 10.871     | 13.986     |
| Tarrawarra | model6_rf      | ppet_365      | 3.000    | -8.098  | -0.673  | 9.685    | 19.636   | -18.610  | -6.970   | 7.425     | 9.951      | 11.640     |
| Tarrawarra | model6_rf      | rain_365      | 3.000    | -7.642  | -0.459  | 11.614   | 17.470   | -16.619  | -7.192   | 7.183     | 5.856      | 9.427      |
| Tarrawarra | model8_process | vpd_30        | 3.000    | -5.002  | 0.047   | 3.036    | 13.689   | -12.915  | 1.295    | 5.049     | 10.653     | 14.210     |
| Tarrawarra | model8_process | ppet_30       | 3.000    | -2.906  | 0.228   | 3.340    | 12.392   | -10.367  | 0.307    | 3.133     | 9.053      | 10.674     |
| Tarrawarra | model8_process | rain_7        | 3.000    | -2.808  | 0.448   | 5.600    | 13.078   | -12.050  | -1.850   | 3.256     | 7.479      | 10.200     |
| Tarrawarra | model8_process | ppet_365      | 3.000    | -2.833  | 0.367   | 5.959    | 12.744   | -11.514  | -3.197   | 3.199     | 6.786      | 8.317      |
| Tarrawarra | model8_process | rain_365      | 3.000    | -2.413  | 0.372   | 7.620    | 10.980   | -9.899   | -3.353   | 2.785     | 3.359      | 6.545      |

### Paired model comparison

Positive `rmse_delta_a_minus_b` means model B has lower RMSE than model A on
matched observations. `bias_delta_a_minus_b` is model A bias minus model B bias.

| site       | model_a   | model_b        | n_matched | rmse_a | rmse_b | rmse_delta_a_minus_b | bias_a  | bias_b | bias_delta_a_minus_b |
| ---------- | --------- | -------------- | --------- | ------ | ------ | -------------------- | ------- | ------ | -------------------- |
| Esdale     | model6_rf | model8_process | 560.000   | 6.477  | 6.452  | 0.026                | -0.558  | 2.645  | -3.203               |
| Tarrawarra | model6_rf | model8_process | 2154.000  | 14.402 | 9.291  | 5.111                | -11.169 | -6.157 | -5.012               |
| Llara      | model6_rf | model8_process | 29247.000 | 13.927 | 14.306 | -0.379               | -2.249  | -6.278 | 4.028                |

## Stage 2 — local training-data spiking

Budgets used: `3,5,10,25%,50%,all`.

Calibration methods:

- `bias_offset`: constant local residual offset;
- `seasonal_offset`: season-specific residual offset;
- `affine`: local intercept and slope correction;
- `residual_ridge`: regularised residual model using prediction-time model
  inputs such as weather, SMIPS/process state, terrain and soil attributes.

The target requested in the plan is average held-out NSE > 0.4. The table
below reports the smallest strict-block design that reaches that target, or the
best strict-block design if the target is not reached.

| site       | base_model     | target_status               | selection_strategy         | budget_label | calibration_points | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ---------- | -------------- | --------------------------- | -------------------------- | ------------ | ------------------ | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| Esdale     | model6_rf      | not reached; best NSE 0.160 | global_prediction_extremes | 50%          | 38.000             | residual_ridge  | 0.160      | 0.531            | 3.480       | 3.240         | -1.269      | 1.000        |
| Esdale     | model8_process | not reached; best NSE 0.237 | landscape_wetdry_prior     | 25%          | 19.000             | residual_ridge  | 0.237      | 0.494            | 3.746       | 3.745         | 0.088       | 1.000        |
| Llara      | model6_rf      | not reached; best NSE 0.205 | global_prediction_extremes | 50%          | 16.000             | seasonal_offset | 0.205      | 0.457            | 10.211      | 10.195        | -0.579      | 1.000        |
| Llara      | model8_process | not reached; best NSE 0.255 | global_prediction_extremes | 50%          | 16.000             | affine          | 0.255      | 0.511            | 9.885       | 9.872         | 0.503       | 1.000        |
| Tarrawarra | model6_rf      | not reached; best NSE 0.263 | global_prediction_extremes | all          | 168.000            | residual_ridge  | 0.263      | 0.820            | 9.736       | 8.929         | -3.882      | 1.000        |
| Tarrawarra | model8_process | reached NSE ≥ 0.4           | landscape_wetdry_prior     | 1            | 1.000              | affine          | 0.460      | 0.859            | 6.807       | 6.488         | -2.061      | 1.000        |

### Best strict-block local calibration design per site/model

| site       | base_model     | selection_strategy           | budget_label | calibration_points | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ---------- | -------------- | ---------------------------- | ------------ | ------------------ | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| Esdale     | model6_rf      | global_prediction_extremes   | 50%          | 38.000             | residual_ridge  | 0.160      | 0.531            | 3.480       | 3.240         | -1.269      | 1.000        |
| Esdale     | model8_process | field_knowledge_wetdry_proxy | 50%          | 38.000             | bias_offset     | 0.099      | 0.452            | 2.952       | 2.925         | 0.397       | 1.000        |
| Llara      | model6_rf      | field_knowledge_wetdry_proxy | 25%          | 8.000              | seasonal_offset | 0.232      | 0.493            | 10.084      | 10.048        | -0.852      | 1.000        |
| Llara      | model8_process | field_knowledge_wetdry_proxy | 50%          | 16.000             | seasonal_offset | 0.242      | 0.496            | 9.601       | 9.588         | -0.506      | 1.000        |
| Tarrawarra | model6_rf      | landscape_wetdry_prior       | 10           | 10.000             | residual_ridge  | -0.058     | 0.819            | 9.496       | 6.952         | -6.469      | 1.000        |
| Tarrawarra | model8_process | landscape_wetdry_prior       | 25%          | 42.000             | affine          | 0.746      | 0.867            | 4.672       | 4.664         | 0.268       | 1.000        |

### Random-placement learning curves

Random placement is the most defensible deployment-oriented strategy because it
does not assume the landowner already knows where the model fails. Landscape and
global-prediction extreme strategies are still useful as practical priors.

| site   | base_model     | budget_label | calibration_points | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ------ | -------------- | ------------ | ------------------ | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| Esdale | model6_rf      | 1            | 1.000              | affine          | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | model6_rf      | 1            | 1.000              | bias_offset     | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | model6_rf      | 1            | 1.000              | residual_ridge  | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | model6_rf      | 1            | 1.000              | seasonal_offset | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | model6_rf      | 3            | 3.000              | affine          | -1.802     | 0.000            | 7.350       | 4.443         | -5.381      | 20.000       |
| Esdale | model6_rf      | 3            | 3.000              | bias_offset     | -0.693     | 0.059            | 5.688       | 4.907         | -2.994      | 20.000       |
| Esdale | model6_rf      | 3            | 3.000              | residual_ridge  | -0.387     | 0.230            | 5.214       | 4.615         | -1.230      | 20.000       |
| Esdale | model6_rf      | 3            | 3.000              | seasonal_offset | -0.693     | 0.059            | 5.688       | 4.907         | -2.994      | 20.000       |
| Esdale | model6_rf      | 5            | 5.000              | affine          | -2.074     | 0.000            | 7.734       | 4.425         | -6.352      | 20.000       |
| Esdale | model6_rf      | 5            | 5.000              | bias_offset     | -0.928     | 0.060            | 6.119       | 4.908         | -3.680      | 20.000       |
| Esdale | model6_rf      | 5            | 5.000              | residual_ridge  | -0.267     | 0.286            | 4.970       | 4.423         | -1.831      | 20.000       |
| Esdale | model6_rf      | 5            | 5.000              | seasonal_offset | -0.928     | 0.060            | 6.119       | 4.908         | -3.680      | 20.000       |
| Esdale | model6_rf      | 10           | 10.000             | affine          | -1.648     | 0.000            | 7.115       | 4.436         | -5.602      | 20.000       |
| Esdale | model6_rf      | 10           | 10.000             | bias_offset     | -0.733     | 0.055            | 5.897       | 4.957         | -3.054      | 20.000       |
| Esdale | model6_rf      | 10           | 10.000             | residual_ridge  | -0.015     | 0.346            | 4.452       | 4.339         | -0.310      | 20.000       |
| Esdale | model6_rf      | 10           | 10.000             | seasonal_offset | -0.733     | 0.055            | 5.897       | 4.957         | -3.054      | 20.000       |
| Esdale | model6_rf      | 25%          | 19.000             | affine          | -1.695     | 0.000            | 7.181       | 4.426         | -5.712      | 20.000       |
| Esdale | model6_rf      | 25%          | 19.000             | bias_offset     | -0.587     | 0.063            | 5.542       | 4.942         | -2.600      | 20.000       |
| Esdale | model6_rf      | 25%          | 19.000             | residual_ridge  | -0.145     | 0.343            | 4.740       | 4.351         | -0.200      | 20.000       |
| Esdale | model6_rf      | 25%          | 19.000             | seasonal_offset | -0.587     | 0.063            | 5.542       | 4.942         | -2.600      | 20.000       |
| Esdale | model6_rf      | 50%          | 38.000             | affine          | -1.719     | 0.000            | 7.524       | 4.561         | -5.982      | 20.000       |
| Esdale | model6_rf      | 50%          | 38.000             | bias_offset     | -0.639     | 0.021            | 5.838       | 5.082         | -2.676      | 20.000       |
| Esdale | model6_rf      | 50%          | 38.000             | residual_ridge  | 0.009      | 0.447            | 4.420       | 4.118         | -1.094      | 20.000       |
| Esdale | model6_rf      | 50%          | 38.000             | seasonal_offset | -0.639     | 0.021            | 5.838       | 5.082         | -2.676      | 20.000       |
| Esdale | model8_process | 1            | 1.000              | affine          | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | model8_process | 1            | 1.000              | bias_offset     | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | model8_process | 1            | 1.000              | residual_ridge  | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | model8_process | 1            | 1.000              | seasonal_offset | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | model8_process | 3            | 3.000              | affine          | -1.325     | 0.271            | 6.683       | 4.760         | 1.933       | 20.000       |
| Esdale | model8_process | 3            | 3.000              | bias_offset     | -0.064     | 0.273            | 4.557       | 4.402         | 0.942       | 20.000       |
| Esdale | model8_process | 3            | 3.000              | residual_ridge  | -0.392     | 0.415            | 5.191       | 4.134         | 2.931       | 20.000       |
| Esdale | model8_process | 3            | 3.000              | seasonal_offset | -0.064     | 0.273            | 4.557       | 4.402         | 0.942       | 20.000       |
| Esdale | model8_process | 5            | 5.000              | affine          | -0.982     | 0.268            | 6.288       | 4.345         | -3.625      | 20.000       |
| Esdale | model8_process | 5            | 5.000              | bias_offset     | -0.091     | 0.279            | 4.597       | 4.403         | 0.131       | 20.000       |
| Esdale | model8_process | 5            | 5.000              | residual_ridge  | -0.094     | 0.430            | 4.614       | 4.078         | 1.588       | 20.000       |
| Esdale | model8_process | 5            | 5.000              | seasonal_offset | -0.091     | 0.279            | 4.597       | 4.403         | 0.131       | 20.000       |
| Esdale | model8_process | 10           | 10.000             | affine          | -0.381     | 0.262            | 5.075       | 4.438         | -0.208      | 20.000       |
| Esdale | model8_process | 10           | 10.000             | bias_offset     | -0.048     | 0.264            | 4.587       | 4.446         | 0.769       | 20.000       |
| Esdale | model8_process | 10           | 10.000             | residual_ridge  | -0.554     | 0.477            | 5.391       | 4.017         | 3.581       | 20.000       |
| Esdale | model8_process | 10           | 10.000             | seasonal_offset | -0.048     | 0.264            | 4.587       | 4.446         | 0.769       | 20.000       |
| Esdale | model8_process | 25%          | 19.000             | affine          | -0.167     | 0.265            | 4.664       | 4.329         | -1.278      | 20.000       |
| Esdale | model8_process | 25%          | 19.000             | bias_offset     | -0.043     | 0.265            | 4.510       | 4.435         | 0.793       | 20.000       |
| Esdale | model8_process | 25%          | 19.000             | residual_ridge  | -0.891     | 0.474            | 6.196       | 3.965         | 4.748       | 20.000       |
| Esdale | model8_process | 25%          | 19.000             | seasonal_offset | -0.043     | 0.265            | 4.510       | 4.435         | 0.793       | 20.000       |
| Esdale | model8_process | 50%          | 38.000             | affine          | -0.189     | 0.272            | 5.211       | 4.388         | -2.319      | 20.000       |
| Esdale | model8_process | 50%          | 38.000             | bias_offset     | -0.037     | 0.272            | 4.540       | 4.494         | 0.702       | 20.000       |
| Esdale | model8_process | 50%          | 38.000             | residual_ridge  | -0.510     | 0.517            | 5.423       | 3.954         | 3.856       | 20.000       |
| Esdale | model8_process | 50%          | 38.000             | seasonal_offset | -0.037     | 0.272            | 4.540       | 4.494         | 0.702       | 20.000       |
| Llara  | model6_rf      | 1            | 1.000              | affine          | -0.567     | 0.350            | 16.287      | 12.322        | -5.676      | 20.000       |
| Llara  | model6_rf      | 1            | 1.000              | bias_offset     | -0.091     | 0.350            | 13.537      | 12.107        | -3.184      | 20.000       |
| Llara  | model6_rf      | 1            | 1.000              | residual_ridge  | -0.374     | 0.460            | 15.086      | 11.769        | -2.155      | 20.000       |
| Llara  | model6_rf      | 1            | 1.000              | seasonal_offset | -0.129     | 0.357            | 13.643      | 12.275        | -2.561      | 20.000       |
| Llara  | model6_rf      | 3            | 3.000              | affine          | -0.406     | 0.338            | 15.297      | 12.883        | -1.914      | 20.000       |
| Llara  | model6_rf      | 3            | 3.000              | bias_offset     | -0.096     | 0.343            | 13.536      | 12.133        | 1.038       | 20.000       |
| Llara  | model6_rf      | 3            | 3.000              | residual_ridge  | -0.367     | 0.412            | 14.788      | 12.528        | 4.148       | 20.000       |
| Llara  | model6_rf      | 3            | 3.000              | seasonal_offset | -0.091     | 0.346            | 13.552      | 12.366        | 0.919       | 20.000       |
| Llara  | model6_rf      | 5            | 5.000              | affine          | -0.198     | 0.345            | 13.925      | 12.530        | -2.814      | 20.000       |
| Llara  | model6_rf      | 5            | 5.000              | bias_offset     | 0.045      | 0.358            | 12.910      | 11.986        | -2.670      | 20.000       |
| Llara  | model6_rf      | 5            | 5.000              | residual_ridge  | -0.843     | 0.276            | 17.049      | 15.761        | 1.373       | 20.000       |
| Llara  | model6_rf      | 5            | 5.000              | seasonal_offset | 0.008      | 0.361            | 12.876      | 12.231        | -2.042      | 20.000       |
| Llara  | model6_rf      | 25%          | 8.000              | affine          | -0.101     | 0.343            | 13.838      | 12.603        | -4.782      | 20.000       |
| Llara  | model6_rf      | 25%          | 8.000              | bias_offset     | -0.100     | 0.367            | 13.556      | 12.181        | -5.907      | 20.000       |
| Llara  | model6_rf      | 25%          | 8.000              | residual_ridge  | -1.981     | 0.240            | 22.064      | 19.810        | -0.842      | 20.000       |
| Llara  | model6_rf      | 25%          | 8.000              | seasonal_offset | -0.014     | 0.392            | 13.068      | 12.257        | -4.797      | 20.000       |
| Llara  | model6_rf      | 10           | 10.000             | affine          | -0.021     | 0.311            | 13.168      | 12.531        | -1.252      | 20.000       |
| Llara  | model6_rf      | 10           | 10.000             | bias_offset     | 0.014      | 0.336            | 13.058      | 12.128        | -3.002      | 20.000       |
| Llara  | model6_rf      | 10           | 10.000             | residual_ridge  | -2.527     | 0.165            | 23.778      | 20.945        | 2.089       | 20.000       |
| Llara  | model6_rf      | 10           | 10.000             | seasonal_offset | 0.007      | 0.358            | 12.827      | 12.158        | -2.393      | 20.000       |
| Llara  | model6_rf      | 50%          | 16.000             | affine          | 0.019      | 0.329            | 12.395      | 12.168        | -0.822      | 20.000       |
| Llara  | model6_rf      | 50%          | 16.000             | bias_offset     | 0.080      | 0.372            | 12.255      | 11.958        | -1.653      | 20.000       |

_Showing first 70 of 152 rows._

### Process-vs-statistical response to local spiking

Positive `process_minus_statistical_rmse_gain_median` means model8 process
benefited more from the same sparse local calibration budget than model6 RF.

| site       | budget_label | calibration_points | method          | statistical_rmse_gain_median | process_rmse_gain_median | process_minus_statistical_rmse_gain_median | fraction_process_wins | n_replicates |
| ---------- | ------------ | ------------------ | --------------- | ---------------------------- | ------------------------ | ------------------------------------------ | --------------------- | ------------ |
| Esdale     | 1            | 1.000              | affine          | -0.750                       | 0.249                    | 0.634                                      | 0.700                 | 20.000       |
| Esdale     | 1            | 1.000              | bias_offset     | -0.750                       | 0.249                    | 0.634                                      | 0.700                 | 20.000       |
| Esdale     | 1            | 1.000              | residual_ridge  | -0.750                       | 0.249                    | 0.634                                      | 0.700                 | 20.000       |
| Esdale     | 1            | 1.000              | seasonal_offset | -0.750                       | 0.249                    | 0.634                                      | 0.700                 | 20.000       |
| Esdale     | 10           | 10.000             | affine          | -1.993                       | 0.257                    | 1.600                                      | 0.750                 | 20.000       |
| Esdale     | 10           | 10.000             | bias_offset     | -0.542                       | 0.755                    | 1.356                                      | 0.900                 | 20.000       |
| Esdale     | 10           | 10.000             | residual_ridge  | 0.796                        | -0.096                   | -0.901                                     | 0.100                 | 20.000       |
| Esdale     | 10           | 10.000             | seasonal_offset | -0.542                       | 0.755                    | 1.356                                      | 0.900                 | 20.000       |
| Esdale     | 25%          | 19.000             | affine          | -2.163                       | 0.488                    | 2.510                                      | 0.950                 | 20.000       |
| Esdale     | 25%          | 19.000             | bias_offset     | -0.386                       | 0.759                    | 1.237                                      | 1.000                 | 20.000       |
| Esdale     | 25%          | 19.000             | residual_ridge  | 0.622                        | -0.860                   | -1.277                                     | 0.250                 | 20.000       |
| Esdale     | 25%          | 19.000             | seasonal_offset | -0.386                       | 0.759                    | 1.237                                      | 1.000                 | 20.000       |
| Esdale     | 3            | 3.000              | affine          | -2.109                       | -1.462                   | 0.202                                      | 0.450                 | 20.000       |
| Esdale     | 3            | 3.000              | bias_offset     | -0.554                       | 0.721                    | 1.348                                      | 0.800                 | 20.000       |
| Esdale     | 3            | 3.000              | residual_ridge  | 0.030                        | 0.093                    | -0.062                                     | 0.500                 | 20.000       |
| Esdale     | 3            | 3.000              | seasonal_offset | -0.554                       | 0.721                    | 1.348                                      | 0.800                 | 20.000       |
| Esdale     | 5            | 5.000              | affine          | -2.572                       | -1.007                   | 1.642                                      | 0.550                 | 20.000       |
| Esdale     | 5            | 5.000              | bias_offset     | -0.892                       | 0.688                    | 1.727                                      | 0.900                 | 20.000       |
| Esdale     | 5            | 5.000              | residual_ridge  | 0.219                        | 0.581                    | 0.413                                      | 0.550                 | 20.000       |
| Esdale     | 5            | 5.000              | seasonal_offset | -0.892                       | 0.688                    | 1.727                                      | 0.900                 | 20.000       |
| Esdale     | 50%          | 38.000             | affine          | -2.141                       | 0.349                    | 2.380                                      | 1.000                 | 20.000       |
| Esdale     | 50%          | 38.000             | bias_offset     | -0.388                       | 0.808                    | 1.279                                      | 1.000                 | 20.000       |
| Esdale     | 50%          | 38.000             | residual_ridge  | 1.074                        | -0.004                   | -0.946                                     | 0.150                 | 20.000       |
| Esdale     | 50%          | 38.000             | seasonal_offset | -0.388                       | 0.808                    | 1.279                                      | 1.000                 | 20.000       |
| Llara      | 1            | 1.000              | affine          | -3.685                       | -4.061                   | 1.037                                      | 0.500                 | 20.000       |
| Llara      | 1            | 1.000              | bias_offset     | -0.967                       | -0.935                   | 0.673                                      | 0.450                 | 20.000       |
| Llara      | 1            | 1.000              | residual_ridge  | -2.630                       | -2.188                   | 1.206                                      | 0.750                 | 20.000       |
| Llara      | 1            | 1.000              | seasonal_offset | -1.095                       | -0.765                   | 0.678                                      | 0.450                 | 20.000       |
| Llara      | 10           | 10.000             | affine          | -0.487                       | 1.192                    | 1.634                                      | 0.750                 | 20.000       |
| Llara      | 10           | 10.000             | bias_offset     | -0.186                       | 1.485                    | 1.743                                      | 0.950                 | 20.000       |
| Llara      | 10           | 10.000             | residual_ridge  | -10.959                      | -9.436                   | 1.512                                      | 0.650                 | 20.000       |
| Llara      | 10           | 10.000             | seasonal_offset | -0.083                       | 1.623                    | 1.560                                      | 0.950                 | 20.000       |
| Llara      | 25%          | 8.000              | affine          | -1.209                       | 0.293                    | 1.705                                      | 0.800                 | 20.000       |
| Llara      | 25%          | 8.000              | bias_offset     | -0.819                       | 1.139                    | 2.073                                      | 1.000                 | 20.000       |
| Llara      | 25%          | 8.000              | residual_ridge  | -9.580                       | -8.135                   | 1.122                                      | 0.450                 | 20.000       |
| Llara      | 25%          | 8.000              | seasonal_offset | -0.347                       | 1.315                    | 1.897                                      | 1.000                 | 20.000       |
| Llara      | 3            | 3.000              | affine          | -2.796                       | -0.435                   | 2.127                                      | 0.750                 | 20.000       |
| Llara      | 3            | 3.000              | bias_offset     | -1.106                       | 0.833                    | 1.607                                      | 0.900                 | 20.000       |
| Llara      | 3            | 3.000              | residual_ridge  | -2.857                       | -2.816                   | 0.554                                      | 0.400                 | 20.000       |
| Llara      | 3            | 3.000              | seasonal_offset | -1.081                       | 0.505                    | 1.573                                      | 0.900                 | 20.000       |
| Llara      | 5            | 5.000              | affine          | -1.329                       | -0.032                   | 1.592                                      | 0.850                 | 20.000       |
| Llara      | 5            | 5.000              | bias_offset     | -0.239                       | 1.379                    | 1.692                                      | 0.950                 | 20.000       |
| Llara      | 5            | 5.000              | residual_ridge  | -5.052                       | -4.603                   | 1.384                                      | 0.700                 | 20.000       |
| Llara      | 5            | 5.000              | seasonal_offset | -0.202                       | 1.191                    | 1.546                                      | 0.950                 | 20.000       |
| Llara      | 50%          | 16.000             | affine          | -0.136                       | 1.476                    | 1.325                                      | 0.750                 | 20.000       |
| Llara      | 50%          | 16.000             | bias_offset     | 0.150                        | 1.701                    | 1.581                                      | 0.950                 | 20.000       |
| Llara      | 50%          | 16.000             | residual_ridge  | -7.449                       | -5.602                   | 1.710                                      | 0.700                 | 20.000       |
| Llara      | 50%          | 16.000             | seasonal_offset | 0.213                        | 1.708                    | 1.560                                      | 0.900                 | 20.000       |
| Tarrawarra | 1            | 1.000              | affine          | 3.393                        | 1.289                    | -2.111                                     | 1.000                 | 20.000       |
| Tarrawarra | 1            | 1.000              | bias_offset     | 3.345                        | 0.957                    | -2.191                                     | 1.000                 | 20.000       |
| Tarrawarra | 1            | 1.000              | residual_ridge  | 3.345                        | 0.957                    | -2.191                                     | 1.000                 | 20.000       |
| Tarrawarra | 1            | 1.000              | seasonal_offset | 4.862                        | 2.274                    | -2.788                                     | 1.000                 | 20.000       |
| Tarrawarra | 10           | 10.000             | affine          | 3.801                        | 4.831                    | 1.045                                      | 1.000                 | 20.000       |
| Tarrawarra | 10           | 10.000             | bias_offset     | 3.761                        | 1.414                    | -2.324                                     | 1.000                 | 20.000       |
| Tarrawarra | 10           | 10.000             | residual_ridge  | 4.798                        | 2.909                    | -1.923                                     | 1.000                 | 20.000       |
| Tarrawarra | 10           | 10.000             | seasonal_offset | 5.314                        | 2.553                    | -2.758                                     | 1.000                 | 20.000       |
| Tarrawarra | 25%          | 42.000             | affine          | 3.833                        | 4.818                    | 1.021                                      | 1.000                 | 20.000       |
| Tarrawarra | 25%          | 42.000             | bias_offset     | 3.594                        | 1.148                    | -2.420                                     | 1.000                 | 20.000       |
| Tarrawarra | 25%          | 42.000             | residual_ridge  | 4.793                        | 2.661                    | -2.172                                     | 1.000                 | 20.000       |
| Tarrawarra | 25%          | 42.000             | seasonal_offset | 5.285                        | 2.515                    | -2.751                                     | 1.000                 | 20.000       |
| Tarrawarra | 3            | 3.000              | affine          | 3.431                        | 4.813                    | 0.914                                      | 1.000                 | 20.000       |
| Tarrawarra | 3            | 3.000              | bias_offset     | 3.838                        | 1.533                    | -2.385                                     | 1.000                 | 20.000       |
| Tarrawarra | 3            | 3.000              | residual_ridge  | 4.459                        | 2.724                    | -2.132                                     | 1.000                 | 20.000       |
| Tarrawarra | 3            | 3.000              | seasonal_offset | 5.255                        | 2.385                    | -2.818                                     | 1.000                 | 20.000       |
| Tarrawarra | 5            | 5.000              | affine          | 3.936                        | 4.913                    | 0.607                                      | 1.000                 | 20.000       |
| Tarrawarra | 5            | 5.000              | bias_offset     | 3.840                        | 1.544                    | -2.406                                     | 1.000                 | 20.000       |
| Tarrawarra | 5            | 5.000              | residual_ridge  | 4.723                        | 2.811                    | -2.075                                     | 1.000                 | 20.000       |
| Tarrawarra | 5            | 5.000              | seasonal_offset | 5.377                        | 2.480                    | -2.920                                     | 1.000                 | 20.000       |
| Tarrawarra | 50%          | 84.000             | affine          | 3.763                        | 4.781                    | 0.974                                      | 1.000                 | 20.000       |
| Tarrawarra | 50%          | 84.000             | bias_offset     | 3.584                        | 1.136                    | -2.425                                     | 1.000                 | 20.000       |

_Showing first 70 of 76 rows._

## Figures

### Stage 1 overall model skill by site

![Stage 1 overall model skill by site](figures/stage1/site_model_overall_skill.png)

Independent pooled skill for each model/site, before any local calibration.

### Seasonal bias by site and model

![Seasonal bias by site and model](figures/stage1/seasonal_bias_by_site_model.png)

Mean residual by season; positive values mean overprediction.

### Dry/wet observed-state bias

![Dry/wet observed-state bias](figures/stage1/wetness_quantile_bias.png)

Bias in driest and wettest observed moisture quartiles.

### Observed and predicted spatial-mean time series

![Observed and predicted spatial-mean time series](figures/stage1/predicted_vs_observed_timeseries_three_sites.png)

Date-wise observed soil moisture compared with model6 and model8 spatial means for each site.

### DEM terrain context and validation supports

![DEM terrain context and validation supports](figures/stage1/dem_point_overlays/dem_points_overlay_gallery.png)

True DEM rasters with validation points or grid-cell centroids overlaid for each site.

### Esdale raster-native dry/wet prediction gallery

![Esdale raster-native dry/wet prediction gallery](figures/stage1/esdale_coarse_model6_model8_gallery.png)

Actual cached coarse/model6/model8 gridded products for Esdale dates.

### Tarrawarra raster-native prediction gallery

![Tarrawarra raster-native prediction gallery](figures/stage1/tarrawarra_coarse_model6_model8_gallery.png)

Actual cached gridded model products plotted in the Tarrawarra 5 m DEM footprint.

### Stage 2 global baseline skill

![Stage 2 global baseline skill](figures/stage2_local_spiking/baseline_site_model_skill.png)

Uncalibrated baseline for the same held-out design used by local spiking.

### Stage 2 random sparse-sensor learning curves

![Stage 2 random sparse-sensor learning curves](figures/stage2_local_spiking/random_spatiotemporal_learning_curves_rmse_gain.png)

Median RMSE gain under the strict spatial+temporal block.

### Process-vs-statistical local calibration responsiveness

![Process-vs-statistical local calibration responsiveness](figures/stage2_local_spiking/process_vs_statistical_responsiveness_random.png)

Positive values indicate model8 gained more from the same sparse local information budget.

## Gallery generation warnings

_None._

## Output index

- Stage 1 tables: `outputs/unified_dense_validation/stage1_independent_validation/`
- Stage 2 tables: `outputs/unified_dense_validation/stage2_local_spiking/`
- Report figures: `reports/analyses/unified_dense_validation/figures/`
- Stage 2 standalone report: `reports/analyses/unified_dense_validation/stage2_local_spiking_report.md`

## Interpretation guardrails

- Stage 1 is the independent validation score. Stage 2 is an intervention
  experiment and should not be mixed into the primary model-transfer score.
- Only spatial+temporal blocking should be treated as strong evidence of local
  calibration transfer.
- Field-knowledge-like placement strategies are useful for exploring landowner
  deployment, but anything using observed chronic wet/dry behaviour is an upper
  bound rather than a blind operational rule.
- Interpolated prediction-quality surfaces are diagnostic maps of point metrics.
  They are not substitutes for full gridded model prediction rasters.
