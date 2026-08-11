# Three-site sparse local calibration: Esdale, Tarrawarra and Llara

This report replaces the Phenode-based local calibration experiment. From here
on, the original dense validation site is called **Esdale**, so each dense site
has a unique name.

The practical question is: if a landowner can afford one or a few soil-moisture
sensors, can that tiny local information budget improve property-scale
downscaling enough to matter? The experiment deliberately assumes that a new
site starts with **no measured soil moisture map**. Sensor locations are
therefore chosen using:

- random point selection;
- a terrain/model-input wet-dry landscape prior;
- global prediction extremes;
- an explicitly labelled `field_knowledge_wetdry_proxy`, which uses observed
  chronic wet/dry points as a proxy for landowner knowledge and should not be
  treated as a fully deployable selection rule.

## Blocking design

Each site is tested under three blocks:

1. `spatial_block`: fit selected calibration points across all available dense
   dates, validate unselected points.
2. `temporal_block`: fit selected calibration points in the early dense dates,
   validate those same points in later dates.
3. `spatiotemporal_block`: fit selected calibration points in early dates,
   validate different points in later dates. This is the strictest and most
   relevant property-map transfer test.

Calibration methods:

- `bias_offset`: one local residual offset;
- `affine`: local intercept and slope correction;
- `residual_ridge`: strongly regularised residual layer using only
  prediction-time model inputs and terrain/soil/weather state.

## Site inputs

| site       | path                                                                                                                                   | rows      | models                   | points   | eligible_points_train_and_future | dates   | date_min   | date_max   | train_dates | future_dates | seasons                     |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------ | -------- | -------------------------------- | ------- | ---------- | ---------- | ----------- | ------------ | --------------------------- |
| Esdale     | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv            | 1120.000  | model6_rf,model8_process | 79.000   | 76.000                           | 9.000   | 2025-04-30 | 2025-07-17 | 3.000       | 6.000        | autumn,winter               |
| Tarrawarra | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid.csv | 17290.000 | model6_rf,model8_process | 3610.000 | 517.000                          | 19.000  | 1995-09-25 | 1996-11-29 | 7.000       | 12.000       | autumn,spring,summer,winter |
| Llara      | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv        | 58494.000 | model6_rf,model8_process | 32.000   | 32.000                           | 955.000 | 2021-10-19 | 2024-06-30 | 316.000     | 639.000      | autumn,spring,summer,winter |

Tarrawarra model6 should be read with a special caveat: the historical SMIPS inputs in the existing Tarrawarra run are zero, so model6 there is closer to a missing-coarse-anchor ablation than a normal model6 run.

## Uncalibrated global model skill

| site       | base_model     | model_track    | n         | nse    | r2     | pearson_r | pearson_r2 | rmse   | ubrmse | bias    | mae    | median_ae | pred_vs_obs_slope | pred_vs_obs_intercept |
| ---------- | -------------- | -------------- | --------- | ------ | ------ | --------- | ---------- | ------ | ------ | ------- | ------ | --------- | ----------------- | --------------------- |
| Esdale     | model6_rf      | statistical_rf | 560.000   | 0.023  | 0.023  | 0.238     | 0.057      | 6.477  | 6.453  | -0.558  | 5.209  | 4.415     | 0.096             | 14.876                |
| Esdale     | model8_process | process_bucket | 560.000   | 0.031  | 0.031  | 0.462     | 0.213      | 6.452  | 5.884  | 2.645   | 5.199  | 4.476     | 0.277             | 14.981                |
| Tarrawarra | model6_rf      | statistical_rf | 8645.000  | -1.614 | -1.614 | 0.394     | 0.155      | 15.080 | 8.770  | -12.267 | 12.707 | 13.111    | 0.077             | 20.785                |
| Tarrawarra | model8_process | process_bucket | 8645.000  | -0.133 | -0.133 | 0.831     | 0.690      | 9.929  | 6.894  | -7.146  | 8.147  | 7.393     | 0.286             | 18.417                |
| Llara      | model6_rf      | statistical_rf | 29247.000 | 0.036  | 0.036  | 0.267     | 0.071      | 13.927 | 13.744 | -2.249  | 10.872 | 9.007     | 0.098             | 25.636                |
| Llara      | model8_process | process_bucket | 29247.000 | -0.017 | -0.017 | 0.453     | 0.205      | 14.306 | 12.855 | -6.278  | 10.796 | 7.831     | 0.132             | 20.566                |

## Headline inference

- Under the strict random one-sensor test, **model8 process is usually more
  responsive than model6 RF at Esdale and Llara**, especially for simple
  bias-offset calibration. This is the cleanest evidence so far that the
  process model may provide a more stable base for tiny local information
  budgets.
- Tarrawarra is different: both models improve strongly with sparse local
  calibration, but model6 often shows larger RMSE gains because its uncalibrated
  bias is very large. However, model8 generally remains the lower-RMSE model
  after calibration. Interpret this alongside the Tarrawarra SMIPS-zero caveat.
- One random sensor is not consistently enough. It helps model8 at Esdale and
  Tarrawarra, but worsens Llara unless more points are supplied. In the random
  strict block, Llara model8 begins to improve with 2-5 calibration points,
  while model6 remains much less responsive.
- The field-knowledge/landscape-prior selections can outperform random
  placement in some cases, which supports the practical idea of putting a
  sensor in an intuitively wet/dry part of the property. But the
  `field_knowledge_wetdry_proxy` is an upper-bound proxy, not a blind deployment
  rule.
- The residual-ridge layer is useful in selected cases, but simple
  `bias_offset` is often the most robust sparse-sensor calibration layer. This
  matters for deployability: a landowner-facing calibration should probably
  start with a small, interpretable correction before adding flexible residual
  models.

## Best one-sensor strict spatio-temporal result

For each site and model, this table selects the best one-sensor calibration
method/selection strategy by median RMSE under the strict block.

| site       | base_model     | selection_strategy         | method         | rmse_median | rmse_gain_median | nse_median | delta_nse_median | bias_median | delta_abs_bias_median | n_replicates |
| ---------- | -------------- | -------------------------- | -------------- | ----------- | ---------------- | ---------- | ---------------- | ----------- | --------------------- | ------------ |
| Esdale     | model6_rf      | landscape_wetdry_prior     | residual_ridge | 4.926       | 0.279            | -0.249     | 0.145            | 0.127       | -1.558                | 1.000        |
| Esdale     | model8_process | global_prediction_extremes | residual_ridge | 4.515       | 0.808            | -0.049     | 0.409            | -0.851      | -2.095                | 1.000        |
| Llara      | model6_rf      | global_prediction_extremes | affine         | 12.745      | -0.213           | 0.000      | -0.033           | -0.041      | -3.206                | 1.000        |
| Llara      | model8_process | global_prediction_extremes | affine         | 12.179      | 1.253            | 0.087      | 0.198            | -1.838      | -5.252                | 1.000        |
| Tarrawarra | model6_rf      | landscape_wetdry_prior     | residual_ridge | 11.703      | 4.406            | -0.785     | 1.597            | -8.365      | -5.510                | 1.000        |
| Tarrawarra | model8_process | landscape_wetdry_prior     | affine         | 7.237       | 3.209            | 0.318      | 0.740            | -3.434      | -4.845                | 1.000        |

## Random sparse-sensor learning curves

This table is the most defensible deployment-oriented result because it does
not assume the landowner already knows where the model fails. Positive
`rmse_gain_median` and `delta_nse_median` indicate improvement over the
uncalibrated global model on the same held-out rows.

| site       | calibration_points | base_model     | method         | rmse_median | rmse_gain_median | nse_median | delta_nse_median | bias_median | n_replicates |
| ---------- | ------------------ | -------------- | -------------- | ----------- | ---------------- | ---------- | ---------------- | ----------- | ------------ |
| Esdale     | 1.000              | model6_rf      | affine         | 5.553       | -0.323           | -0.572     | -0.177           | -1.825      | 30.000       |
| Esdale     | 1.000              | model6_rf      | bias_offset    | 5.553       | -0.323           | -0.572     | -0.177           | -1.825      | 30.000       |
| Esdale     | 1.000              | model6_rf      | residual_ridge | 5.553       | -0.323           | -0.572     | -0.177           | -1.825      | 30.000       |
| Esdale     | 1.000              | model8_process | affine         | 5.048       | 0.249            | -0.303     | 0.132            | 1.343       | 30.000       |
| Esdale     | 1.000              | model8_process | bias_offset    | 5.048       | 0.249            | -0.303     | 0.132            | 1.343       | 30.000       |
| Esdale     | 1.000              | model8_process | residual_ridge | 5.048       | 0.249            | -0.303     | 0.132            | 1.343       | 30.000       |
| Esdale     | 2.000              | model6_rf      | affine         | 7.558       | -2.331           | -1.931     | -1.533           | -5.927      | 30.000       |
| Esdale     | 2.000              | model6_rf      | bias_offset    | 6.094       | -0.844           | -0.891     | -0.488           | -3.572      | 30.000       |
| Esdale     | 2.000              | model6_rf      | residual_ridge | 5.346       | -0.132           | -0.459     | -0.072           | -2.163      | 30.000       |
| Esdale     | 2.000              | model8_process | affine         | 8.280       | -2.995           | -2.514     | -2.082           | 5.021       | 30.000       |
| Esdale     | 2.000              | model8_process | bias_offset    | 4.810       | 0.461            | -0.182     | 0.239            | -0.093      | 30.000       |
| Esdale     | 2.000              | model8_process | residual_ridge | 4.786       | 0.472            | -0.168     | 0.242            | 1.358       | 30.000       |
| Esdale     | 3.000              | model6_rf      | affine         | 6.726       | -1.669           | -1.405     | -1.046           | -5.035      | 30.000       |
| Esdale     | 3.000              | model6_rf      | bias_offset    | 5.504       | -0.296           | -0.543     | -0.164           | -2.523      | 30.000       |
| Esdale     | 3.000              | model6_rf      | residual_ridge | 4.757       | 0.343            | -0.201     | 0.176            | -0.275      | 30.000       |
| Esdale     | 3.000              | model8_process | affine         | 7.622       | -2.357           | -1.997     | -1.590           | -1.604      | 30.000       |
| Esdale     | 3.000              | model8_process | bias_offset    | 4.687       | 0.645            | -0.108     | 0.326            | 0.843       | 30.000       |
| Esdale     | 3.000              | model8_process | residual_ridge | 5.059       | 0.196            | -0.311     | 0.104            | 2.916       | 30.000       |
| Esdale     | 5.000              | model6_rf      | affine         | 7.282       | -2.046           | -1.709     | -1.307           | -5.625      | 30.000       |
| Esdale     | 5.000              | model6_rf      | bias_offset    | 5.703       | -0.516           | -0.687     | -0.295           | -2.946      | 30.000       |
| Esdale     | 5.000              | model6_rf      | residual_ridge | 4.764       | 0.414            | -0.157     | 0.210            | 0.281       | 30.000       |
| Esdale     | 5.000              | model8_process | affine         | 6.151       | -0.832           | -0.956     | -0.492           | -2.430      | 30.000       |
| Esdale     | 5.000              | model8_process | bias_offset    | 4.586       | 0.731            | -0.069     | 0.362            | 0.379       | 30.000       |
| Esdale     | 5.000              | model8_process | residual_ridge | 5.852       | -0.468           | -0.727     | -0.265           | 4.062       | 30.000       |
| Llara      | 1.000              | model6_rf      | affine         | 17.687      | -5.438           | -0.920     | -1.014           | -7.625      | 30.000       |
| Llara      | 1.000              | model6_rf      | bias_offset    | 18.158      | -5.914           | -0.992     | -1.086           | -5.416      | 30.000       |
| Llara      | 1.000              | model6_rf      | residual_ridge | 18.515      | -6.279           | -1.060     | -1.163           | -6.982      | 30.000       |
| Llara      | 1.000              | model8_process | affine         | 19.837      | -6.343           | -1.356     | -1.267           | -8.259      | 30.000       |
| Llara      | 1.000              | model8_process | bias_offset    | 15.282      | -1.804           | -0.385     | -0.308           | -7.131      | 30.000       |
| Llara      | 1.000              | model8_process | residual_ridge | 17.487      | -4.065           | -0.839     | -0.757           | -6.574      | 30.000       |
| Llara      | 2.000              | model6_rf      | affine         | 14.966      | -2.582           | -0.382     | -0.433           | -5.845      | 30.000       |
| Llara      | 2.000              | model6_rf      | bias_offset    | 13.049      | -0.356           | 0.009      | -0.053           | -3.685      | 30.000       |
| Llara      | 2.000              | model6_rf      | residual_ridge | 14.979      | -2.778           | -0.405     | -0.473           | -2.501      | 30.000       |
| Llara      | 2.000              | model8_process | affine         | 14.703      | -1.325           | -0.297     | -0.223           | -6.448      | 30.000       |
| Llara      | 2.000              | model8_process | bias_offset    | 12.493      | 0.837            | 0.086      | 0.131            | -2.064      | 30.000       |
| Llara      | 2.000              | model8_process | residual_ridge | 15.724      | -2.559           | -0.569     | -0.463           | -2.403      | 30.000       |
| Llara      | 3.000              | model6_rf      | affine         | 14.440      | -2.241           | -0.307     | -0.375           | -5.143      | 30.000       |
| Llara      | 3.000              | model6_rf      | bias_offset    | 13.692      | -1.216           | -0.114     | -0.192           | -1.804      | 30.000       |
| Llara      | 3.000              | model6_rf      | residual_ridge | 16.137      | -3.935           | -0.633     | -0.703           | -4.429      | 30.000       |
| Llara      | 3.000              | model8_process | affine         | 13.474      | -0.330           | -0.123     | -0.053           | -2.376      | 30.000       |
| Llara      | 3.000              | model8_process | bias_offset    | 12.994      | 0.377            | -0.011     | 0.058            | -1.300      | 30.000       |
| Llara      | 3.000              | model8_process | residual_ridge | 15.309      | -1.931           | -0.451     | -0.343           | -1.219      | 30.000       |
| Llara      | 5.000              | model6_rf      | affine         | 13.637      | -1.306           | -0.130     | -0.213           | -2.865      | 30.000       |
| Llara      | 5.000              | model6_rf      | bias_offset    | 12.474      | -0.051           | 0.053      | -0.007           | -2.474      | 30.000       |
| Llara      | 5.000              | model6_rf      | residual_ridge | 16.238      | -3.671           | -0.586     | -0.637           | -0.470      | 30.000       |
| Llara      | 5.000              | model8_process | affine         | 12.557      | 0.770            | 0.017      | 0.121            | -2.631      | 30.000       |
| Llara      | 5.000              | model8_process | bias_offset    | 11.791      | 1.468            | 0.170      | 0.219            | -2.733      | 30.000       |
| Llara      | 5.000              | model8_process | residual_ridge | 16.981      | -3.837           | -0.787     | -0.696           | -1.197      | 30.000       |
| Tarrawarra | 1.000              | model6_rf      | affine         | 12.026      | 4.085            | -0.884     | 1.497            | -8.810      | 30.000       |
| Tarrawarra | 1.000              | model6_rf      | bias_offset    | 12.026      | 4.085            | -0.884     | 1.497            | -8.810      | 30.000       |
| Tarrawarra | 1.000              | model6_rf      | residual_ridge | 12.026      | 4.085            | -0.884     | 1.497            | -8.810      | 30.000       |
| Tarrawarra | 1.000              | model8_process | affine         | 8.665       | 1.785            | 0.022      | 0.445            | -5.872      | 30.000       |
| Tarrawarra | 1.000              | model8_process | bias_offset    | 8.665       | 1.785            | 0.022      | 0.445            | -5.872      | 30.000       |
| Tarrawarra | 1.000              | model8_process | residual_ridge | 8.665       | 1.785            | 0.022      | 0.445            | -5.872      | 30.000       |
| Tarrawarra | 2.000              | model6_rf      | affine         | 11.547      | 4.561            | -0.738     | 1.644            | -8.252      | 30.000       |
| Tarrawarra | 2.000              | model6_rf      | bias_offset    | 11.737      | 4.376            | -0.795     | 1.587            | -8.411      | 30.000       |
| Tarrawarra | 2.000              | model6_rf      | residual_ridge | 11.737      | 4.376            | -0.795     | 1.587            | -8.411      | 30.000       |
| Tarrawarra | 2.000              | model8_process | affine         | 5.212       | 5.239            | 0.646      | 1.070            | -0.533      | 30.000       |
| Tarrawarra | 2.000              | model8_process | bias_offset    | 7.980       | 2.472            | 0.170      | 0.593            | -4.803      | 30.000       |
| Tarrawarra | 2.000              | model8_process | residual_ridge | 7.980       | 2.472            | 0.170      | 0.593            | -4.803      | 30.000       |

_Showing first 60 of 72 rows._

## Process-vs-statistical calibration responsiveness

Positive `process_minus_statistical_rmse_gain_median` means model8 process
benefited more from the same sparse local calibration than model6 RF. Negative
values mean model6 RF benefited more.

| site       | calibration_points | method         | statistical_rmse_gain_median | process_rmse_gain_median | process_minus_statistical_rmse_gain_median | fraction_process_wins | n_replicates |
| ---------- | ------------------ | -------------- | ---------------------------- | ------------------------ | ------------------------------------------ | --------------------- | ------------ |
| Esdale     | 1.000              | affine         | -0.323                       | 0.249                    | 0.634                                      | 0.700                 | 30.000       |
| Esdale     | 1.000              | bias_offset    | -0.323                       | 0.249                    | 0.634                                      | 0.700                 | 30.000       |
| Esdale     | 1.000              | residual_ridge | -0.323                       | 0.249                    | 0.634                                      | 0.700                 | 30.000       |
| Esdale     | 2.000              | affine         | -2.331                       | -2.995                   | 0.039                                      | 0.367                 | 30.000       |
| Esdale     | 2.000              | bias_offset    | -0.844                       | 0.461                    | 1.507                                      | 0.900                 | 30.000       |
| Esdale     | 2.000              | residual_ridge | -0.132                       | 0.472                    | 0.766                                      | 0.633                 | 30.000       |
| Esdale     | 3.000              | affine         | -1.669                       | -2.357                   | 0.016                                      | 0.233                 | 30.000       |
| Esdale     | 3.000              | bias_offset    | -0.296                       | 0.645                    | 1.106                                      | 0.733                 | 30.000       |
| Esdale     | 3.000              | residual_ridge | 0.343                        | 0.196                    | -0.200                                     | 0.400                 | 30.000       |
| Esdale     | 5.000              | affine         | -2.046                       | -0.832                   | 0.689                                      | 0.600                 | 30.000       |
| Esdale     | 5.000              | bias_offset    | -0.516                       | 0.731                    | 1.315                                      | 0.767                 | 30.000       |
| Esdale     | 5.000              | residual_ridge | 0.414                        | -0.468                   | -1.190                                     | 0.300                 | 30.000       |
| Llara      | 1.000              | affine         | -5.438                       | -6.343                   | 3.058                                      | 0.733                 | 30.000       |
| Llara      | 1.000              | bias_offset    | -5.914                       | -1.804                   | 3.172                                      | 0.733                 | 30.000       |
| Llara      | 1.000              | residual_ridge | -6.279                       | -4.065                   | 2.012                                      | 0.800                 | 30.000       |
| Llara      | 2.000              | affine         | -2.582                       | -1.325                   | 2.266                                      | 0.700                 | 30.000       |
| Llara      | 2.000              | bias_offset    | -0.356                       | 0.837                    | 1.491                                      | 0.867                 | 30.000       |
| Llara      | 2.000              | residual_ridge | -2.778                       | -2.559                   | 1.117                                      | 0.533                 | 30.000       |
| Llara      | 3.000              | affine         | -2.241                       | -0.330                   | 2.006                                      | 0.767                 | 30.000       |
| Llara      | 3.000              | bias_offset    | -1.216                       | 0.377                    | 1.680                                      | 0.900                 | 30.000       |
| Llara      | 3.000              | residual_ridge | -3.935                       | -1.931                   | 1.554                                      | 0.733                 | 30.000       |
| Llara      | 5.000              | affine         | -1.306                       | 0.770                    | 1.659                                      | 0.767                 | 30.000       |
| Llara      | 5.000              | bias_offset    | -0.051                       | 1.468                    | 1.721                                      | 1.000                 | 30.000       |
| Llara      | 5.000              | residual_ridge | -3.671                       | -3.837                   | 0.683                                      | 0.433                 | 30.000       |
| Tarrawarra | 1.000              | affine         | 4.085                        | 1.785                    | -2.220                                     | 1.000                 | 30.000       |
| Tarrawarra | 1.000              | bias_offset    | 4.085                        | 1.785                    | -2.220                                     | 1.000                 | 30.000       |
| Tarrawarra | 1.000              | residual_ridge | 4.085                        | 1.785                    | -2.220                                     | 1.000                 | 30.000       |
| Tarrawarra | 2.000              | affine         | 4.561                        | 5.239                    | 0.540                                      | 1.000                 | 30.000       |
| Tarrawarra | 2.000              | bias_offset    | 4.376                        | 2.472                    | -2.234                                     | 1.000                 | 30.000       |
| Tarrawarra | 2.000              | residual_ridge | 4.376                        | 2.472                    | -2.234                                     | 1.000                 | 30.000       |
| Tarrawarra | 3.000              | affine         | 4.855                        | 5.388                    | 0.539                                      | 1.000                 | 30.000       |
| Tarrawarra | 3.000              | bias_offset    | 4.599                        | 2.517                    | -2.383                                     | 1.000                 | 30.000       |
| Tarrawarra | 3.000              | residual_ridge | 4.089                        | 2.601                    | -1.581                                     | 1.000                 | 30.000       |
| Tarrawarra | 5.000              | affine         | 4.855                        | 5.388                    | 0.357                                      | 1.000                 | 30.000       |
| Tarrawarra | 5.000              | bias_offset    | 4.488                        | 2.285                    | -2.403                                     | 1.000                 | 30.000       |
| Tarrawarra | 5.000              | residual_ridge | 3.693                        | 2.252                    | -1.688                                     | 1.000                 | 30.000       |

## Figures

### Figure 1. Uncalibrated global model skill by dense site

![Uncalibrated global model skill by dense site](three_site_sparse_local_calibration/figures/baseline_site_model_skill.png)

Baseline RMSE and NSE/R² for model6 RF and model8 process before any local calibration.

### Figure 2. Strict spatio-temporal random sparse-sensor learning curves

![Strict spatio-temporal random sparse-sensor learning curves](three_site_sparse_local_calibration/figures/random_spatiotemporal_learning_curves_rmse_gain.png)

Median RMSE gain from random sparse local sensors when calibration and validation are separated in space and time.

### Figure 3. One-sensor selection strategy comparison

![One-sensor selection strategy comparison](three_site_sparse_local_calibration/figures/one_sensor_strategy_comparison_rmse_gain.png)

Best one-sensor RMSE gain by site, model and sensor-placement strategy under the strict block.

### Figure 4. Process-vs-statistical calibration responsiveness

![Process-vs-statistical calibration responsiveness](three_site_sparse_local_calibration/figures/process_vs_statistical_responsiveness_random.png)

Positive values indicate model8 process gains more from the same random sparse calibration budget than model6 RF.

## Interpretation guardrails

- Local calibration is not independent validation. It is a separate
  intervention/sensor-placement experiment layered after unseen-site
  validation.
- The `spatiotemporal_block` results are the most defensible for property-scale
  transfer because calibration and validation are separated in both space and
  time.
- The field-knowledge proxy is useful for thinking with landowners, but it is
  not a strict blind selection rule because the proxy is generated from observed
  chronic wet/dry behaviour.
- A calibration layer that improves RMSE by destroying seasonal behaviour should
  not be treated as a win. Seasonal metrics are written to
  `metrics_by_design_season.csv` for that reason.
- The process-vs-statistical question should be read as **responsiveness to a
  tiny local information budget**, not as a universal ranking of model types.
