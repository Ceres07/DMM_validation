# Tarrawarra ASCII conversion

This module converts the historical Tarrawarra ASCII terrain and TDR
soil-moisture files into geospatial outputs suitable for `DMM_validation`.

The official coordinate transform is from the Tarrawarra documentation:

```text
E = 361474 + x*cos(14°) - y*sin(14°)
N = 5829892 + x*sin(14°) + y*cos(14°)
```

The source UTM-like coordinates are AGD66 / AMG zone 55 (`EPSG:20255`). For
modern lon/lat columns, the converter transforms `EPSG:20255 -> EPSG:4326`.

## Outputs

The converter writes:

- `tarrawarra_5m_dem_agd66_amg55.tif` — rotated 5 m DEM GeoTIFF in `EPSG:20255`;
- `tarrawarra_tdr_observations.csv` — transformed TDR points with full metadata;
- `tarrawarra_dmm_observation_template.csv` — leading columns aligned to the
  DMM validation schema:

  ```text
  model_name, point_id, date, lon, lat, obs_sm_pct, pred_sm_pct
  ```

- `tarrawarra_points_bbox.json` — W/S/E/N bbox derived from transformed point
  coordinates;
- `tarrawarra_conversion_metadata.json`.

`pred_sm_pct` is intentionally blank in the observation template. Model
predictions should be appended later as model-specific rows before calling
`dmm-validate-dense`.

## Bbox policy

For consistency with other DMM validation sites, use the observation-point bbox
from `tarrawarra_points_bbox.json` when extracting terrain/weather/model inputs.
Do not use the local DEM extent as the feature-extraction AOI, because the DEM
has a larger rotated footprint than the actual point observations.

## Example

```bash
PYTHONPATH=src python scripts/sites/tarrawarra/convert_tarrawarra_ascii.py \
  --dem-local path/to/tarrawar.dem \
  --tdr-dir path/to/tdr_maps \
  --outdir outputs/tarrawarra_conversion
```

## Model6/model8 comparison

After conversion, run the Tarrawarra-specific bridge from this `DMM_validation`
repo while pointing it at a checked-out `DownscalingMoistureModel` repo:

```bash
/opt/miniconda3/envs/paddockts/bin/python \
  scripts/sites/tarrawarra/run_tarrawarra_model6_model8_comparison.py \
  --dmm-repo /Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel
```

The bridge writes model-specific prediction tables, combined model-agnostic
tables, per-date GeoTIFF prediction maps, logs, and a `dmm-validate-dense`
report under `outputs/tarrawarra_model6_vs_model8/`. Terrain, soil, weather,
and SMIPS diagnostics are sampled using the point-derived bbox above.
