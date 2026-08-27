# DMM validation

This repository contains the model-agnostic validation layer for the
DownscalingMoistureModel project.

The current primary output is the unified dense-point validation and local
spiking report:

[`reports/analyses/unified_dense_validation/unified_dense_validation_report.md`](reports/analyses/unified_dense_validation/unified_dense_validation_report.md)

The protocol follows the two-stage plan in:

[`docs/Downscaling moisture validation plan.pdf`](docs/Downscaling%20moisture%20validation%20plan.pdf)

Mulloon Rehydration Initiative (MRI) probes are currently kept in a separate
validation run while the unified dense report remains unchanged:

[`reports/sites/mri_dense_validation/mri_dense_validation_report.md`](reports/sites/mri_dense_validation/mri_dense_validation_report.md)

## Current protocol

### Stage 1 — independent dense-point validation

All point/date observations are used only as external validation. The scoring
table is model-agnostic: every model is judged by `point_id`, `date`, observed
soil moisture and predicted soil moisture.

Outputs include:

- pooled and per-site NSE/R², Pearson r, RMSE, ubRMSE, bias and MAE;
- seasonal and dry/wet-state bias diagnostics;
- terrain/model-input stratified error summaries;
- paired model comparisons;
- point-level prediction-quality maps.

### Stage 2 — local training-data spiking

Small subsets of local points are used as calibration spikes, then evaluated on
held-out points/dates. The strict spatial+temporal block is treated as the main
transfer test.

Calibration layers currently include:

- constant residual offset;
- seasonal residual offset;
- affine correction;
- regularised residual ridge layer using prediction-time model inputs.

The target analysis asks how many local points are needed to approach or exceed
held-out NSE/R² > 0.4, and whether the process model responds differently from
the statistical model.

## Dense validation sites

- **Esdale** — modern dense campaign, autumn/winter 2025.
- **Tarrawarra** — very dense 1995/96 campaign; note the current model6 run has
  a known SMIPS-zero caveat.
- **Llara** — profile-mean probe time series from 2021–2024; point-level SMIPS
  columns are available, but full gridded Llara model GeoTIFFs are not currently
  cached.

MRI is staged separately for now. The runner uses
`/Volumes/Dmitry_work/borevitz_projects/Data/MRI_data/SM_combined_cleaned/SM(%)_combined_cleaned.csv`
for probe values, `Soil_Moisture_Probes` for labels/coordinates,
`HT_Measurement_Point_Matrix` for logger serial crosswalks, and records
`SM_metadata.pdf` as the metadata reference.

## Re-running

From the repository root:

```bash
python scripts/analyses/unified_dense/run_unified_dense_validation.py
```

Useful faster/report-only rerun after Stage 2 already exists:

```bash
python scripts/analyses/unified_dense/run_unified_dense_validation.py --skip-stage2
```

Run the separate MRI validation with the PaddockTS-compatible environment:

```bash
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/mri/run_mri_model6_model8_validation.py
```

Main outputs:

- `outputs/unified_dense_validation/stage1_independent_validation/`
- `outputs/unified_dense_validation/stage2_local_spiking/`
- `reports/analyses/unified_dense_validation/`
- `outputs/mri_dense_validation/`
- `reports/sites/mri_dense_validation/`

Generated geospatial/model outputs are intentionally ignored by git; reports,
figures, scripts and docs are intended to be versioned.
