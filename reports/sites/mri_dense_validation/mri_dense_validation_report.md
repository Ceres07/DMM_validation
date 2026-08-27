# MRI separate dense validation - model6 RF vs model8 process

This report keeps the Mulloon Rehydration Initiative soil-moisture probes
separate from `reports/analyses/unified_dense_validation` while using the same
model-agnostic validation and local-spiking figure pipeline.

## Data preparation

| site | source_table                                                                                                         | rows      | models                   | points_unique | dates    | date_min   | date_max   | seasons                     | eligible_points_stage2 | smips_columns_present | note |
| ---- | -------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------ | ------------- | -------- | ---------- | ---------- | --------------------------- | ---------------------- | --------------------- | ---- |
| MRI  | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/mri_model6_model8_predictions.csv | 60518.000 | model6_rf,model8_process | 18.000        | 1931.000 | 2020-09-25 | 2026-06-03 | autumn,spring,summer,winter | 18.000                 | yes                   |      |

Preparation details:

- Source percent CSV: `/Volumes/Dmitry_work/borevitz_projects/Data/MRI_data/SM_combined_cleaned/SM(%)_combined_cleaned.csv`
- Source GPKG: `/Volumes/Dmitry_work/borevitz_projects/Data/MRI_data/MulloonRehydrationInitiative.gpkg`
- Coordinate and label layer: `Soil_Moisture_Probes`
- Logger serial crosswalk layer: `HT_Measurement_Point_Matrix`
- Metadata PDF reference: `/Volumes/Dmitry_work/borevitz_projects/Data/MRI_data/SM_metadata.pdf`
- Daily profile observations: 30259 rows from 18 probes
- Dates used: 2020-09-25 to 2026-06-03 (1931 dates)
- Feature/prediction bbox W/S/E/N: `(149.5768581609843, -35.293447188943425, 149.6383966184215, -35.192121174251156)`
- Daily date policy: UTC timestamps converted to `Australia/Sydney` before daily aggregation
- Observation filter: `1e-06 < soil_moisture_percent <= 100.0`
- Profile mean policy: daily mean per depth channel, then unweighted profile mean across valid depth channels
- Coordinate policy: lon/lat from Soil_Moisture_Probes GPKG layer; HT_Measurement_Point_Matrix used only for logger serial to Irrimax_ID crosswalk

Filtered cells: 303 low/zero and
10305 above 100.0% VWC.

## Stage 1 - independent validation

### Overall skill

| site | base_model     | n         | nse    | pearson_r | rmse   | ubrmse | bias   | mae   |
| ---- | -------------- | --------- | ------ | --------- | ------ | ------ | ------ | ----- |
| MRI  | model6_rf      | 30259.000 | -0.016 | 0.527     | 10.067 | 8.502  | -5.390 | 7.980 |
| MRI  | model8_process | 30259.000 | 0.011  | 0.590     | 9.933  | 8.205  | -5.599 | 8.051 |

### Seasonal skill

| site | base_model     | season | n        | nse    | pearson_r | rmse   | ubrmse | bias   | mae   |
| ---- | -------------- | ------ | -------- | ------ | --------- | ------ | ------ | ------ | ----- |
| MRI  | model6_rf      | spring | 7505.000 | -0.024 | 0.519     | 10.138 | 8.568  | -5.419 | 8.099 |
| MRI  | model6_rf      | summer | 7129.000 | 0.084  | 0.592     | 9.930  | 8.530  | -5.083 | 7.780 |
| MRI  | model6_rf      | autumn | 7887.000 | 0.011  | 0.524     | 10.003 | 8.604  | -5.103 | 7.869 |
| MRI  | model6_rf      | winter | 7738.000 | -0.441 | 0.275     | 10.187 | 8.277  | -5.938 | 8.161 |
| MRI  | model8_process | spring | 7505.000 | -0.095 | 0.613     | 10.484 | 8.009  | -6.765 | 8.633 |
| MRI  | model8_process | summer | 7129.000 | 0.217  | 0.664     | 9.181  | 8.141  | -4.245 | 7.331 |
| MRI  | model8_process | autumn | 7887.000 | 0.080  | 0.565     | 9.650  | 8.464  | -4.636 | 7.726 |
| MRI  | model8_process | winter | 7738.000 | -0.481 | 0.377     | 10.326 | 7.861  | -6.696 | 8.482 |

### Dry/wet observed-state bias

| site | base_model     | obs_moisture_quantile | n        | obs_mean | pred_mean | rmse   | ubrmse | bias    | mae    |
| ---- | -------------- | --------------------- | -------- | -------- | --------- | ------ | ------ | ------- | ------ |
| MRI  | model6_rf      | dry_q1                | 7565.000 | 16.935   | 21.259    | 7.282  | 5.858  | 4.324   | 5.407  |
| MRI  | model6_rf      | q2                    | 7565.000 | 27.692   | 24.522    | 4.979  | 3.839  | -3.169  | 3.763  |
| MRI  | model6_rf      | q3                    | 7564.000 | 34.706   | 27.071    | 8.971  | 4.710  | -7.635  | 7.667  |
| MRI  | model6_rf      | wet_q4                | 7565.000 | 42.745   | 27.662    | 15.719 | 4.428  | -15.083 | 15.083 |
| MRI  | model8_process | dry_q1                | 7565.000 | 16.935   | 21.227    | 6.837  | 5.323  | 4.292   | 5.293  |
| MRI  | model8_process | q2                    | 7565.000 | 27.692   | 23.941    | 5.057  | 3.391  | -3.751  | 3.974  |
| MRI  | model8_process | q3                    | 7564.000 | 34.706   | 26.662    | 9.045  | 4.135  | -8.044  | 8.047  |
| MRI  | model8_process | wet_q4                | 7565.000 | 42.745   | 27.853    | 15.509 | 4.331  | -14.892 | 14.892 |

### Paired model comparison

Positive `mean_delta_abs_error` means model8 has lower absolute error than
model6 on matched probe-date observations.

| site | model_a   | model_b        | n_matched | mean_delta_abs_error | rmse_a | rmse_b | bias_a | bias_b |
| ---- | --------- | -------------- | --------- | -------------------- | ------ | ------ | ------ | ------ |
| MRI  | model6_rf | model8_process | 30259.000 | -0.072               | 10.067 | 9.933  | -5.390 | -5.599 |

### Most notable terrain/model-input strata

| site | base_model     | terrain_var | n_strata | nse_min | nse_max | rmse_min | rmse_max | bias_min | bias_max |
| ---- | -------------- | ----------- | -------- | ------- | ------- | -------- | -------- | -------- | -------- |
| MRI  | model6_rf      | northness   | 3.000    | -1.321  | 0.412   | 7.101    | 13.330   | -11.292  | 0.817    |
| MRI  | model6_rf      | twi         | 3.000    | -1.606  | 0.296   | 8.255    | 12.708   | -10.517  | -0.207   |
| MRI  | model6_rf      | elevation   | 3.000    | -0.719  | 0.355   | 8.086    | 12.743   | -10.145  | -0.688   |
| MRI  | model6_rf      | soil_bdw    | 3.000    | -0.262  | 0.303   | 8.850    | 11.969   | -8.773   | -1.355   |
| MRI  | model6_rf      | slope       | 3.000    | -0.805  | 0.260   | 8.851    | 10.763   | -7.708   | -0.130   |
| MRI  | model6_rf      | hli         | 3.000    | -0.346  | 0.191   | 9.092    | 11.394   | -8.024   | -1.182   |
| MRI  | model6_rf      | soil_awc    | 3.000    | -1.160  | 0.286   | 8.954    | 11.114   | -8.546   | -2.351   |
| MRI  | model6_rf      | soil_clay   | 3.000    | -0.223  | 0.147   | 8.832    | 11.201   | -7.357   | -3.116   |
| MRI  | model8_process | northness   | 3.000    | -1.280  | 0.458   | 6.820    | 13.212   | -11.332  | 0.203    |
| MRI  | model8_process | twi         | 3.000    | -1.521  | 0.372   | 7.794    | 12.497   | -10.768  | -0.219   |
| MRI  | model8_process | elevation   | 3.000    | -0.546  | 0.353   | 8.093    | 12.084   | -9.305   | -1.328   |
| MRI  | model8_process | slope       | 3.000    | -0.702  | 0.339   | 8.363    | 10.599   | -8.021   | -0.127   |
| MRI  | model8_process | soil_bdw    | 3.000    | -0.235  | 0.266   | 8.566    | 11.839   | -8.506   | -2.368   |
| MRI  | model8_process | hli         | 3.000    | -0.464  | 0.275   | 8.605    | 10.849   | -7.402   | -1.621   |
| MRI  | model8_process | soil_awc    | 3.000    | -0.995  | 0.240   | 8.616    | 10.683   | -8.443   | -3.374   |
| MRI  | model8_process | ppet_365    | 3.000    | -0.457  | 0.251   | 8.445    | 11.064   | -7.345   | -3.019   |

## Stage 2 - local-spiking sensitivity

Stage 2 uses the same sparse local-calibration design as the unified dense
validation, but only on MRI probes. The strict `spatiotemporal_block` remains
the main transfer test.

### Uncalibrated baseline

| site | base_model     | model_track    | n         | nse    | pearson_r | rmse   | ubrmse | bias   |
| ---- | -------------- | -------------- | --------- | ------ | --------- | ------ | ------ | ------ |
| MRI  | model6_rf      | statistical_rf | 30259.000 | -0.016 | 0.527     | 10.067 | 8.502  | -5.390 |
| MRI  | model8_process | process_bucket | 30259.000 | 0.011  | 0.590     | 9.933  | 8.205  | -5.599 |

### NSE target summary

| site | base_model     | target_status     | selection_strategy         | budget_label | calibration_points | method         | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ---- | -------------- | ----------------- | -------------------------- | ------------ | ------------------ | -------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| MRI  | model6_rf      | reached NSE ≥ 0.4 | global_prediction_extremes | 50%          | 9.000              | residual_ridge | 0.404      | 0.664            | 8.127       | 8.010         | -1.376      | 1.000        |
| MRI  | model8_process | reached NSE ≥ 0.4 | global_prediction_extremes | 3            | 3.000              | residual_ridge | 0.487      | 0.747            | 7.237       | 7.232         | -0.272      | 1.000        |

### Best strict-block local calibration design

| site | base_model     | selection_strategy           | budget_label | calibration_points | method      | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ---- | -------------- | ---------------------------- | ------------ | ------------------ | ----------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| MRI  | model6_rf      | field_knowledge_wetdry_proxy | 50%          | 9.000              | bias_offset | 0.148      | 0.428            | 6.410       | 6.389         | 0.521       | 1.000        |
| MRI  | model8_process | field_knowledge_wetdry_proxy | 50%          | 9.000              | bias_offset | 0.257      | 0.517            | 5.988       | 5.966         | 0.506       | 1.000        |

### Process-vs-statistical response under random placement

| site | budget_label | calibration_points | method          | statistical_rmse_gain_median | process_rmse_gain_median | process_minus_statistical_rmse_gain_median | fraction_process_wins | n_replicates |
| ---- | ------------ | ------------------ | --------------- | ---------------------------- | ------------------------ | ------------------------------------------ | --------------------- | ------------ |
| MRI  | 1            | 1.000              | affine          | 0.319                        | 0.302                    | 0.310                                      | 0.750                 | 20.000       |
| MRI  | 1            | 1.000              | bias_offset     | 0.685                        | 1.086                    | 0.124                                      | 0.800                 | 20.000       |
| MRI  | 1            | 1.000              | residual_ridge  | -2.194                       | -0.917                   | 0.715                                      | 0.900                 | 20.000       |
| MRI  | 1            | 1.000              | seasonal_offset | 0.655                        | 1.009                    | 0.225                                      | 0.850                 | 20.000       |
| MRI  | 10           | 10.000             | affine          | -2.135                       | -1.052                   | 1.127                                      | 0.900                 | 20.000       |
| MRI  | 10           | 10.000             | bias_offset     | -0.056                       | -0.103                   | 0.064                                      | 0.600                 | 20.000       |
| MRI  | 10           | 10.000             | residual_ridge  | -3.112                       | -3.831                   | 0.000                                      | 0.550                 | 20.000       |
| MRI  | 10           | 10.000             | seasonal_offset | -0.308                       | -0.205                   | 0.265                                      | 0.800                 | 20.000       |
| MRI  | 25%          | 5.000              | affine          | -1.073                       | -0.174                   | 0.755                                      | 0.700                 | 20.000       |
| MRI  | 25%          | 5.000              | bias_offset     | 0.688                        | 0.712                    | -0.014                                     | 0.550                 | 20.000       |
| MRI  | 25%          | 5.000              | residual_ridge  | -0.079                       | -0.091                   | 0.014                                      | 0.450                 | 20.000       |
| MRI  | 25%          | 5.000              | seasonal_offset | 0.550                        | 0.595                    | 0.123                                      | 0.700                 | 20.000       |
| MRI  | 3            | 3.000              | affine          | -1.695                       | -1.588                   | 0.367                                      | 0.700                 | 20.000       |
| MRI  | 3            | 3.000              | bias_offset     | 0.177                        | 0.227                    | 0.176                                      | 0.900                 | 20.000       |
| MRI  | 3            | 3.000              | residual_ridge  | -0.956                       | -1.180                   | 0.236                                      | 0.600                 | 20.000       |
| MRI  | 3            | 3.000              | seasonal_offset | 0.021                        | 0.091                    | 0.382                                      | 0.900                 | 20.000       |
| MRI  | 5            | 5.000              | affine          | -0.313                       | 0.047                    | 0.403                                      | 0.850                 | 20.000       |
| MRI  | 5            | 5.000              | bias_offset     | 0.381                        | 0.659                    | 0.113                                      | 0.600                 | 20.000       |
| MRI  | 5            | 5.000              | residual_ridge  | 0.161                        | -0.257                   | -0.180                                     | 0.300                 | 20.000       |
| MRI  | 5            | 5.000              | seasonal_offset | -0.035                       | 0.431                    | 0.207                                      | 0.950                 | 20.000       |
| MRI  | 50%          | 9.000              | affine          | -1.112                       | -0.136                   | 1.409                                      | 0.800                 | 20.000       |
| MRI  | 50%          | 9.000              | bias_offset     | 0.831                        | 0.924                    | 0.109                                      | 0.550                 | 20.000       |
| MRI  | 50%          | 9.000              | residual_ridge  | -3.734                       | -3.519                   | 0.049                                      | 0.600                 | 20.000       |
| MRI  | 50%          | 9.000              | seasonal_offset | 0.600                        | 0.781                    | 0.232                                      | 0.750                 | 20.000       |

## Stage 1 Figures

### Stage 1 overall model skill

![Stage 1 overall model skill](figures/stage1/site_model_overall_skill.png)

Independent MRI probe-date validation before local calibration.

### Seasonal bias

![Seasonal bias](figures/stage1/seasonal_bias_by_site_model.png)

Mean residual by southern-hemisphere season; positive values mean overprediction.

### Dry/wet observed-state bias

![Dry/wet observed-state bias](figures/stage1/wetness_quantile_bias.png)

Bias in observed soil-moisture quartiles.

### Observed vs predicted by season

![Observed vs predicted by season](figures/stage1/site_diagnostics/mri/scatter_observed_vs_predicted_by_season.png)

Point-date observations compared with model predictions by season.

### Spatial-mean time series

![Spatial-mean time series](figures/stage1/site_diagnostics/mri/timeseries_observed_vs_predicted_mean.png)

Date-wise MRI observed soil moisture compared with model6 and model8 spatial means.

### Mean residual time series

![Mean residual time series](figures/stage1/site_diagnostics/mri/timeseries_residuals_mean.png)

Date-wise mean prediction residuals.

### Seasonal residual distributions

![Seasonal residual distributions](figures/stage1/site_diagnostics/mri/seasonal_bias_boxplot.png)

Residual spread by season and model.

### Model6 point RMSE

![Model6 point RMSE](figures/stage1/site_diagnostics/mri/point_map_model6_rf_rmse.png)

Point-level model6 RMSE at MRI probe coordinates.

### Model8 point RMSE

![Model8 point RMSE](figures/stage1/site_diagnostics/mri/point_map_model8_process_rmse.png)

Point-level model8 RMSE at MRI probe coordinates.

### Paired model error difference

![Paired model error difference](figures/stage1/site_diagnostics/mri/paired_error_difference_map_model6_rf_minus_model8_process.png)

Mean paired absolute-error difference at MRI probe coordinates.

### Model6 interpolated RMSE surface

![Model6 interpolated RMSE surface](figures/stage1/quality_surfaces/mri_model6_rf_rmse_idw_surface.png)

IDW interpolation of point-level RMSE for visual diagnosis only.

### Model8 interpolated RMSE surface

![Model8 interpolated RMSE surface](figures/stage1/quality_surfaces/mri_model8_process_rmse_idw_surface.png)

IDW interpolation of point-level RMSE for visual diagnosis only.

## Stage 2 Figures

### Uncalibrated global model skill by dense site

![Uncalibrated global model skill by dense site](figures/stage2_local_spiking/baseline_site_model_skill.png)

Baseline RMSE and NSE for model6 RF and model8 process before any local calibration.

### Strict spatio-temporal prior-guided learning curves: RMSE gain

![Strict spatio-temporal prior-guided learning curves: RMSE gain](figures/stage2_local_spiking/prior_guided_spatiotemporal_learning_curves_rmse_gain.png)

Best RMSE gain from deployable non-random placement priors under the strict spatial+temporal block.

### Strict spatio-temporal prior-guided learning curves: NSE

![Strict spatio-temporal prior-guided learning curves: NSE](figures/stage2_local_spiking/prior_guided_spatiotemporal_learning_curves_nse.png)

Best held-out NSE from deployable non-random placement priors under the strict spatial+temporal block.

### Process-vs-statistical responsiveness under prior-guided placement

![Process-vs-statistical responsiveness under prior-guided placement](figures/stage2_local_spiking/prior_guided_process_vs_statistical_responsiveness.png)

Positive values indicate model8 process gains more from the same deployable non-random placement strategy than model6 RF.

### Appendix: random strict spatio-temporal learning curves, RMSE gain

![Appendix: random strict spatio-temporal learning curves, RMSE gain](figures/stage2_local_spiking/random_spatiotemporal_learning_curves_rmse_gain.png)

Median RMSE gain from random sparse local sensors when calibration and validation are separated in space and time.

### Appendix: random strict spatio-temporal learning curves, NSE

![Appendix: random strict spatio-temporal learning curves, NSE](figures/stage2_local_spiking/random_spatiotemporal_learning_curves_nse.png)

Median held-out NSE from random sparse local sensors when calibration and validation are separated in space and time.

### Appendix: process-vs-statistical responsiveness under random placement

![Appendix: process-vs-statistical responsiveness under random placement](figures/stage2_local_spiking/process_vs_statistical_responsiveness_random.png)

Positive values indicate model8 process gains more from the same random sparse calibration budget than model6 RF.

## Output index

- Prepared observations: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/mri_profile_mean_observations.csv`
- Probe coordinate crosswalk: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/mri_probe_coordinate_crosswalk.csv`
- Model input features: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/mri_model_input_features.csv`
- Model-agnostic predictions: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/mri_model6_model8_predictions.csv`
- Stage 1 outputs: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/stage1_independent_validation`
- Stage 2 outputs: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/mri_dense_validation/stage2_local_spiking`
- Report figures: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/reports/sites/mri_dense_validation/figures`

## Interpretation guardrails

- These MRI outputs are intentionally not merged into the unified dense report
  yet.
- Interpolated quality surfaces are diagnostic visualizations of point metrics,
  not gridded model products.
- The MRI source values are treated as volumetric soil water content percent.
  Values above 100% and zero/negative placeholders are filtered before daily
  profile means are computed.
