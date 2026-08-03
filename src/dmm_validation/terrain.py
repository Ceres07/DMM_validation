from __future__ import annotations

import numpy as np
import pandas as pd


DEFAULT_TERRAIN_CANDIDATES = [
    "elevation",
    "slope",
    "northness",
    "eastness",
    "twi",
    "hli",
    "accumulation",
    "soil_clay",
    "soil_sand",
    "soil_awc",
    "soil_bdw",
    "rain_7",
    "rain_30",
    "rain_365",
    "ppet_30",
    "ppet_365",
    "vpd_30",
    "rain_365_anom",
    "terrain_zone",
    "landform",
    "soil_class",
]


NON_TERRAIN_COLUMNS = {
    "model_name",
    "point_id",
    "date",
    "lon",
    "lat",
    "obs_sm_pct",
    "pred_sm_pct",
    "season",
    "season_year",
    "residual",
    "abs_error",
    "sq_error",
    "depth_cm",
    "measurement_id",
    "replicate_id",
}


def detect_terrain_columns(df: pd.DataFrame, requested: str | None = None) -> list[str]:
    if requested and requested.lower() not in {"auto", "none"}:
        return [c.strip() for c in requested.split(",") if c.strip() in df.columns]
    if requested and requested.lower() == "none":
        return []

    present = [c for c in DEFAULT_TERRAIN_CANDIDATES if c in df.columns]
    if present:
        return present

    # Fallback: numeric columns that are not core validation fields.
    numeric = df.select_dtypes(include=[np.number]).columns.tolist()
    return [c for c in numeric if c not in NON_TERRAIN_COLUMNS]


def add_terrain_strata(
    df: pd.DataFrame,
    terrain_cols: list[str],
    q: int = 3,
) -> tuple[pd.DataFrame, list[dict]]:
    """Add low/mid/high style strata columns for terrain diagnostics."""
    out = df.copy()
    metadata: list[dict] = []

    for col in terrain_cols:
        if col not in out.columns:
            continue
        stratum_col = f"{col}_stratum"
        series = out[col]

        if pd.api.types.is_numeric_dtype(series):
            finite = series[np.isfinite(series)]
            if finite.nunique() < 2:
                continue
            try:
                bins = pd.qcut(series, q=q, duplicates="drop")
            except ValueError:
                continue
            n_bins = bins.cat.categories.size
            if n_bins < 2:
                continue
            if n_bins == 2:
                labels = ["low", "high"]
            elif n_bins == 3:
                labels = ["low", "mid", "high"]
            else:
                labels = [f"q{i + 1}" for i in range(n_bins)]
            code = bins.cat.codes
            out[stratum_col] = pd.Series(
                np.where(code >= 0, np.asarray(labels, dtype=object)[code], None),
                index=out.index,
            )
            metadata.append(
                {
                    "terrain_var": col,
                    "stratum_col": stratum_col,
                    "type": "quantile",
                    "n_strata": int(n_bins),
                }
            )
        else:
            if series.nunique(dropna=True) < 2:
                continue
            out[stratum_col] = series.astype(str)
            metadata.append(
                {
                    "terrain_var": col,
                    "stratum_col": stratum_col,
                    "type": "categorical",
                    "n_strata": int(series.nunique(dropna=True)),
                }
            )

    return out, metadata

