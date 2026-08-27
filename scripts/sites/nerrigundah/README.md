# Nerrigundah

Placeholder for a future Nerrigundah dense-campaign adapter.

Raw data have been downloaded from Jeff Walker's Monash-hosted Nerrigundah
catchment page:

- Source page: `https://users.monash.edu.au/~jpwalker/data/nerrigundah/index.html`
- Data archive: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/data.zip`
- Extracted data: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/data/`
- Documentation archive: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/documentation.zip`
- Extracted documentation: `/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/documentation/`

For a Tarrawarra-like dense validation adapter, the likely primary inputs are:

- `GM-TDR/TDR*.dat`: 12 near-surface 15 cm TDR maps on a 20 m local grid.
- `DEM/ACCURATE/nerrig-local.grd` and `DEM/ACCURATE/nerrig-amg.xyz`: accurate DEM products.
- `TRANSFORM/trans-par.dat`: local-to-AMG coordinate transformation parameters.
- `CON-TDR/cTDR-*.dat`: 13 profile TDR locations for profile/context checks.

Reference:

Walker, J. P., Willgoose, G. R., and Kalma, J. D. (2001). The Nerrigundah Data
Set: Soil Moisture Patterns, Soil Characteristics, and Hydrological Flux
Measurements. Water Resources Research, 37(11), 2653-2658.
https://doi.org/10.1029/2001WR000545
