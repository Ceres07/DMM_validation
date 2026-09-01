# Model-agnostic covariate PCA and terrain residual stratification scaffold

This is a separate diagnostic report for the dense validation work. It is designed to sit beside the main dense-validation manuscript rather than replace it.

## 1. Purpose

The main question is whether the retained validation sites occupy comparable or distinct parts of the model-agnostic covariate space, and whether model failures occur in the same parts of that space across sites. This matters because a model can have acceptable pooled skill while still failing systematically in particular terrain, soil, exposure, or seasonal-climate contexts.

The analysis is framed around four working hypotheses.

1. **Absolute covariate-space transfer:** if a site sits far from the OzNet training distribution, both model6 and model8 should be treated as extrapolating or semi-extrapolating there.
2. **Covariate-space failure consistency:** if high-error points cluster in the same PCA region across sites, that suggests a transferable structural weakness.
3. **Scale-dependence of PCA:** global-scaled PCA should reveal between-site environmental differences, while site-standardised PCA should reveal within-site wet/dry terrain contrasts after removing site means.
4. **Model-type contrast:** the process model and statistical model may fail in different parts of the terrain/climate covariate space, which is directly relevant to local calibration design.

## 2. Data used

- Validation predictions: `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/unified_dense_validation/stage1_independent_validation/combined_model_agnostic_predictions.csv`
- OzNet training covariate table: `/Volumes/Dmitry_work/borevitz_projects/Data/oznet_model6_training_2006_2010.csv`
- Validation sites: Esdale, Tarrawarra, Nerrigundah, Llara, MRI.
- Models compared: model6 statistical RF/HGB and model8 process bucket.

All PCA inputs are model-agnostic covariates already present in the validation prediction table, not covariates from the raw point-measurement CSVs.

## 3. Feature spaces

Three related spaces are scaffolded.

1. **Static terrain-soil space:** elevation, slope, northness, eastness, TWI, HLI, accumulation, clay, sand, AWC, and bulk density. This is the cleanest terrain stratification space.
2. **Dynamic model-agnostic covariate space:** static terrain-soil plus SMIPS totalbucket, SMIPS lookback/anomaly terms, day-of-year terms, and SILO antecedent rainfall/water-balance/VPD terms.
3. **Process-context covariate space:** bucket storage where available plus the static process-model readout/capacity variables available in the unified table. This is included as exploratory because the complete process forcing/static matrix is not yet fully represented in the unified table for every site.

## 4. PCA methodology

### 4.1 Global-scaled PCA

For each feature space, features are median-imputed and standardised once across pooled validation supports. PCA is then fitted to the pooled support matrix. This preserves absolute between-site differences. Large separation of site centroids means the sites occupy different parts of covariate space.

Interpretation: this is the right view for asking whether the validation sites are genuinely different environments to the model.

### 4.2 Site-standardised PCA

For each site, every feature is z-scored within that site before fitting PCA across all supports. This removes the site-average environmental offset and keeps within-site structure. Local covariate extremes therefore become comparable across sites even when the absolute covariate distributions differ.

Interpretation: this is the right view for asking whether models fail in analogous within-property terrain positions.

## 5. Distance from training covariate space

Where the OzNet training covariate table is available, validation rows are compared with the training distribution in standardised feature space. Two distances are reported.

1. **Nearest-neighbour distance percentile:** distance from each validation row to its nearest OzNet training row, expressed as a percentile of OzNet leave-one-neighbour distances.
2. **Training-PCA Mahalanobis distance percentile:** validation rows are projected into PCA fitted on OzNet training rows. Distance from the OzNet centre is scaled by training PC variance and expressed as a percentile of training-row distances.

Rows above the 95th percentile are flagged as practically out-of-distribution for that feature space. This does not prove the prediction is wrong; it says the prediction is being made in a part of covariate space with weak training support.

## 6. Residual stratification methodology

For each site and support point/grid cell, observed and predicted soil moisture are summarised into support-level metrics. The PCA residual decomposition deliberately focuses on only two response variables:

1. **Bias**: prediction minus observation, used to diagnose signed wet/dry structure.
2. **RMSE**: error magnitude, used to diagnose unreliable regions regardless of sign.

NSE, Pearson r, and ubRMSE remain important validation metrics in the main manuscript, but they are not used here as PC-decomposition targets.

The diagnostic outputs are:

- high-RMSE locations in PCA space for each model;
- signed-bias locations in PCA space for each model;
- model6-minus-model8 RMSE difference in PCA space;
- correlations between PC axes and support-level RMSE and bias;
- a loading-weighted decomposition that identifies which covariates dominate the PC axes most associated with RMSE and bias;
- overlap between the worst 20% of supports for model6 and model8.

If both models fail on the same supports, this suggests a shared missing process, measurement/support mismatch, or terrain state not captured by the available inputs. If only one model fails, that gives clues about process-model versus statistical-model vulnerabilities.

## 7. Headline numeric outputs from this run

### PCA variance explained

| feature_set               | scaling           | PC1    | PC2    |
| ------------------------- | ----------------- | ------ | ------ |
| model_agnostic_covariates | global            | 33.254 | 21.227 |
| model_agnostic_covariates | site_standardised | 21.682 | 11.848 |
| static_terrain_soil       | global            | 32.401 | 20.178 |
| static_terrain_soil       | site_standardised | 21.732 | 18.980 |

### Site centroid distances in validation PCA space

| feature_set               | scaling           | site_a      | site_b      | pc1_pc2_distance | pc1_pc2_pc3_distance |
| ------------------------- | ----------------- | ----------- | ----------- | ---------------- | -------------------- |
| model_agnostic_covariates | global            | Esdale      | Llara       | 7.998            | 9.461                |
| model_agnostic_covariates | global            | Esdale      | MRI         | 4.585            | 5.628                |
| model_agnostic_covariates | global            | Esdale      | Nerrigundah | 6.669            | 6.669                |
| model_agnostic_covariates | global            | Esdale      | Tarrawarra  | 5.368            | 6.479                |
| model_agnostic_covariates | global            | Llara       | MRI         | 4.076            | 4.452                |
| model_agnostic_covariates | global            | Llara       | Nerrigundah | 7.638            | 9.189                |
| model_agnostic_covariates | global            | Llara       | Tarrawarra  | 9.856            | 9.958                |
| model_agnostic_covariates | global            | MRI         | Nerrigundah | 7.631            | 8.321                |
| model_agnostic_covariates | global            | MRI         | Tarrawarra  | 8.363            | 8.371                |
| model_agnostic_covariates | global            | Nerrigundah | Tarrawarra  | 3.444            | 5.042                |
| model_agnostic_covariates | site_standardised | Esdale      | Llara       | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Esdale      | MRI         | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Esdale      | Nerrigundah | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Esdale      | Tarrawarra  | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Llara       | MRI         | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Llara       | Nerrigundah | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Llara       | Tarrawarra  | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | MRI         | Nerrigundah | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | MRI         | Tarrawarra  | 0.000            | 0.000                |
| model_agnostic_covariates | site_standardised | Nerrigundah | Tarrawarra  | 0.000            | 0.000                |
| static_terrain_soil       | global            | Esdale      | Llara       | 4.827            | 4.971                |
| static_terrain_soil       | global            | Esdale      | MRI         | 0.426            | 3.357                |
| static_terrain_soil       | global            | Esdale      | Nerrigundah | 4.900            | 4.925                |
| static_terrain_soil       | global            | Esdale      | Tarrawarra  | 3.984            | 3.998                |
| static_terrain_soil       | global            | Llara       | MRI         | 4.839            | 5.292                |
| static_terrain_soil       | global            | Llara       | Nerrigundah | 3.756            | 3.820                |
| static_terrain_soil       | global            | Llara       | Tarrawarra  | 1.049            | 1.850                |
| static_terrain_soil       | global            | MRI         | Nerrigundah | 4.602            | 5.409                |
| static_terrain_soil       | global            | MRI         | Tarrawarra  | 3.939            | 5.381                |
| static_terrain_soil       | global            | Nerrigundah | Tarrawarra  | 2.967            | 3.079                |
| static_terrain_soil       | site_standardised | Esdale      | Llara       | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Esdale      | MRI         | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Esdale      | Nerrigundah | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Esdale      | Tarrawarra  | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Llara       | MRI         | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Llara       | Nerrigundah | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Llara       | Tarrawarra  | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | MRI         | Nerrigundah | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | MRI         | Tarrawarra  | 0.000            | 0.000                |
| static_terrain_soil       | site_standardised | Nerrigundah | Tarrawarra  | 0.000            | 0.000                |

### Model failure overlap by site

| site        | n_supports | worst_set_size | shared_worst_supports | jaccard_top20pct_worst_rmse | rmse_correlation_model6_model8 | bias_correlation_model6_model8 | model8_better_fraction |
| ----------- | ---------- | -------------- | --------------------- | --------------------------- | ------------------------------ | ------------------------------ | ---------------------- |
| Esdale      | 77.000     | 16.000         | 8.000                 | 0.333                       | 0.476                          | 0.858                          | 0.494                  |
| Llara       | 32.000     | 7.000          | 5.000                 | 0.556                       | 0.796                          | 0.950                          | 0.531                  |
| MRI         | 18.000     | 4.000          | 3.000                 | 0.600                       | 0.986                          | 0.990                          | 0.556                  |
| Nerrigundah | 128.000    | 26.000         | 14.000                | 0.368                       | 0.525                          | 0.986                          | 0.523                  |
| Tarrawarra  | 169.000    | 34.000         | 26.000                | 0.619                       | 0.897                          | 0.873                          | 1.000                  |

### Distance from OzNet training space

| feature_set               | site        | n_validation_rows | n_common_features | median_nn_percentile | p90_nn_percentile | fraction_nn_gt95 | median_mahalanobis_percentile | fraction_mahalanobis_gt95 |
| ------------------------- | ----------- | ----------------- | ----------------- | -------------------- | ----------------- | ---------------- | ----------------------------- | ------------------------- |
| static_terrain_soil       | Esdale      | 560.000           | 11.000            | 86.111               | 100.000           | 0.263            | 83.333                        | 0.180                     |
| static_terrain_soil       | Llara       | 28390.000         | 11.000            | 88.889               | 100.000           | 0.155            | 80.556                        | 0.155                     |
| static_terrain_soil       | MRI         | 29046.000         | 11.000            | 88.889               | 97.222            | 0.121            | 83.333                        | 0.062                     |
| static_terrain_soil       | Nerrigundah | 1536.000          | 11.000            | 88.889               | 88.889            | 0.000            | 91.667                        | 0.258                     |
| static_terrain_soil       | Tarrawarra  | 2154.000          | 11.000            | 86.111               | 88.889            | 0.000            | 36.111                        | 0.000                     |
| model_agnostic_covariates | Esdale      | 560.000           | 25.000            | 100.000              | 100.000           | 1.000            | 62.590                        | 0.070                     |
| model_agnostic_covariates | Llara       | 28390.000         | 25.000            | 100.000              | 100.000           | 1.000            | 98.318                        | 0.840                     |
| model_agnostic_covariates | MRI         | 29046.000         | 25.000            | 100.000              | 100.000           | 1.000            | 91.837                        | 0.376                     |
| model_agnostic_covariates | Nerrigundah | 1536.000          | 25.000            | 100.000              | 100.000           | 1.000            | 90.523                        | 0.043                     |
| model_agnostic_covariates | Tarrawarra  | 2154.000          | 25.000            | 100.000              | 100.000           | 1.000            | 98.662                        | 0.863                     |

### Seasonal distance from OzNet training space

| feature_set               | site        | season | n_validation_rows | median_nn_percentile | fraction_nn_gt95 | median_mahalanobis_percentile | fraction_mahalanobis_gt95 |
| ------------------------- | ----------- | ------ | ----------------- | -------------------- | ---------------- | ----------------------------- | ------------------------- |
| static_terrain_soil       | Esdale      | autumn | 308.000           | 86.111               | 0.260            | 83.333                        | 0.182                     |
| static_terrain_soil       | Esdale      | winter | 252.000           | 86.111               | 0.266            | 83.333                        | 0.179                     |
| static_terrain_soil       | Llara       | autumn | 8617.000          | 88.889               | 0.149            | 80.556                        | 0.149                     |
| static_terrain_soil       | Llara       | spring | 5821.000          | 88.889               | 0.156            | 80.556                        | 0.156                     |
| static_terrain_soil       | Llara       | summer | 7188.000          | 88.889               | 0.158            | 80.556                        | 0.158                     |
| static_terrain_soil       | Llara       | winter | 6764.000          | 88.889               | 0.156            | 80.556                        | 0.156                     |
| static_terrain_soil       | MRI         | autumn | 7179.000          | 88.889               | 0.119            | 83.333                        | 0.064                     |
| static_terrain_soil       | MRI         | spring | 7490.000          | 88.889               | 0.120            | 83.333                        | 0.061                     |
| static_terrain_soil       | MRI         | summer | 7129.000          | 88.889               | 0.126            | 83.333                        | 0.063                     |
| static_terrain_soil       | MRI         | winter | 7248.000          | 88.889               | 0.119            | 83.333                        | 0.060                     |
| static_terrain_soil       | Nerrigundah | spring | 1280.000          | 88.889               | 0.000            | 91.667                        | 0.258                     |
| static_terrain_soil       | Nerrigundah | winter | 256.000           | 88.889               | 0.000            | 91.667                        | 0.258                     |
| static_terrain_soil       | Tarrawarra  | autumn | 663.000           | 86.111               | 0.000            | 36.111                        | 0.000                     |
| static_terrain_soil       | Tarrawarra  | spring | 994.000           | 86.111               | 0.000            | 36.111                        | 0.000                     |
| static_terrain_soil       | Tarrawarra  | summer | 333.000           | 86.111               | 0.000            | 36.111                        | 0.000                     |
| static_terrain_soil       | Tarrawarra  | winter | 164.000           | 86.111               | 0.000            | 36.111                        | 0.000                     |
| model_agnostic_covariates | Esdale      | autumn | 308.000           | 100.000              | 1.000            | 69.958                        | 0.107                     |
| model_agnostic_covariates | Esdale      | winter | 252.000           | 100.000              | 1.000            | 51.475                        | 0.024                     |
| model_agnostic_covariates | Llara       | autumn | 8617.000          | 100.000              | 1.000            | 98.543                        | 0.907                     |
| model_agnostic_covariates | Llara       | spring | 5821.000          | 100.000              | 1.000            | 98.451                        | 0.857                     |
| model_agnostic_covariates | Llara       | summer | 7188.000          | 100.000              | 1.000            | 98.098                        | 0.819                     |
| model_agnostic_covariates | Llara       | winter | 6764.000          | 100.000              | 1.000            | 97.986                        | 0.761                     |
| model_agnostic_covariates | MRI         | autumn | 7179.000          | 100.000              | 1.000            | 90.971                        | 0.346                     |
| model_agnostic_covariates | MRI         | spring | 7490.000          | 100.000              | 1.000            | 92.814                        | 0.409                     |
| model_agnostic_covariates | MRI         | summer | 7129.000          | 100.000              | 1.000            | 93.159                        | 0.412                     |
| model_agnostic_covariates | MRI         | winter | 7248.000          | 100.000              | 1.000            | 91.362                        | 0.336                     |
| model_agnostic_covariates | Nerrigundah | spring | 1280.000          | 100.000              | 1.000            | 90.197                        | 0.035                     |
| model_agnostic_covariates | Nerrigundah | winter | 256.000           | 100.000              | 1.000            | 92.851                        | 0.082                     |
| model_agnostic_covariates | Tarrawarra  | autumn | 663.000           | 100.000              | 1.000            | 99.478                        | 1.000                     |
| model_agnostic_covariates | Tarrawarra  | spring | 994.000           | 100.000              | 1.000            | 96.649                        | 0.702                     |
| model_agnostic_covariates | Tarrawarra  | summer | 333.000           | 100.000              | 1.000            | 99.117                        | 1.000                     |
| model_agnostic_covariates | Tarrawarra  | winter | 164.000           | 100.000              | 1.000            | 98.268                        | 1.000                     |

### Correlation between training distance and absolute error

| feature_set               | base_model     | n         | distance_abs_error_correlation | median_abs_error_in_distribution | median_abs_error_above_95pct |
| ------------------------- | -------------- | --------- | ------------------------------ | -------------------------------- | ---------------------------- |
| static_terrain_soil       | model6_rf      | 61686.000 | 0.007                          | 8.130                            | 5.742                        |
| static_terrain_soil       | model8_process | 61686.000 | 0.024                          | 7.463                            | 5.470                        |
| model_agnostic_covariates | model6_rf      | 61686.000 | 0.007                          |                                  | 7.681                        |
| model_agnostic_covariates | model8_process | 61686.000 | 0.003                          |                                  | 7.037                        |

### Strongest PC associations with bias and RMSE

| feature_set               | scaling           | site        | pc_axis | metric                       | pc_metric_correlation | n_supports |
| ------------------------- | ----------------- | ----------- | ------- | ---------------------------- | --------------------- | ---------- |
| static_terrain_soil       | site_standardised | Esdale      | PC1     | bias_model6_rf               | -0.605                | 77.000     |
| static_terrain_soil       | site_standardised | Nerrigundah | PC1     | bias_model6_rf               | -0.595                | 128.000    |
| static_terrain_soil       | site_standardised | Nerrigundah | PC1     | bias_model8_process          | -0.592                | 128.000    |
| model_agnostic_covariates | site_standardised | Esdale      | PC2     | bias_model6_rf               | -0.581                | 77.000     |
| static_terrain_soil       | site_standardised | Esdale      | PC1     | bias_model8_process          | -0.576                | 77.000     |
| static_terrain_soil       | site_standardised | Esdale      | PC1     | abs_bias_model6_minus_model8 | 0.564                 | 77.000     |
| static_terrain_soil       | site_standardised | MRI         | PC1     | bias_model6_rf               | 0.564                 | 18.000     |
| model_agnostic_covariates | site_standardised | Nerrigundah | PC2     | bias_model8_process          | -0.563                | 128.000    |
| static_terrain_soil       | site_standardised | MRI         | PC1     | bias_model8_process          | 0.562                 | 18.000     |
| static_terrain_soil       | site_standardised | Nerrigundah | PC1     | rmse_model6_minus_model8     | 0.557                 | 128.000    |
| model_agnostic_covariates | site_standardised | Nerrigundah | PC2     | bias_model6_rf               | -0.550                | 128.000    |
| model_agnostic_covariates | site_standardised | Esdale      | PC2     | abs_bias_model6_minus_model8 | 0.543                 | 77.000     |
| model_agnostic_covariates | site_standardised | MRI         | PC1     | rmse_model6_rf               | 0.525                 | 18.000     |
| model_agnostic_covariates | site_standardised | MRI         | PC1     | bias_model6_rf               | -0.523                | 18.000     |
| model_agnostic_covariates | site_standardised | MRI         | PC1     | bias_model8_process          | -0.521                | 18.000     |
| model_agnostic_covariates | site_standardised | MRI         | PC1     | rmse_model8_process          | 0.519                 | 18.000     |
| model_agnostic_covariates | site_standardised | Tarrawarra  | PC2     | bias_model8_process          | -0.518                | 169.000    |
| model_agnostic_covariates | site_standardised | Llara       | PC2     | bias_model6_rf               | 0.517                 | 32.000     |
| static_terrain_soil       | site_standardised | Esdale      | PC1     | rmse_model6_minus_model8     | 0.514                 | 77.000     |
| model_agnostic_covariates | site_standardised | Nerrigundah | PC2     | rmse_model6_minus_model8     | 0.510                 | 128.000    |
| static_terrain_soil       | site_standardised | Nerrigundah | PC1     | abs_bias_model6_minus_model8 | 0.502                 | 128.000    |
| model_agnostic_covariates | site_standardised | Esdale      | PC2     | bias_model8_process          | -0.488                | 77.000     |
| static_terrain_soil       | site_standardised | Tarrawarra  | PC3     | abs_bias_model6_minus_model8 | -0.486                | 169.000    |
| model_agnostic_covariates | site_standardised | Esdale      | PC2     | rmse_model6_minus_model8     | 0.479                 | 77.000     |
| static_terrain_soil       | site_standardised | Llara       | PC3     | bias_model6_rf               | 0.476                 | 32.000     |
| static_terrain_soil       | site_standardised | Tarrawarra  | PC1     | bias_model8_process          | -0.474                | 169.000    |
| static_terrain_soil       | site_standardised | Tarrawarra  | PC3     | rmse_model6_minus_model8     | -0.474                | 169.000    |
| model_agnostic_covariates | site_standardised | Nerrigundah | PC2     | abs_bias_model6_minus_model8 | 0.464                 | 128.000    |
| static_terrain_soil       | site_standardised | Esdale      | PC1     | rmse_model8_process          | -0.452                | 77.000     |
| model_agnostic_covariates | site_standardised | MRI         | PC3     | rmse_model6_minus_model8     | -0.450                | 18.000     |

### Site-standardised PC feature decomposition

This table back-projects the PC/error correlations through the PCA loadings. It is a diagnostic ranking, not a causal attribution model.

| feature_set               | metric_family | feature       | mean_abs_contribution | max_abs_contribution | mean_signed_contribution | n_tests |
| ------------------------- | ------------- | ------------- | --------------------- | -------------------- | ------------------------ | ------- |
| model_agnostic_covariates | RMSE          | hli           | 0.063                 | 0.286                | 0.004                    | 45.000  |
| model_agnostic_covariates | RMSE          | soil_sand     | 0.059                 | 0.189                | 0.016                    | 45.000  |
| model_agnostic_covariates | RMSE          | soil_clay     | 0.056                 | 0.173                | -0.015                   | 45.000  |
| model_agnostic_covariates | RMSE          | northness     | 0.052                 | 0.232                | 0.003                    | 45.000  |
| model_agnostic_covariates | RMSE          | elevation     | 0.052                 | 0.151                | 0.007                    | 45.000  |
| model_agnostic_covariates | RMSE          | slope         | 0.051                 | 0.196                | 0.008                    | 45.000  |
| model_agnostic_covariates | RMSE          | vpd_30        | 0.049                 | 0.161                | -0.002                   | 45.000  |
| model_agnostic_covariates | RMSE          | rain_365_anom | 0.045                 | 0.154                | -0.008                   | 45.000  |
| model_agnostic_covariates | bias          | hli           | 0.087                 | 0.326                | -0.002                   | 45.000  |
| model_agnostic_covariates | bias          | northness     | 0.072                 | 0.265                | -0.002                   | 45.000  |
| model_agnostic_covariates | bias          | slope         | 0.067                 | 0.223                | -0.004                   | 45.000  |
| model_agnostic_covariates | bias          | soil_sand     | 0.062                 | 0.170                | -0.006                   | 45.000  |
| model_agnostic_covariates | bias          | soil_clay     | 0.059                 | 0.156                | 0.005                    | 45.000  |
| model_agnostic_covariates | bias          | elevation     | 0.058                 | 0.145                | -0.002                   | 45.000  |
| model_agnostic_covariates | bias          | eastness      | 0.053                 | 0.148                | 0.002                    | 45.000  |
| model_agnostic_covariates | bias          | vpd_30        | 0.052                 | 0.160                | 0.003                    | 45.000  |
| static_terrain_soil       | RMSE          | soil_clay     | 0.084                 | 0.208                | -0.034                   | 45.000  |
| static_terrain_soil       | RMSE          | soil_sand     | 0.083                 | 0.201                | 0.032                    | 45.000  |
| static_terrain_soil       | RMSE          | hli           | 0.083                 | 0.282                | -0.013                   | 45.000  |
| static_terrain_soil       | RMSE          | slope         | 0.065                 | 0.208                | -0.010                   | 45.000  |
| static_terrain_soil       | RMSE          | accumulation  | 0.064                 | 0.176                | 0.017                    | 45.000  |
| static_terrain_soil       | RMSE          | northness     | 0.063                 | 0.246                | -0.003                   | 45.000  |
| static_terrain_soil       | RMSE          | twi           | 0.062                 | 0.182                | 0.016                    | 45.000  |
| static_terrain_soil       | RMSE          | eastness      | 0.053                 | 0.146                | -0.019                   | 45.000  |
| static_terrain_soil       | bias          | hli           | 0.109                 | 0.307                | 0.011                    | 45.000  |
| static_terrain_soil       | bias          | soil_clay     | 0.103                 | 0.213                | 0.016                    | 45.000  |
| static_terrain_soil       | bias          | soil_sand     | 0.101                 | 0.218                | -0.014                   | 45.000  |
| static_terrain_soil       | bias          | slope         | 0.085                 | 0.226                | 0.010                    | 45.000  |
| static_terrain_soil       | bias          | northness     | 0.083                 | 0.267                | 0.004                    | 45.000  |
| static_terrain_soil       | bias          | accumulation  | 0.066                 | 0.180                | -0.013                   | 45.000  |
| static_terrain_soil       | bias          | twi           | 0.062                 | 0.187                | -0.013                   | 45.000  |
| static_terrain_soil       | bias          | eastness      | 0.061                 | 0.150                | 0.011                    | 45.000  |

### Direct site-standardised covariate/error correlations

This is a simpler companion diagnostic: support-level covariates are standardised within each site, then directly correlated with bias and RMSE metrics.

| metric_family | feature    | mean_abs_correlation | max_abs_correlation | n_tests |
| ------------- | ---------- | -------------------- | ------------------- | ------- |
| RMSE          | northness  | 0.290                | 0.526               | 15.000  |
| RMSE          | rain_7     | 0.271                | 0.523               | 15.000  |
| RMSE          | soil_sand  | 0.263                | 0.535               | 15.000  |
| RMSE          | doy_sin    | 0.257                | 0.476               | 15.000  |
| RMSE          | hli        | 0.252                | 0.420               | 15.000  |
| RMSE          | smips_365d | 0.246                | 0.465               | 15.000  |
| RMSE          | soil_clay  | 0.242                | 0.512               | 15.000  |
| RMSE          | elevation  | 0.240                | 0.491               | 15.000  |
| RMSE          | ppet_365   | 0.225                | 0.535               | 15.000  |
| RMSE          | smips_anom | 0.218                | 0.373               | 15.000  |
| bias          | northness  | 0.388                | 0.665               | 15.000  |
| bias          | hli        | 0.377                | 0.525               | 15.000  |
| bias          | soil_sand  | 0.333                | 0.649               | 15.000  |
| bias          | slope      | 0.305                | 0.476               | 15.000  |
| bias          | soil_clay  | 0.290                | 0.573               | 15.000  |
| bias          | rain_7     | 0.277                | 0.445               | 15.000  |
| bias          | elevation  | 0.257                | 0.536               | 15.000  |
| bias          | doy_sin    | 0.217                | 0.513               | 15.000  |
| bias          | eastness   | 0.196                | 0.381               | 15.000  |
| bias          | rain_30    | 0.194                | 0.548               | 15.000  |

### Dominant PCA loadings

| feature_set               | scaling           | feature           | PC1_loading | PC2_loading | PC1_PC2_abs_loading |
| ------------------------- | ----------------- | ----------------- | ----------- | ----------- | ------------------- |
| model_agnostic_covariates | global            | ppet_30           | -0.093      | 0.385       | 0.397               |
| model_agnostic_covariates | global            | soil_sand         | 0.073       | 0.371       | 0.378               |
| model_agnostic_covariates | global            | elevation         | 0.267       | 0.210       | 0.340               |
| model_agnostic_covariates | global            | vpd_30            | 0.163       | -0.292      | 0.334               |
| model_agnostic_covariates | global            | smips_totalbucket | 0.333       | 0.020       | 0.334               |
| model_agnostic_covariates | global            | rain_365          | -0.245      | -0.226      | 0.333               |
| model_agnostic_covariates | site_standardised | hli               | -0.058      | 0.562       | 0.564               |
| model_agnostic_covariates | site_standardised | northness         | -0.066      | 0.456       | 0.461               |
| model_agnostic_covariates | site_standardised | ppet_30           | 0.410       | 0.048       | 0.413               |
| model_agnostic_covariates | site_standardised | rain_365          | 0.409       | 0.039       | 0.411               |
| model_agnostic_covariates | site_standardised | ppet_365          | 0.397       | 0.040       | 0.399               |
| model_agnostic_covariates | site_standardised | slope             | -0.048      | 0.385       | 0.388               |
| static_terrain_soil       | global            | soil_awc          | 0.115       | 0.537       | 0.549               |
| static_terrain_soil       | global            | soil_bdw          | 0.405       | -0.316      | 0.514               |
| static_terrain_soil       | global            | eastness          | -0.296      | -0.410      | 0.505               |
| static_terrain_soil       | global            | hli               | -0.334      | -0.361      | 0.492               |
| static_terrain_soil       | global            | soil_sand         | 0.434       | 0.193       | 0.475               |
| static_terrain_soil       | global            | soil_clay         | -0.397      | 0.240       | 0.464               |
| static_terrain_soil       | site_standardised | hli               | 0.506       | 0.147       | 0.527               |
| static_terrain_soil       | site_standardised | twi               | -0.024      | 0.523       | 0.523               |
| static_terrain_soil       | site_standardised | accumulation      | 0.066       | 0.498       | 0.502               |
| static_terrain_soil       | site_standardised | soil_sand         | 0.360       | -0.323      | 0.484               |
| static_terrain_soil       | site_standardised | northness         | 0.442       | 0.150       | 0.467               |
| static_terrain_soil       | site_standardised | soil_clay         | -0.352      | 0.293       | 0.458               |

## 8. Figures

### Static terrain-soil PCA

![Static global PCA sites](figures/model_space_pca/static_terrain_soil_global_site_pca.png)

![Static site-standardised PCA sites](figures/model_space_pca/static_terrain_soil_site_standardised_site_pca.png)

![Static global PCA RMSE](figures/model_space_pca/static_terrain_soil_global_rmse_pca.png)

![Static global PCA bias](figures/model_space_pca/static_terrain_soil_global_bias_pca.png)

![Static site-standardised PCA RMSE](figures/model_space_pca/static_terrain_soil_site_standardised_rmse_pca.png)

![Static site-standardised PCA bias](figures/model_space_pca/static_terrain_soil_site_standardised_bias_pca.png)

![Static global model difference](figures/model_space_pca/static_terrain_soil_global_model_difference_pca.png)

![Static site-standardised model difference](figures/model_space_pca/static_terrain_soil_site_standardised_model_difference_pca.png)

### Dynamic model-agnostic covariate PCA and training distance

![Dynamic covariate global PCA sites](figures/model_space_pca/model_agnostic_covariates_global_site_pca.png)

![Dynamic covariate site-standardised PCA sites](figures/model_space_pca/model_agnostic_covariates_site_standardised_site_pca.png)

![Dynamic covariate training distance](figures/model_space_pca/model_agnostic_covariates_training_distance_by_site.png)

![Dynamic covariate seasonal Mahalanobis distance](figures/model_space_pca/model_agnostic_covariates_training_mahalanobis_by_site_season.png)

![Dynamic covariate seasonal distance skill](figures/model_space_pca/model_agnostic_covariates_seasonal_distance_skill.png)

![Dynamic covariate distance error](figures/model_space_pca/model_agnostic_covariates_training_distance_vs_abs_error.png)

## 9. Interpretation guardrails

- PCA axes are descriptive rotations of correlated covariates; they are not physical mechanisms by themselves. Loadings should be used to name axes cautiously.
- Global-scaled PCA is best for between-site transfer questions. Site-standardised PCA is best for within-site terrain analogues. These are complementary rather than competing versions.
- Training distance is covariate-space distance, not geographic distance. A point can be geographically close to OzNet-like terrain and still be seasonally outlying in the dynamic covariate space.
- Tarrawarra observations have been aggregated to the 30 m prediction support in the upstream validation table; residual sub-pixel variation should still be treated as support mismatch where within-cell variance is high.
- The model8 process-context PCA is exploratory until the unified table carries the complete process-model forcing/static variables for every site.

## 10. Suggested manuscript use

For the publication-facing report, I would use:

1. one global-scaled static terrain-soil PCA panel to show site separation;
2. one site-standardised static PCA panel coloured by RMSE to show whether bad supports occupy analogous covariate positions, with signed-bias PCA retained as a diagnostic supplement;
3. one dynamic covariate-space training-distance figure to quantify how far each validation site/date is from OzNet;
4. a small table of PC-decomposed bias/RMSE associations and worst-support overlap.

That combination keeps the story sharp: first, where are these sites relative to each other and to training; second, are the failures terrain-structured; third, does the process model fail differently from the statistical model?
