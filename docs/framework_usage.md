# DMM validation

Independent validation tools for downscaled soil-moisture predictions.

This repository is deliberately model-agnostic. A random forest, a process model,
or any other model can be evaluated as long as it writes predictions to the same
long-format table:

```text
model_name, point_id, date, lon, lat, obs_sm_pct, pred_sm_pct
```

Optional columns such as `depth_cm`, `twi`, `hli`, `slope`, `elevation`,
`soil_clay`, `soil_sand`, `rain_30`, or `terrain_zone` are used only for
diagnostics and stratification. They are not required and they are not assumed to
be model inputs.

## Why this exists

The validation layer should be independent of the downscaling model. That keeps
the comparison between an RF model and a process model clean: both models predict
the same dense point observations, then this repo scores them with the same
metrics, seasons, terrain strata, paired tests, maps, and time-series plots.

Local calibration and spiking experiments belong in a separate protocol. They
are useful, but they should not be mixed into the primary independent validation
score.

## Quick start

Install in editable mode from this repository:

```bash
python -m pip install -e .
```

Run the dense-point validation:

```bash
dmm-validate-dense \
  --predictions path/to/model_agnostic_predictions.csv \
  --outdir outputs/dense_point_validation
```

Or run directly without installing:

```bash
python -m dmm_validation.cli \
  --predictions path/to/model_agnostic_predictions.csv \
  --outdir outputs/dense_point_validation
```

## Core outputs

The validator writes:

- `standardized_predictions.csv`
- `metrics_overall.csv`
- `metrics_by_season.csv`
- `metrics_by_season_year.csv`
- `metrics_by_point.csv`
- `metrics_by_point_season.csv`
- `seasonal_bias_summary.csv`
- `bias_by_moisture_quantile.csv`
- `metrics_by_terrain_strata.csv`, when terrain columns are present
- `paired_model_comparison_overall.csv`, when two or more models are present
- `paired_model_comparison_by_season.csv`, when two or more models are present
- `paired_model_comparison_by_terrain.csv`, when terrain strata are present
- `point_metrics.geojson`
- `report.md`
- diagnostic figures in `figures/`

## Recommended interpretation

Use the independent validation in this order:

1. overall skill: NSE/R², RMSE, ubRMSE, bias, MAE, Pearson correlation;
2. seasonal skill and seasonal bias amplitude;
3. dry/wet regime bias using observed soil-moisture quantiles;
4. paired RF-vs-process residual comparisons on the same point-date rows;
5. spatial and terrain stratification of point-level errors;
6. visual checks with maps and time-series residuals.

See:

- `docs/independent_dense_point_validation_protocol.md`
- `docs/local_calibration_layers.md`

