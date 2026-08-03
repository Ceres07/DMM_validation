# Stage 3 — Time series validation

Objective: quantify how well dense point calibration transfers to unseen time
windows in the Phenode wireless in-situ time series, and compare that with the
reverse transfer from time-series sensors back to dense point observations.

## Inputs

- Dense calibration source:
  `/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/Validation_2stage/stage1_dense_unseen_validation/point_date_model_inputs.csv`
- Phenode wireless data:
  `/Volumes/Dmitry_work/borevitz_projects/Data/Phenode_wireless_data`
- Stage 3 output folder:
  `/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel/reports/stage3_time_series_validation`

Phenode usable observations:

| point | device_name | n | date_min | date_max | obs_mean | obs_min | obs_max |
| --- | --- | --- | --- | --- | --- | --- | --- |
| WS-201f28e185df | EOG | 324 | 2025-06-10 | 2026-07-01 | 23.059 | 20.500 | 25.600 |
| WS-4aa144a4eafe | EER? | 356 | 2025-06-10 | 2026-07-01 | 23.373 | 21.300 | 26.300 |
| WS-555215c413db | EOR? | 107 | 2025-06-10 | 2025-09-24 | 25.285 | 23.800 | 26.300 |
| WS-57c7afe16ae1 | AER | 356 | 2025-06-10 | 2026-07-01 | 23.321 | 20.900 | 25.900 |
| WS-a2f10ef43bc1 | AOG | 356 | 2025-06-10 | 2026-07-01 | 23.103 | 20.300 | 25.700 |
| WS-a84d3fd5d4ca | AOR | 356 | 2025-06-10 | 2026-07-01 | 23.187 | 20.800 | 25.600 |
| WS-f575dcdea0dc | AEG? | 352 | 2025-06-10 | 2026-07-01 | 23.924 | 20.800 | 27.400 |

## Calibration method

The primary local calibration is a ridge residual model trained on:

`model6 residual = observed soil moisture - uncalibrated model6 prediction`

using model6's own input features plus the uncalibrated model6 prediction. A
bias-only correction is also written to CSV as a conservative reference, but the
main tables below focus on:

- `model6`: uncalibrated shipped model6;
- `dense_ridge`: residual calibration trained on dense points and applied to
  Phenode time-series sensors;
- `phenode_ridge`: residual calibration trained on Phenode sensors and applied
  back to dense points.

The repo's shared evaluation helper reports `r2` as the same coefficient as NSE;
Pearson correlation is reported separately as `r`.

Training rows:

- Dense residual calibration rows: 560
- Phenode residual calibration rows: 2207
- Dense dates: 2025-04-30 to 2025-07-17
- Phenode dates: 2025-06-10 to 2026-07-01

## Dense point calibration → Phenode time-series sensors

Overall:

| prediction | n | nse | r2 | r | rmse | ubrmse | bias |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model6 | 2207 | -17.681 | -17.681 | 0.742 | 7.015 | 1.907 | -6.751 |
| dense_bias | 2207 | -14.940 | -14.940 | 0.742 | 6.480 | 1.907 | -6.193 |
| dense_ridge | 2207 | -65.997 | -65.997 | -0.225 | 13.285 | 12.422 | 4.708 |

By season:

| season | prediction | n | nse | r2 | r | rmse | ubrmse | bias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| spring | model6 | 538 | -19.062 | -19.062 | 0.773 | 6.531 | 1.933 | -6.239 |
| spring | dense_bias | 538 | -15.935 | -15.935 | 0.773 | 6.001 | 1.933 | -5.681 |
| spring | dense_ridge | 538 | -211.600 | -211.600 | -0.325 | 21.261 | 5.684 | 20.487 |
| summer | model6 | 539 | -79.327 | -79.327 | 0.362 | 8.093 | 0.960 | -8.036 |
| summer | dense_bias | 539 | -68.713 | -68.713 | 0.362 | 7.539 | 0.960 | -7.478 |
| summer | dense_ridge | 539 | -138.199 | -138.199 | 0.366 | 10.653 | 7.449 | 7.616 |
| autumn | model6 | 366 | -32.795 | -32.795 | 0.533 | 7.433 | 1.153 | -7.343 |
| autumn | dense_bias | 366 | -27.974 | -27.974 | 0.533 | 6.882 | 1.153 | -6.785 |
| autumn | dense_ridge | 366 | -32.700 | -32.700 | 0.283 | 7.423 | 5.849 | -4.570 |
| winter | model6 | 764 | -80.384 | -80.384 | -0.105 | 6.280 | 2.093 | -5.921 |
| winter | dense_bias | 764 | -67.395 | -67.395 | -0.105 | 5.757 | 2.093 | -5.363 |
| winter | dense_ridge | 764 | -174.468 | -174.468 | -0.093 | 9.221 | 8.304 | -4.010 |

By season-year:

| season | season_year | prediction | n | nse | r2 | r | rmse | ubrmse | bias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| spring | 2025 | model6 | 538 | -19.062 | -19.062 | 0.773 | 6.531 | 1.933 | -6.239 |
| spring | 2025 | dense_bias | 538 | -15.935 | -15.935 | 0.773 | 6.001 | 1.933 | -5.681 |
| spring | 2025 | dense_ridge | 538 | -211.600 | -211.600 | -0.325 | 21.261 | 5.684 | 20.487 |
| summer | 2026 | model6 | 539 | -79.327 | -79.327 | 0.362 | 8.093 | 0.960 | -8.036 |
| summer | 2026 | dense_bias | 539 | -68.713 | -68.713 | 0.362 | 7.539 | 0.960 | -7.478 |
| summer | 2026 | dense_ridge | 539 | -138.199 | -138.199 | 0.366 | 10.653 | 7.449 | 7.616 |
| autumn | 2026 | model6 | 366 | -32.795 | -32.795 | 0.533 | 7.433 | 1.153 | -7.343 |
| autumn | 2026 | dense_bias | 366 | -27.974 | -27.974 | 0.533 | 6.882 | 1.153 | -6.785 |
| autumn | 2026 | dense_ridge | 366 | -32.700 | -32.700 | 0.283 | 7.423 | 5.849 | -4.570 |
| winter | 2025 | model6 | 581 | -64.752 | -64.752 | -0.084 | 5.904 | 2.173 | -5.490 |
| winter | 2025 | dense_bias | 581 | -53.786 | -53.786 | -0.084 | 5.389 | 2.173 | -4.932 |
| winter | 2025 | dense_ridge | 581 | -147.729 | -147.729 | -0.047 | 8.880 | 8.594 | -2.232 |
| winter | 2026 | model6 | 183 | -193.099 | -193.099 | 0.283 | 7.348 | 0.913 | -7.291 |
| winter | 2026 | dense_bias | 183 | -164.974 | -164.974 | 0.283 | 6.795 | 0.913 | -6.733 |
| winter | 2026 | dense_ridge | 183 | -375.339 | -375.339 | 0.147 | 10.232 | 3.382 | -9.656 |

## Phenode time-series calibration → dense points

Overall:

| prediction | n | nse | r2 | r | rmse | ubrmse | bias |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model6 | 560 | 0.023 | 0.023 | 0.238 | 6.477 | 6.453 | -0.558 |
| phenode_bias | 560 | -0.863 | -0.863 | 0.238 | 8.944 | 6.453 | 6.193 |
| phenode_ridge | 560 | -0.763 | -0.763 | 0.367 | 8.701 | 6.116 | 6.188 |

By season:

| season | prediction | n | nse | r2 | r | rmse | ubrmse | bias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| autumn | model6 | 308 | -0.030 | -0.030 | 0.100 | 7.279 | 7.273 | 0.296 |
| autumn | phenode_bias | 308 | -0.993 | -0.993 | 0.100 | 10.127 | 7.273 | 7.046 |
| autumn | phenode_ridge | 308 | -1.094 | -1.094 | 0.426 | 10.379 | 6.579 | 8.028 |
| winter | model6 | 252 | -0.292 | -0.292 | 0.111 | 5.336 | 5.090 | -1.601 |
| winter | phenode_bias | 252 | -1.379 | -1.379 | 0.111 | 7.241 | 5.090 | 5.150 |
| winter | phenode_ridge | 252 | -0.659 | -0.659 | 0.254 | 6.046 | 4.586 | 3.940 |

Dense points only cover autumn/winter campaign dates, so spring and summer are
not available for this reverse-transfer test.

## Figures

- `stage3_time_series_validation/figures/phenode_timeseries_observed_vs_predicted.png`
- `stage3_time_series_validation/figures/phenode_residuals_through_time.png`
- `stage3_time_series_validation/figures/dense_mean_residuals_with_phenode_calibration.png`

## Short interpretation

The Stage 3 comparison is intentionally a transfer test, not an in-sample
calibration score. Dense point calibration is trained on a short autumn/winter
field campaign and then asked to transfer into a longer Phenode time series that
includes unseen spring and summer conditions. The reverse test asks whether
continuous in-situ sensors can provide a useful local residual correction for
the dense spatial campaign.

If dense-calibrated Phenode metrics degrade in spring/summer, that indicates the
dense campaign calibration is too seasonally narrow. If Phenode-calibrated dense
metrics improve, that suggests continuous local sensors are valuable anchors for
spatial dense-point campaigns. If they degrade, the Phenode sensors and dense
handheld points are likely measuring different soil depths, micro-sites, or
calibration scales.

Important caveat: Phenode VWC%, dense handheld points and model6's OzNet-style
root-zone target are not guaranteed to represent exactly the same sensing depth
or support volume. Treat these as calibration-transfer diagnostics unless sensor
depths/calibration equations are reconciled.
