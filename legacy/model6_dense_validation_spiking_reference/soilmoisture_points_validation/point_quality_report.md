# Point prediction-quality raster report

Rasterised point metric radius: 45.0 m. If point buffers overlap, the nearest point wins for each pixel.

Primary GeoTIFF: `point_quality_nse_r2.tif`.

Multiband GeoTIFF: `point_quality_metrics.tif` with bands: nse, r2, r, bias, rmse, ubrmse, n, rank_nse.

## Best points by NSE/R²

| point | nse | r | bias | rmse | n | lon | lat | quality_class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6e | 0.457 | 0.811 | 0.560 | 2.785 | 7 | 148.921 | -35.104 | positive |
| 20o | 0.448 | 0.813 | 0.377 | 4.118 | 8 | 148.933 | -35.088 | positive |
| 37o | 0.412 | 0.738 | -1.199 | 4.951 | 7 | 148.933 | -35.087 | positive |
| 4e | 0.384 | 0.773 | -0.414 | 4.337 | 7 | 148.926 | -35.094 | positive |
| 36e | 0.369 | 0.707 | -0.096 | 5.084 | 8 | 148.934 | -35.087 | positive |
| 32e | 0.354 | 0.769 | 0.329 | 5.170 | 7 | 148.921 | -35.105 | positive |
| 8e | 0.335 | 0.771 | 0.423 | 6.999 | 6 | 148.941 | -35.088 | positive |
| 17o | 0.297 | 0.595 | 0.264 | 4.905 | 7 | 148.931 | -35.088 | positive |
| 29e | 0.286 | 0.754 | -0.887 | 3.735 | 6 | 148.931 | -35.096 | positive |
| 22e | 0.284 | 0.751 | 1.146 | 5.604 | 8 | 148.927 | -35.097 | positive |

## Worst points by NSE/R²

| point | nse | r | bias | rmse | n | lon | lat | quality_class |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 13o | -3.114 | 0.705 | -11.072 | 12.370 | 7 | 148.937 | -35.094 | very_poor |
| 15o | -2.568 | 0.461 | -6.294 | 7.130 | 7 | 148.931 | -35.097 | very_poor |
| 25o | -2.172 | 0.753 | -10.440 | 11.588 | 7 | 148.924 | -35.087 | very_poor |
| 18e | -1.838 | 0.592 | -10.191 | 12.121 | 6 | 148.932 | -35.094 | very_poor |
| 12o | -1.820 | 0.664 | -6.786 | 7.702 | 8 | 148.931 | -35.106 | very_poor |
| 33o | -1.592 | 0.706 | -7.889 | 9.039 | 8 | 148.928 | -35.106 | very_poor |
| 24o | -1.520 | 0.759 | 6.508 | 7.347 | 7 | 148.933 | -35.099 | very_poor |
| 35o | -1.475 | 0.307 | 5.953 | 7.663 | 7 | 148.932 | -35.098 | very_poor |
| 37e | -1.415 | 0.598 | 7.031 | 8.371 | 7 | 148.941 | -35.088 | very_poor |
| 19o | -1.316 | 0.345 | -7.119 | 9.048 | 9 | 148.926 | -35.100 | very_poor |

## Strongest source-terrain correlations with NSE/R²

| terrain_variable | pearson_r_with_nse | n |
| --- | --- | --- |
| Soil_depth | -0.375 | 77 |
| Zone | 0.320 | 70 |
| PISR_antecedent | 0.307 | 77 |
| PISR_retention | 0.306 | 77 |
| PISR_total | 0.280 | 77 |
| Slope | 0.254 | 76 |
| ilr1 | -0.214 | 77 |
| ilr2 | 0.179 | 77 |
| TWI | -0.177 | 77 |
| Rain_total_7days | 0.081 | 77 |
| Days_since_rain_.24_hour_period. | -0.063 | 77 |
| Rain_total_period | 0.058 | 77 |
