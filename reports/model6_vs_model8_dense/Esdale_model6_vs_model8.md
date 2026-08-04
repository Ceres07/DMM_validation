# Model6 vs model8 independent dense-point validation

Date run: 2026-08-03  
Model branch used for model8: `DownscalingMoistureModel/process-model`  
Dense point source: `/Volumes/Dmitry_work/borevitz_projects/Data/soilmoisture_points_coordinates.csv`

This comparison uses the independent `DMM_validation` model-agnostic protocol.
Model8 process predictions were generated over the dense-point AOI for each
campaign date, sampled at the same 560 point-date rows used in the existing
model6 unseen dense-point validation, then combined with model6 predictions in a
single long-format table.

Important caveat: `model8` prints its own warning that it is calibrated on the
Murrumbidgee catchment and predictions elsewhere are plausible but unvalidated.
Treat this as an independent transfer diagnostic, not a locally calibrated score.

## Output locations

- Combined model-agnostic table:
  `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv`
- Model8-only model-agnostic table:
  `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/model8_model_agnostic_predictions.csv`
- Full validation output folder:
  `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/independent_validation`
- Auto-generated framework report:
  `/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/independent_validation/report.md`

## Overall skill

| model | n | NSE/R² | Pearson r | RMSE | ubRMSE | bias | MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| model6 RF | 560 | 0.023 | 0.238 | 6.477 | 6.453 | -0.558 | 5.209 |
| model8 process | 560 | 0.031 | 0.462 | 6.452 | 5.884 | 2.645 | 5.199 |

Overall, the two models are close in RMSE/MAE. Model8 has a slightly better
NSE/R² and RMSE, and substantially higher Pearson correlation, suggesting it
captures more temporal/relative variation. However, model8 also has a clear wet
bias of about +2.65 percentage points.

The paired comparison is essentially a tie:

| comparison | matched rows | mean Δ absolute error | 95% CI | fraction model6 lower abs error |
| --- | ---: | ---: | --- | ---: |
| model6 RF - model8 process | 560 | 0.010 | -0.408 to 0.467 | 0.516 |

Positive Δ absolute error means model8 is better; negative means model6 is
better. The confidence interval spans zero.

## Seasonal skill

The dense campaign only spans autumn and winter.

| model | season | n | NSE/R² | Pearson r | RMSE | ubRMSE | bias |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| model6 RF | autumn | 308 | -0.030 | 0.100 | 7.279 | 7.273 | 0.296 |
| model8 process | autumn | 308 | 0.027 | 0.336 | 7.076 | 6.777 | 2.033 |
| model6 RF | winter | 252 | -0.292 | 0.111 | 5.336 | 5.090 | -1.601 |
| model8 process | winter | 252 | -0.421 | 0.355 | 5.595 | 4.448 | 3.394 |

Seasonally, model8 is better in autumn by RMSE/NSE, while model6 is better in
winter by RMSE/NSE. Model8 maintains higher Pearson correlation in both seasons
but is consistently wetter, especially in winter.

Seasonal bias amplitude is lower for model8 (1.36) than model6 (1.90), but this
is because model8 remains positively biased in both seasons. Model6 switches
from a slight autumn wet bias to a winter dry bias.

## Dry/wet regime bias

| model | observed moisture quantile | bias | RMSE |
| --- | --- | ---: | ---: |
| model6 RF | dry q1 | 7.270 | 8.019 |
| model8 process | dry q1 | 8.277 | 9.030 |
| model6 RF | wet q4 | -7.907 | 8.949 |
| model8 process | wet q4 | -3.622 | 6.188 |

Both models overpredict the driest observations and underpredict the wettest
observations. Model6 has the stronger compression problem: it is less wet-biased
overall but much more strongly underpredicts the wettest quartile. Model8 also
overpredicts dry soils, but handles wet observations better.

## Terrain-stratified paired comparison

Negative Δ absolute error means model6 has lower absolute error; positive means
model8 has lower absolute error.

Most model8-favouring strata:

| terrain stratum | mean Δ absolute error | model6 RMSE | model8 RMSE | interpretation |
| --- | ---: | ---: | ---: | --- |
| high soil sand | 1.571 | 7.243 | 5.609 | model8 much better |
| high HLI | 1.349 | 7.043 | 5.808 | model8 better on high heat-load terrain |
| low soil clay | 1.112 | 7.025 | 5.883 | model8 better on lower clay / sandier soils |
| high northness | 1.067 | 7.004 | 5.792 | model8 better on high-northness strata |
| high rain_7 | 0.845 | 5.280 | 4.337 | model8 better in recent-rain high strata |

Most model6-favouring strata:

| terrain stratum | mean Δ absolute error | model6 RMSE | model8 RMSE | interpretation |
| --- | ---: | ---: | ---: | --- |
| low soil sand | -1.281 | 6.251 | 7.350 | model6 better |
| high soil clay | -1.124 | 6.251 | 7.235 | model6 better on clayier strata |
| low rain_7 | -0.962 | 6.603 | 7.340 | model6 better in low recent-rain strata |
| mid HLI | -0.828 | 5.864 | 6.703 | model6 better |
| high soil bulk density | -0.762 | 6.362 | 7.124 | model6 better |

The strongest terrain signal is soil-texture-like: model8 improves over model6
in sandier / lower-clay strata and degrades in lower-sand / higher-clay strata.
That is consistent with model8 using SLGA soil terms inside a process-model
readout. The process model may be capturing a more physically coherent wetness
trajectory, but its local soil-level/readout offset is not yet calibrated for
this site.

## Visual diagnostics generated

The framework generated scatter plots, residual time series, seasonal bias
boxplots, point-level metric maps and the paired error-difference map here:

`/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense/independent_validation/figures`

Most important figure for model comparison:

`paired_error_difference_map_model6_rf_minus_model8_process.png`

Negative values mean model6 is better at that point; positive values mean model8
is better.

## Interpretation

This first model6-vs-model8 dense validation does not show a decisive overall
winner. Model8 has better correlation, slightly better overall RMSE/NSE, and
better wet-quartile behaviour. Model6 has less overall bias and slightly better
winter RMSE.

Scientifically, the most interesting result is the model disagreement structure:
model8 appears stronger in high-HLI, high-sand / low-clay, and wetter recent-rain
strata, while model6 is stronger in clayier, lower-sand and some lower-rain
strata. This is exactly the kind of seasonal/terrain-dependent contrast the
independent validation protocol was designed to reveal.

