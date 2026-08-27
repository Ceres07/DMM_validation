# Script Layout

Source scripts are grouped by role.

- `sites/esdale/`: Esdale dense-campaign table builders.
- `sites/tarrawarra/`: Tarrawarra conversion, aggregation, and model6/model8 bridge scripts.
- `sites/llara/`: Llara probe adapter and native raster helpers.
- `sites/mri/`: standalone Mulloon Rehydration Initiative probe validation.
- `sites/nerrigundah/`: reserved for the Nerrigundah dense-campaign adapter.
- `analyses/unified_dense/`: manuscript-scale dense validation orchestration and figures.
- `analyses/local_calibration/`: sparse local calibration and temporal-CV experiments.
- `analyses/model_space/`: model-input/covariate-space diagnostics.
- `shared/`: reserved for script-side utilities that are not ready for `src/dmm_validation`.

Primary entrypoints:

```bash
python scripts/analyses/unified_dense/run_unified_dense_validation.py
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/mri/run_mri_model6_model8_validation.py
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/tarrawarra/run_tarrawarra_model6_model8_comparison.py
```
