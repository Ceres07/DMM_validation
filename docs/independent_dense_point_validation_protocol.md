# Independent dense-point validation protocol

## Objective

Compare downscaled soil-moisture models on an independent dense point dataset
without depending on model internals.

The same protocol should be able to compare:

- a random forest model;
- a process or water-balance model;
- a hybrid model;
- any later local-calibrated variant, as long as that variant is clearly labelled
  as a separate model.

## Contract between model and validator

Each model must produce a long-format prediction table with at least:

| column | meaning |
| --- | --- |
| `model_name` | model or model variant name |
| `point_id` | dense sample point identifier |
| `date` | observation date |
| `lon` | longitude |
| `lat` | latitude |
| `obs_sm_pct` | observed soil moisture, percent VWC or agreed target scale |
| `pred_sm_pct` | model prediction on the same scale |

Recommended optional columns:

- `depth_cm`
- `measurement_id`
- `season`
- `twi`
- `hli`
- `slope`
- `northness`
- `eastness`
- `elevation`
- `soil_clay`
- `soil_sand`
- `soil_awc`
- `rain_7`
- `rain_30`
- `ppet_30`
- `vpd_30`
- `terrain_zone`

These optional variables are diagnostics. They should not be interpreted as
requirements that all models use the same predictors.

## Primary scores

Report the following for each model:

- NSE / `r2`, defined as `1 - SS_res / SS_tot`;
- RMSE;
- ubRMSE;
- bias, prediction minus observation;
- MAE;
- Pearson `r` and Pearson `r²`;
- observed-vs-predicted slope and intercept.

## Seasonal-bias sensitivity

The protocol reports metrics by southern-hemisphere season:

- spring: September-November;
- summer: December-February;
- autumn: March-May;
- winter: June-August.

It also reports:

- seasonal mean bias;
- seasonal RMSE;
- seasonal bias amplitude:
  `max(seasonal bias) - min(seasonal bias)`;
- dry/wet bias by observed soil-moisture quartile.

The seasonal bias amplitude is useful because a model can have a low pooled bias
while flipping from wet-season underprediction to dry-season overprediction.

## Paired model comparison

When two or more models are present, models are compared on exactly matched
point-date observations.

For each pair:

`delta_abs_error = abs_error_model_a - abs_error_model_b`

Negative values mean `model_a` was closer to the observation. The protocol
reports:

- mean paired absolute-error difference;
- median paired absolute-error difference;
- paired squared-error difference;
- RMSE for each model on matched rows;
- bias difference;
- fraction of matched observations where model A was better;
- cluster bootstrap confidence intervals, resampling by point.

This paired design is preferable to comparing separate metric tables because it
asks which model was better at the same places and times.

## Terrain and spatial stratification

The validator creates low/mid/high quantile strata for numeric diagnostic
variables such as TWI, HLI, slope and elevation. It then reports model skill and
bias inside each stratum.

Recommended interpretation questions:

- Does either model fail on high-TWI lower-slope points?
- Does either model over-dry exposed/high-HLI slopes?
- Does the process model perform better during wetting or drydown?
- Does the RF model perform better inside terrain states represented in its
  training set but worse outside them?
- Are paired RF-process error differences spatially clustered?

## Visual diagnostics

The protocol writes:

- observed-vs-predicted scatter by season;
- mean observed and predicted time series;
- mean residual time series;
- seasonal residual boxplots;
- point-level maps of RMSE, bias and NSE/R²;
- paired model error-difference maps;
- residual boxplots by terrain stratum.

These figures are intended as a visual falsification layer. If the metrics look
good but the residual maps show strong spatial structure, the model is still not
field-robust.

## What this protocol deliberately avoids

The independent validation score should not include:

- local calibration fitted using validation observations;
- spiking/fine-tuning using the same dense point observations being scored;
- hand-tuned post-processing after looking at validation residuals;
- model-specific covariates that cannot be generated for competing models.

Local calibration can and should be studied, but as a separate experiment with
explicit calibration and held-out validation windows.

