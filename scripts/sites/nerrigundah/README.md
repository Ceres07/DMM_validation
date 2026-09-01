# Nerrigundah

Adapter notes for the Nerrigundah dense-campaign validation.

Raw data have been downloaded from Jeff Walker's Monash-hosted Nerrigundah
catchment page:

- Source page: `https://users.monash.edu.au/~jpwalker/data/nerrigundah/index.html`
- Data archive: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/data.zip`
- Extracted data: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/data/`
- Documentation archive: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/documentation.zip`
- Extracted documentation: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/documentation/`

Primary inputs:

- `GM-TDR/TDR*.dat`: 12 near-surface 15 cm TDR maps on a 20 m local grid.
- `DEM/ACCURATE/nerrig-local.grd` and `DEM/ACCURATE/nerrig-amg.xyz`: accurate DEM products.
- `TRANSFORM/trans-par.dat`: local-to-AMG coordinate transformation parameters.
- `CON-TDR/cTDR-*.dat`: 13 profile TDR locations for profile/context checks.

Current Stage 1 workflow:

```bash
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/nerrigundah/convert_nerrigundah_gm_tdr.py
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/tarrawarra/run_tarrawarra_model6_model8_comparison.py \
  --observations outputs/nerrigundah_conversion/nerrigundah_dmm_observation_template.csv \
  --bbox-json outputs/nerrigundah_conversion/nerrigundah_points_bbox.json \
  --outdir outputs/nerrigundah_model6_vs_model8 \
  --run-label nerrigundah \
  --model8-step-deg 0.05 \
  --no-validation
/opt/miniconda3/envs/paddockts/bin/python scripts/sites/tarrawarra/aggregate_tarrawarra_to_model_grid.py \
  --input outputs/nerrigundah_model6_vs_model8/model6_model8_combined_predictions_valid.csv \
  --map-dir outputs/nerrigundah_model6_vs_model8/maps \
  --output outputs/nerrigundah_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv \
  --summary outputs/nerrigundah_model6_vs_model8/nerrigundah_30m_gridcell_aggregation_summary.json \
  --site-prefix nerrigundah
```

`convert_nerrigundah_gm_tdr.py` filters the artificial-looking GM-TDR boundary
anchor rows outside the DEM-supported local grid, then inverts the published
AMG-to-local transform and converts AGD66/AMG zone 56 coordinates to WGS84.

Reference:

Walker, J. P., Willgoose, G. R., and Kalma, J. D. (2001). The Nerrigundah Data
Set: Soil Moisture Patterns, Soil Characteristics, and Hydrological Flux
Measurements. Water Resources Research, 37(11), 2653-2658.
https://doi.org/10.1029/2001WR000545
