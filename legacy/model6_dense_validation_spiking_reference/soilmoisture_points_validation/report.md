# Soil-moisture point validation report

Input CSV: `/Volumes/Dmitry_work/borevitz_projects/Data/soilmoisture_points_coordinates.csv`

Generated/sampled dates: 2025-04-30, 2025-05-07, 2025-05-21, 2025-05-27, 2025-06-22, 2025-06-26, 2025-07-03, 2025-07-11, 2025-07-17

BBox used: `148.918296 -35.108100 148.947784 -35.084795` (`W S E N`, EPSG:4326)

Rows:

- source rows: 631
- rows with usable date, observation and coordinates: 560
- excluded rows: 71
- sampled prediction/observation pairs: 560

## Handout-style summary

| Skill | model6 on soil-moisture point CSV |
|---|---:|
| Pooled NSE / r | 0.023 / 0.238 |
| RMSE / ubRMSE / bias | 6.477 / 6.453 / -0.558 % |
| Median per-point \|bias\| | 2.26 % |
| Per-point NSE > 0 | 43/79 |

## Caveat

The handout model predicts OzNet-style root-zone soil moisture, while this CSV
appears to contain shallower point measurements. These scores are therefore best
read as an external terrain-transfer diagnostic rather than a strict root-zone
validation unless the field measurement depth is reconciled.
