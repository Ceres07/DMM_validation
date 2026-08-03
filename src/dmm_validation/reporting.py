from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


def markdown_table(df: pd.DataFrame, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No rows._"
    show = df.head(max_rows).copy()
    for col in show.columns:
        if pd.api.types.is_numeric_dtype(show[col]):
            show[col] = show[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    headers = [str(c) for c in show.columns]
    rows = [[str(value) for value in record] for record in show.to_numpy()]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    header = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
    sep = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    body = ["| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(headers))) + " |" for row in rows]
    text = "\n".join([header, sep] + body)
    if len(df) > max_rows:
        text += f"\n\n_Showing first {max_rows} of {len(df)} rows._"
    return text


def write_geojson_points(df: pd.DataFrame, out_path: Path, lon_col: str = "lon", lat_col: str = "lat") -> None:
    features = []
    for _, row in df.iterrows():
        lon = row.get(lon_col)
        lat = row.get(lat_col)
        if not np.isfinite(lon) or not np.isfinite(lat):
            continue
        props = {}
        for key, value in row.items():
            if key in {lon_col, lat_col}:
                continue
            if isinstance(value, (np.integer, np.floating)):
                value = value.item()
            if pd.isna(value):
                value = None
            props[key] = value
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
                "properties": props,
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_report(
    out_path: Path,
    prediction_path: Path,
    summary: dict,
    overall: pd.DataFrame,
    seasonal: pd.DataFrame,
    seasonal_bias: pd.DataFrame,
    moisture_bias: pd.DataFrame,
    paired_overall: pd.DataFrame,
    paired_season: pd.DataFrame,
    terrain_metrics: pd.DataFrame,
) -> None:
    body = f"""# Independent dense-point validation report

Input prediction table:

`{prediction_path}`

Validation rows: {summary["n_rows"]}

Models: {", ".join(summary["models"])}

Points: {summary["n_points"]}

Dates: {summary["date_min"]} to {summary["date_max"]}

## Overall skill

`r2` is reported as the NSE/coefficient-of-determination style score
`1 - SS_res / SS_tot`. Pearson correlation is reported separately as
`pearson_r` and `pearson_r2`.

{markdown_table(overall)}

## Seasonal skill

{markdown_table(seasonal)}

## Seasonal bias summary

`seasonal_bias_amplitude` is the difference between the most positive and most
negative seasonal mean bias for each model.

{markdown_table(seasonal_bias)}

## Dry/wet regime bias

Observed soil moisture is split into quartiles. This helps show whether a model
is systematically biased in dry or wet conditions even when pooled RMSE looks
acceptable.

{markdown_table(moisture_bias)}

## Paired model comparison

Negative `mean_delta_abs_error` means `model_a` had lower absolute error than
`model_b` on the same point-date observations.

{markdown_table(paired_overall)}

## Paired model comparison by season

{markdown_table(paired_season)}

## Terrain-stratified error

Terrain strata are diagnostic only. They are used to interpret where errors
occur; they are not assumed to be inputs used by any model.

{markdown_table(terrain_metrics)}

## Figures

See the `figures/` folder for:

- observed-vs-predicted scatter by season;
- mean observed/predicted time series;
- residual time series;
- seasonal bias boxplots;
- point-level maps of RMSE, bias and NSE/R²;
- paired RF-vs-process error-difference maps when two or more models are present.

## Interpretation guardrails

This report is an independent validation protocol. Do not mix local calibration
or spiking into the primary score. If local calibration is tested, run it as a
separate experiment with explicit calibration and validation windows.
"""
    out_path.write_text(body, encoding="utf-8")
