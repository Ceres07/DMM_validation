# Local calibration layers on top of a global model

Yes: a local calibration layer can be more useful than a constant residual
offset through time. The important idea is to keep the global model as the base
predictor, then learn a small, regularised local correction that changes with
state, season or terrain.

This should be explored separately from the independent validation protocol.

## Candidate designs

### 1. Local affine correction

Instead of:

`prediction_local = prediction_global + constant_bias`

use:

`prediction_local = a_local + b_local * prediction_global`

This allows the local layer to correct both offset and amplitude. For example,
if the global model captures timing but underestimates wet/dry range, `b_local`
can stretch the response.

Useful extension:

`prediction_local = a_local(season) + b_local(season) * prediction_global`

That gives each area seasonal wet/dry response parameters.

### 2. Residual model with local environmental state

Train a residual layer:

`residual = observed - prediction_global`

using only variables available at prediction time, for example:

- global prediction;
- day-of-year sin/cos;
- antecedent rainfall;
- antecedent PET;
- SMIPS or process-model state;
- TWI/HLI/slope/elevation;
- local sensor recent anomaly, if available.

The final prediction is:

`prediction_local = prediction_global + residual_layer(inputs)`

This can vary through time and terrain rather than acting as a static offset.

### 3. Partial pooling / hierarchical calibration

Use a pooled residual model across multiple properties/sites with local random
effects:

`residual = global_terms + site_terms + site_by_season_terms`

This is attractive scientifically because each small area gets its own local
adaptation, but weakly sampled areas borrow strength from the broader population.
It is less likely to overfit than fitting a completely separate model per site.

### 4. Spatial-temporal residual surface

Learn a residual surface over:

- x/y coordinates;
- terrain position;
- date or hydrological state.

This can be done with Gaussian processes, splines, GAMs, kriging of residuals,
or a compact machine-learning residual model. It is useful when errors are
spatially structured rather than random.

### 5. State updating for process models

For process models, local calibration can be framed as state or parameter
updating rather than residual correction:

- update soil-water store after local observations;
- locally adjust field capacity / wilting point / hydraulic conductivity;
- use an ensemble Kalman filter or similar assimilation method;
- validate on future windows after the update.

This is closer to hydrological data assimilation and may be more interpretable
than a black-box residual correction.

## Recommended experiment design

Keep this separate from the independent validation:

1. Fit the global model without using the local dense validation dataset.
2. Choose local calibration windows, e.g. first 10%, 25%, 50% of local
   observations or specific early-season windows.
3. Fit local adaptation layers using only those calibration observations.
4. Validate on withheld future windows and withheld points.
5. Report whether the layer improves:
   - overall RMSE/NSE;
   - seasonal bias amplitude;
   - dry/wet regime bias;
   - point-level spatial bias;
   - temporal transfer to unseen spring/summer/autumn/winter windows.

## Guardrails

- Treat constant bias correction as the baseline, not the endpoint.
- Use strong regularisation or partial pooling.
- Always compare against the unchanged global model.
- Always validate on unseen dates and/or unseen points.
- Report when a local layer improves RMSE by simply distorting the seasonal
  pattern or damaging dry/wet extremes.

