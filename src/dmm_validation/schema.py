from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import add_error_columns
from .seasons import add_season_columns


REQUIRED_COLUMNS = ["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]

ALIASES = {
    "model": "model_name",
    "model_id": "model_name",
    "point": "point_id",
    "site": "point_id",
    "station": "point_id",
    "timestamp": "date",
    "time": "date",
    "longitude": "lon",
    "lng": "lon",
    "x": "lon",
    "latitude": "lat",
    "y": "lat",
    "observed": "obs_sm_pct",
    "obs": "obs_sm_pct",
    "soil_moisture_obs": "obs_sm_pct",
    "soil_moisture_observed": "obs_sm_pct",
    "prediction": "pred_sm_pct",
    "pred": "pred_sm_pct",
    "soil_moisture_pred": "pred_sm_pct",
    "soil_moisture_prediction": "pred_sm_pct",
}


def _normalise_name(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Rename common input-column variants to the validation schema."""
    rename = {}
    seen: set[str] = set()
    for col in df.columns:
        norm = _normalise_name(col)
        canonical = ALIASES.get(norm, norm)
        if canonical in seen:
            # Preserve duplicate-like fields rather than silently clobbering.
            canonical = norm
        rename[col] = canonical
        seen.add(canonical)
    out = df.rename(columns=rename)
    return out


def load_prediction_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        raw = pd.read_parquet(path)
    else:
        raw = pd.read_csv(path)
    return prepare_prediction_table(raw)


def prepare_prediction_table(df: pd.DataFrame) -> pd.DataFrame:
    out = standardise_columns(df)

    missing = [c for c in REQUIRED_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(
            "Prediction table is missing required columns: "
            + ", ".join(missing)
            + ". Required schema: "
            + ", ".join(REQUIRED_COLUMNS)
        )

    out["model_name"] = out["model_name"].astype(str)
    out["point_id"] = out["point_id"].astype(str)
    out["date"] = pd.to_datetime(out["date"]).dt.date.astype(str)
    for col in ["lon", "lat", "obs_sm_pct", "pred_sm_pct"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=REQUIRED_COLUMNS).reset_index(drop=True)
    out = add_season_columns(out)
    out = add_error_columns(out)
    return out


def default_pair_keys(df: pd.DataFrame) -> list[str]:
    keys = ["point_id", "date"]
    for candidate in ["depth_cm", "measurement_id", "replicate_id"]:
        if candidate in df.columns:
            keys.append(candidate)
    return keys

