# Stage 2 local-spiking calibration: Esdale, Tarrawarra and Llara

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
- `seasonal_offset`: separate residual offsets by southern-hemisphere season,
  falling back to the global offset where a season is unseen in calibration;
- `affine`: local intercept and slope correction;
- `residual_ridge`: strongly regularised residual layer using only
  prediction-time model inputs and terrain/soil/weather state.

## Site inputs

| site       | path                                                                                                                                                | rows      | models                   | points  | eligible_points_train_and_future | dates   | date_min   | date_max   | train_dates | future_dates | seasons                     |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ------------------------ | ------- | -------------------------------- | ------- | ---------- | ---------- | ----------- | ------------ | --------------------------- |
| Esdale     | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv                         | 1120.000  | model6_rf,model8_process | 79.000  | 76.000                           | 9.000   | 2025-04-30 | 2025-07-17 | 3.000       | 6.000        | autumn,winter               |
| Tarrawarra | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv | 4308.000  | model6_rf,model8_process | 178.000 | 168.000                          | 19.000  | 1995-09-25 | 1996-11-29 | 7.000       | 12.000       | autumn,spring,summer,winter |
| Llara      | /Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv                     | 58494.000 | model6_rf,model8_process | 32.000  | 32.000                           | 955.000 | 2021-10-19 | 2024-06-30 | 316.000     | 639.000      | autumn,spring,summer,winter |

Tarrawarra observations are aggregated to the model prediction grid cell by date before validation, because the raw campaign points are much closer than the raster support. Tarrawarra model6 should also be read with a special caveat: the historical SMIPS inputs in the existing Tarrawarra run are zero, so model6 there is closer to a missing-coarse-anchor ablation than a normal model6 run.

## Uncalibrated global model skill

| site       | base_model     | model_track    | n         | nse    | pearson_r | rmse   | ubrmse | bias    |
| ---------- | -------------- | -------------- | --------- | ------ | --------- | ------ | ------ | ------- |
| Esdale     | model6_rf      | statistical_rf | 560.000   | 0.023  | 0.238     | 6.477  | 6.453  | -0.558  |
| Esdale     | model8_process | process_bucket | 560.000   | 0.031  | 0.462     | 6.452  | 5.884  | 2.645   |
| Tarrawarra | model6_rf      | statistical_rf | 2154.000  | -1.219 | 0.398     | 14.402 | 9.093  | -11.169 |
| Tarrawarra | model8_process | process_bucket | 2154.000  | 0.077  | 0.853     | 9.291  | 6.958  | -6.157  |
| Llara      | model6_rf      | statistical_rf | 29247.000 | 0.036  | 0.267     | 13.927 | 13.744 | -2.249  |
| Llara      | model8_process | process_bucket | 29247.000 | -0.017 | 0.453     | 14.306 | 12.855 | -6.278  |

## Headline inference

- Under the strict prior-guided, non-proxy placement test, **model8 process is
  usually more responsive than model6 RF at Esdale and Llara**, especially when
  the selected supports represent landscape wet/dry structure or model
  prediction extremes. This is the cleanest evidence so far that the process
  model may provide a more stable base for small local information budgets.
- Tarrawarra is different: both models improve strongly with sparse local
  calibration, but model6 often shows larger RMSE gains because its uncalibrated
  bias is very large. However, model8 generally remains the lower-RMSE model
  after calibration. Interpret this alongside the Tarrawarra SMIPS-zero caveat.
- Random placement is retained as an appendix comparator. It is not consistently
  enough under the strict block, which supports the practical idea of using
  defensible landscape knowledge rather than arbitrary sensor placement.
- The `field_knowledge_wetdry_proxy` can outperform deployable priors in some
  cases, but it is an upper-bound proxy, not a blind deployment rule.
- The residual-ridge layer is useful in selected cases, but simple
  `bias_offset` is often the most robust sparse-sensor calibration layer. This
  matters for deployability: a landowner-facing calibration should probably
  start with a small, interpretable correction before adding flexible residual
  models.

## Best one-sensor strict spatio-temporal result

For each site and model, this table selects the best one-sensor calibration
method/selection strategy by median RMSE under the strict block.

| site       | base_model     | selection_strategy         | budget_label | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ---------- | -------------- | -------------------------- | ------------ | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| Esdale     | model6_rf      | landscape_wetdry_prior     | 1            | residual_ridge  | -0.249     | 0.046            | 4.926       | 4.924         | 0.127       | 1.000        |
| Esdale     | model8_process | global_prediction_extremes | 1            | bias_offset     | -0.049     | 0.262            | 4.515       | 4.434         | -0.851      | 1.000        |
| Llara      | model6_rf      | global_prediction_extremes | 1            | affine          | 0.000      | 0.318            | 12.745      | 12.745        | -0.041      | 1.000        |
| Llara      | model8_process | global_prediction_extremes | 1            | affine          | 0.087      | 0.470            | 12.179      | 12.039        | -1.838      | 1.000        |
| Tarrawarra | model6_rf      | landscape_wetdry_prior     | 1            | seasonal_offset | -0.146     | 0.144            | 9.917       | 9.726         | -1.939      | 1.000        |
| Tarrawarra | model8_process | landscape_wetdry_prior     | 1            | affine          | 0.460      | 0.859            | 6.807       | 6.488         | -2.061      | 1.000        |

## Prior-guided sparse-sensor learning curves

This table mirrors the main manuscript learning-curve figures and
Table 5-style minimum-budget summary. It keeps only deployable non-random,
non-proxy placement strategies: `landscape_wetdry_prior` and
`global_prediction_extremes`.

| site       | budget_label | calibration_points | base_model     | selection_strategy         | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | rmse_gain_median | delta_nse_median | n_replicates |
| ---------- | ------------ | ------------------ | -------------- | -------------------------- | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ---------------- | ---------------- | ------------ |
| Esdale     | 1            | 1.000              | model6_rf      | landscape_wetdry_prior     | affine          | -0.249     | 0.046            | 4.926       | 4.924         | 0.127       | 0.279            | 0.145            | 1.000        |
| Esdale     | 3            | 3.000              | model6_rf      | global_prediction_extremes | residual_ridge  | 0.040      | 0.441            | 4.138       | 3.804         | 1.627       | 0.678            | 0.341            | 1.000        |
| Esdale     | 5            | 5.000              | model6_rf      | global_prediction_extremes | bias_offset     | -0.152     | 0.085            | 4.547       | 4.546         | -0.106      | 0.241            | 0.125            | 1.000        |
| Esdale     | 10           | 10.000             | model6_rf      | landscape_wetdry_prior     | bias_offset     | -0.354     | 0.090            | 5.113       | 4.828         | -1.683      | -0.048           | -0.025           | 1.000        |
| Esdale     | 25%          | 19.000             | model6_rf      | global_prediction_extremes | residual_ridge  | 0.003      | 0.314            | 4.029       | 3.989         | 0.564       | 0.123            | 0.062            | 1.000        |
| Esdale     | 50%          | 38.000             | model6_rf      | global_prediction_extremes | residual_ridge  | 0.160      | 0.531            | 3.480       | 3.240         | -1.269      | 0.201            | 0.100            | 1.000        |
| Esdale     | 1            | 1.000              | model8_process | global_prediction_extremes | affine          | -0.049     | 0.262            | 4.515       | 4.434         | -0.851      | 0.808            | 0.409            | 1.000        |
| Esdale     | 3            | 3.000              | model8_process | global_prediction_extremes | affine          | -0.069     | 0.274            | 4.365       | 4.081         | 1.549       | 0.938            | 0.509            | 1.000        |
| Esdale     | 5            | 5.000              | model8_process | landscape_wetdry_prior     | affine          | 0.034      | 0.254            | 4.420       | 4.396         | -0.457      | 1.006            | 0.490            | 1.000        |
| Esdale     | 10           | 10.000             | model8_process | landscape_wetdry_prior     | residual_ridge  | 0.045      | 0.462            | 4.294       | 4.075         | 1.354       | 1.036            | 0.516            | 1.000        |
| Esdale     | 25%          | 19.000             | model8_process | landscape_wetdry_prior     | residual_ridge  | 0.237      | 0.494            | 3.746       | 3.745         | 0.088       | 1.539            | 0.756            | 1.000        |
| Esdale     | 50%          | 38.000             | model8_process | global_prediction_extremes | bias_offset     | 0.101      | 0.427            | 3.600       | 3.494         | 0.868       | 1.201            | 0.700            | 1.000        |
| Llara      | 1            | 1.000              | model6_rf      | global_prediction_extremes | affine          | 0.000      | 0.318            | 12.745      | 12.745        | -0.041      | -0.213           | -0.033           | 1.000        |
| Llara      | 3            | 3.000              | model6_rf      | landscape_wetdry_prior     | residual_ridge  | -0.182     | 0.429            | 14.079      | 12.759        | -5.952      | -1.443           | -0.230           | 1.000        |
| Llara      | 5            | 5.000              | model6_rf      | landscape_wetdry_prior     | bias_offset     | -0.361     | 0.364            | 14.812      | 11.841        | -8.899      | -2.354           | -0.398           | 1.000        |
| Llara      | 25%          | 8.000              | model6_rf      | landscape_wetdry_prior     | affine          | 0.038      | 0.368            | 12.605      | 12.125        | -3.444      | -0.186           | -0.028           | 1.000        |
| Llara      | 10           | 10.000             | model6_rf      | global_prediction_extremes | seasonal_offset | 0.064      | 0.330            | 12.485      | 12.356        | -1.784      | 0.050            | 0.008            | 1.000        |
| Llara      | 50%          | 16.000             | model6_rf      | global_prediction_extremes | seasonal_offset | 0.205      | 0.457            | 10.211      | 10.195        | -0.579      | 0.065            | 0.010            | 1.000        |
| Llara      | 1            | 1.000              | model8_process | global_prediction_extremes | affine          | 0.087      | 0.470            | 12.179      | 12.039        | -1.838      | 1.253            | 0.198            | 1.000        |
| Llara      | 3            | 3.000              | model8_process | landscape_wetdry_prior     | seasonal_offset | -0.153     | 0.449            | 13.902      | 11.571        | -7.706      | -0.151           | -0.025           | 1.000        |
| Llara      | 5            | 5.000              | model8_process | landscape_wetdry_prior     | bias_offset     | -0.240     | 0.458            | 14.139      | 11.417        | -8.341      | -0.300           | -0.052           | 1.000        |
| Llara      | 25%          | 8.000              | model8_process | global_prediction_extremes | seasonal_offset | 0.099      | 0.453            | 12.651      | 11.885        | -4.337      | 1.089            | 0.162            | 1.000        |
| Llara      | 10           | 10.000             | model8_process | global_prediction_extremes | affine          | 0.166      | 0.434            | 11.780      | 11.639        | -1.819      | 1.668            | 0.253            | 1.000        |
| Llara      | 50%          | 16.000             | model8_process | global_prediction_extremes | affine          | 0.255      | 0.511            | 9.885       | 9.872         | 0.503       | 1.605            | 0.262            | 1.000        |
| Tarrawarra | 1            | 1.000              | model6_rf      | landscape_wetdry_prior     | seasonal_offset | -0.146     | 0.144            | 9.917       | 9.726         | -1.939      | 5.836            | 1.745            | 1.000        |
| Tarrawarra | 3            | 3.000              | model6_rf      | landscape_wetdry_prior     | seasonal_offset | -0.165     | 0.154            | 10.003      | 9.610         | -2.776      | 5.737            | 1.720            | 1.000        |
| Tarrawarra | 5            | 5.000              | model6_rf      | landscape_wetdry_prior     | residual_ridge  | -0.133     | 0.799            | 9.848       | 7.106         | -6.817      | 5.847            | 1.745            | 1.000        |
| Tarrawarra | 10           | 10.000             | model6_rf      | landscape_wetdry_prior     | residual_ridge  | -0.058     | 0.819            | 9.496       | 6.952         | -6.469      | 6.124            | 1.805            | 1.000        |
| Tarrawarra | 25%          | 42.000             | model6_rf      | global_prediction_extremes | residual_ridge  | -0.055     | 0.830            | 9.628       | 6.761         | -6.854      | 6.029            | 1.734            | 1.000        |
| Tarrawarra | 50%          | 84.000             | model6_rf      | global_prediction_extremes | residual_ridge  | -0.120     | 0.826            | 10.035      | 6.696         | -7.475      | 5.780            | 1.662            | 1.000        |
| Tarrawarra | all          | 168.000            | model6_rf      | global_prediction_extremes | residual_ridge  | 0.263      | 0.820            | 9.736       | 8.929         | -3.882      | 5.800            | 1.139            | 1.000        |
| Tarrawarra | 1            | 1.000              | model8_process | landscape_wetdry_prior     | affine          | 0.460      | 0.859            | 6.807       | 6.488         | -2.061      | 3.120            | 0.608            | 1.000        |
| Tarrawarra | 3            | 3.000              | model8_process | landscape_wetdry_prior     | affine          | 0.689      | 0.859            | 5.163       | 4.822         | 1.847       | 4.747            | 0.834            | 1.000        |
| Tarrawarra | 5            | 5.000              | model8_process | landscape_wetdry_prior     | affine          | 0.690      | 0.860            | 5.155       | 4.808         | 1.859       | 4.718            | 0.828            | 1.000        |
| Tarrawarra | 10           | 10.000             | model8_process | landscape_wetdry_prior     | affine          | 0.728      | 0.860            | 4.815       | 4.768         | 0.673       | 4.991            | 0.856            | 1.000        |
| Tarrawarra | 25%          | 42.000             | model8_process | landscape_wetdry_prior     | affine          | 0.746      | 0.867            | 4.672       | 4.664         | 0.268       | 4.891            | 0.812            | 1.000        |
| Tarrawarra | 50%          | 84.000             | model8_process | landscape_wetdry_prior     | affine          | 0.738      | 0.863            | 4.764       | 4.756         | -0.280      | 4.588            | 0.748            | 1.000        |
| Tarrawarra | all          | 168.000            | model8_process | global_prediction_extremes | affine          | 0.663      | 0.822            | 6.587       | 6.505         | 1.033       | 2.758            | 0.341            | 1.000        |

## Appendix comparator: random sparse-sensor learning curves

Random placement is retained as a conservative comparator because it does not
assume any landscape knowledge. The report table shows calibrated held-out NSE,
Pearson r, RMSE, ubRMSE and bias; improvement bookkeeping is retained in the
CSV outputs.

| site   | budget_label | calibration_points | base_model     | method          | nse_median | pearson_r_median | rmse_median | ubrmse_median | bias_median | n_replicates |
| ------ | ------------ | ------------------ | -------------- | --------------- | ---------- | ---------------- | ----------- | ------------- | ----------- | ------------ |
| Esdale | 1            | 1.000              | model6_rf      | affine          | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | 1            | 1.000              | model6_rf      | bias_offset     | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | 1            | 1.000              | model6_rf      | residual_ridge  | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | 1            | 1.000              | model6_rf      | seasonal_offset | -0.835     | 0.055            | 5.946       | 4.925         | -2.319      | 20.000       |
| Esdale | 1            | 1.000              | model8_process | affine          | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | 1            | 1.000              | model8_process | bias_offset     | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | 1            | 1.000              | model8_process | residual_ridge  | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | 1            | 1.000              | model8_process | seasonal_offset | -0.303     | 0.274            | 5.048       | 4.428         | 1.693       | 20.000       |
| Esdale | 10           | 10.000             | model6_rf      | affine          | -1.648     | 0.000            | 7.115       | 4.436         | -5.602      | 20.000       |
| Esdale | 10           | 10.000             | model6_rf      | bias_offset     | -0.733     | 0.055            | 5.897       | 4.957         | -3.054      | 20.000       |
| Esdale | 10           | 10.000             | model6_rf      | residual_ridge  | -0.015     | 0.346            | 4.452       | 4.339         | -0.310      | 20.000       |
| Esdale | 10           | 10.000             | model6_rf      | seasonal_offset | -0.733     | 0.055            | 5.897       | 4.957         | -3.054      | 20.000       |
| Esdale | 10           | 10.000             | model8_process | affine          | -0.381     | 0.262            | 5.075       | 4.438         | -0.208      | 20.000       |
| Esdale | 10           | 10.000             | model8_process | bias_offset     | -0.048     | 0.264            | 4.587       | 4.446         | 0.769       | 20.000       |
| Esdale | 10           | 10.000             | model8_process | residual_ridge  | -0.554     | 0.477            | 5.391       | 4.017         | 3.581       | 20.000       |
| Esdale | 10           | 10.000             | model8_process | seasonal_offset | -0.048     | 0.264            | 4.587       | 4.446         | 0.769       | 20.000       |
| Esdale | 25%          | 19.000             | model6_rf      | affine          | -1.695     | 0.000            | 7.181       | 4.426         | -5.712      | 20.000       |
| Esdale | 25%          | 19.000             | model6_rf      | bias_offset     | -0.587     | 0.063            | 5.542       | 4.942         | -2.600      | 20.000       |
| Esdale | 25%          | 19.000             | model6_rf      | residual_ridge  | -0.145     | 0.343            | 4.740       | 4.351         | -0.200      | 20.000       |
| Esdale | 25%          | 19.000             | model6_rf      | seasonal_offset | -0.587     | 0.063            | 5.542       | 4.942         | -2.600      | 20.000       |
| Esdale | 25%          | 19.000             | model8_process | affine          | -0.167     | 0.265            | 4.664       | 4.329         | -1.278      | 20.000       |
| Esdale | 25%          | 19.000             | model8_process | bias_offset     | -0.043     | 0.265            | 4.510       | 4.435         | 0.793       | 20.000       |
| Esdale | 25%          | 19.000             | model8_process | residual_ridge  | -0.891     | 0.474            | 6.196       | 3.965         | 4.748       | 20.000       |
| Esdale | 25%          | 19.000             | model8_process | seasonal_offset | -0.043     | 0.265            | 4.510       | 4.435         | 0.793       | 20.000       |
| Esdale | 3            | 3.000              | model6_rf      | affine          | -1.802     | 0.000            | 7.350       | 4.443         | -5.381      | 20.000       |
| Esdale | 3            | 3.000              | model6_rf      | bias_offset     | -0.693     | 0.059            | 5.688       | 4.907         | -2.994      | 20.000       |
| Esdale | 3            | 3.000              | model6_rf      | residual_ridge  | -0.387     | 0.230            | 5.214       | 4.615         | -1.230      | 20.000       |
| Esdale | 3            | 3.000              | model6_rf      | seasonal_offset | -0.693     | 0.059            | 5.688       | 4.907         | -2.994      | 20.000       |
| Esdale | 3            | 3.000              | model8_process | affine          | -1.325     | 0.271            | 6.683       | 4.760         | 1.933       | 20.000       |
| Esdale | 3            | 3.000              | model8_process | bias_offset     | -0.064     | 0.273            | 4.557       | 4.402         | 0.942       | 20.000       |
| Esdale | 3            | 3.000              | model8_process | residual_ridge  | -0.392     | 0.415            | 5.191       | 4.134         | 2.931       | 20.000       |
| Esdale | 3            | 3.000              | model8_process | seasonal_offset | -0.064     | 0.273            | 4.557       | 4.402         | 0.942       | 20.000       |
| Esdale | 5            | 5.000              | model6_rf      | affine          | -2.074     | 0.000            | 7.734       | 4.425         | -6.352      | 20.000       |
| Esdale | 5            | 5.000              | model6_rf      | bias_offset     | -0.928     | 0.060            | 6.119       | 4.908         | -3.680      | 20.000       |
| Esdale | 5            | 5.000              | model6_rf      | residual_ridge  | -0.267     | 0.286            | 4.970       | 4.423         | -1.831      | 20.000       |
| Esdale | 5            | 5.000              | model6_rf      | seasonal_offset | -0.928     | 0.060            | 6.119       | 4.908         | -3.680      | 20.000       |
| Esdale | 5            | 5.000              | model8_process | affine          | -0.982     | 0.268            | 6.288       | 4.345         | -3.625      | 20.000       |
| Esdale | 5            | 5.000              | model8_process | bias_offset     | -0.091     | 0.279            | 4.597       | 4.403         | 0.131       | 20.000       |
| Esdale | 5            | 5.000              | model8_process | residual_ridge  | -0.094     | 0.430            | 4.614       | 4.078         | 1.588       | 20.000       |
| Esdale | 5            | 5.000              | model8_process | seasonal_offset | -0.091     | 0.279            | 4.597       | 4.403         | 0.131       | 20.000       |
| Esdale | 50%          | 38.000             | model6_rf      | affine          | -1.719     | 0.000            | 7.524       | 4.561         | -5.982      | 20.000       |
| Esdale | 50%          | 38.000             | model6_rf      | bias_offset     | -0.639     | 0.021            | 5.838       | 5.082         | -2.676      | 20.000       |
| Esdale | 50%          | 38.000             | model6_rf      | residual_ridge  | 0.009      | 0.447            | 4.420       | 4.118         | -1.094      | 20.000       |
| Esdale | 50%          | 38.000             | model6_rf      | seasonal_offset | -0.639     | 0.021            | 5.838       | 5.082         | -2.676      | 20.000       |
| Esdale | 50%          | 38.000             | model8_process | affine          | -0.189     | 0.272            | 5.211       | 4.388         | -2.319      | 20.000       |
| Esdale | 50%          | 38.000             | model8_process | bias_offset     | -0.037     | 0.272            | 4.540       | 4.494         | 0.702       | 20.000       |
| Esdale | 50%          | 38.000             | model8_process | residual_ridge  | -0.510     | 0.517            | 5.423       | 3.954         | 3.856       | 20.000       |
| Esdale | 50%          | 38.000             | model8_process | seasonal_offset | -0.037     | 0.272            | 4.540       | 4.494         | 0.702       | 20.000       |
| Llara  | 1            | 1.000              | model6_rf      | affine          | -0.567     | 0.350            | 16.287      | 12.322        | -5.676      | 20.000       |
| Llara  | 1            | 1.000              | model6_rf      | bias_offset     | -0.091     | 0.350            | 13.537      | 12.107        | -3.184      | 20.000       |
| Llara  | 1            | 1.000              | model6_rf      | residual_ridge  | -0.374     | 0.460            | 15.086      | 11.769        | -2.155      | 20.000       |
| Llara  | 1            | 1.000              | model6_rf      | seasonal_offset | -0.129     | 0.357            | 13.643      | 12.275        | -2.561      | 20.000       |
| Llara  | 1            | 1.000              | model8_process | affine          | -0.814     | 0.497            | 17.374      | 11.615        | -4.610      | 20.000       |
| Llara  | 1            | 1.000              | model8_process | bias_offset     | -0.242     | 0.497            | 14.347      | 11.424        | -4.036      | 20.000       |
| Llara  | 1            | 1.000              | model8_process | residual_ridge  | -0.457     | 0.497            | 15.593      | 11.635        | -5.221      | 20.000       |
| Llara  | 1            | 1.000              | model8_process | seasonal_offset | -0.208     | 0.458            | 14.140      | 11.556        | -4.314      | 20.000       |
| Llara  | 10           | 10.000             | model6_rf      | affine          | -0.021     | 0.311            | 13.168      | 12.531        | -1.252      | 20.000       |
| Llara  | 10           | 10.000             | model6_rf      | bias_offset     | 0.014      | 0.336            | 13.058      | 12.128        | -3.002      | 20.000       |
| Llara  | 10           | 10.000             | model6_rf      | residual_ridge  | -2.527     | 0.165            | 23.778      | 20.945        | 2.089       | 20.000       |
| Llara  | 10           | 10.000             | model6_rf      | seasonal_offset | 0.007      | 0.358            | 12.827      | 12.158        | -2.393      | 20.000       |

_Showing first 60 of 152 rows._

## Process-vs-statistical calibration responsiveness

Positive `process_minus_statistical_rmse_gain_median` means model8 process
benefited more from the same sparse local calibration than model6 RF. Negative
values mean model6 RF benefited more.

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

_Showing first 60 of 76 rows._

## Figures

### Figure 1. Uncalibrated global model skill by dense site

![Uncalibrated global model skill by dense site](figures/stage2_local_spiking/baseline_site_model_skill.png)

Baseline RMSE and NSE for model6 RF and model8 process before any local calibration.

### Figure 2. Strict spatio-temporal prior-guided learning curves: RMSE gain

![Strict spatio-temporal prior-guided learning curves: RMSE gain](figures/stage2_local_spiking/prior_guided_spatiotemporal_learning_curves_rmse_gain.png)

Best RMSE gain from deployable non-random placement priors under the strict spatial+temporal block.

### Figure 3. Strict spatio-temporal prior-guided learning curves: NSE

![Strict spatio-temporal prior-guided learning curves: NSE](figures/stage2_local_spiking/prior_guided_spatiotemporal_learning_curves_nse.png)

Best held-out NSE from deployable non-random placement priors under the strict spatial+temporal block.

### Figure 4. Process-vs-statistical responsiveness under prior-guided placement

![Process-vs-statistical responsiveness under prior-guided placement](figures/stage2_local_spiking/prior_guided_process_vs_statistical_responsiveness.png)

Positive values indicate model8 process gains more from the same deployable non-random placement strategy than model6 RF.

### Figure 5. Appendix: random strict spatio-temporal learning curves, RMSE gain

![Appendix: random strict spatio-temporal learning curves, RMSE gain](figures/stage2_local_spiking/random_spatiotemporal_learning_curves_rmse_gain.png)

Median RMSE gain from random sparse local sensors when calibration and validation are separated in space and time.

### Figure 6. Appendix: random strict spatio-temporal learning curves, NSE

![Appendix: random strict spatio-temporal learning curves, NSE](figures/stage2_local_spiking/random_spatiotemporal_learning_curves_nse.png)

Median held-out NSE from random sparse local sensors when calibration and validation are separated in space and time.

### Figure 7. Appendix: process-vs-statistical responsiveness under random placement

![Appendix: process-vs-statistical responsiveness under random placement](figures/stage2_local_spiking/process_vs_statistical_responsiveness_random.png)

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
