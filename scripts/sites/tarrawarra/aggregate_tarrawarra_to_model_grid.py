#!/usr/bin/env python3
"""Aggregate Tarrawarra point observations to model prediction grid cells.

Tarrawarra campaign points are much closer together than the ~30 m DMM output
grid.  Point-level validation therefore over-weights sub-grid variability that
the gridded models cannot resolve.  This script collapses observations to one
row per model/date/model-grid-cell and samples the prediction directly from the
corresponding model GeoTIFF cell.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = ROOT / "outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid.csv"
DEFAULT_MAP_DIR = ROOT / "outputs/tarrawarra_model6_vs_model8/maps"
DEFAULT_OUTPUT = (
    ROOT
    / "outputs/tarrawarra_model6_vs_model8/"
    / "model6_model8_combined_predictions_valid_30m_gridcell.csv"
)
DEFAULT_SUMMARY = ROOT / "outputs/tarrawarra_model6_vs_model8/tarrawarra_30m_gridcell_aggregation_summary.json"

MODEL_INPUT_COLUMNS = [
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
    "smips_totalbucket",
    "smips_7d",
    "smips_30d",
    "smips_365d",
    "smips_anom",
    "depth_cm",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--map-dir", type=Path, default=DEFAULT_MAP_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument(
        "--models",
        default="model6_rf,model8_process",
        help="Comma-separated model labels matching map filenames.",
    )
    return parser.parse_args()


def model_raster_path(map_dir: Path, model_name: str, day: str) -> Path:
    return map_dir / f"{model_name}_{day}.tif"


def attach_grid_indices(group: pd.DataFrame, raster_path: Path) -> pd.DataFrame:
    import rasterio
    from pyproj import Transformer

    if not raster_path.exists():
        raise FileNotFoundError(raster_path)

    out = group.copy()
    with rasterio.open(raster_path) as src:
        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
        xs, ys = transformer.transform(out["lon"].to_numpy(dtype=float), out["lat"].to_numpy(dtype=float))
        rows, cols = rasterio.transform.rowcol(src.transform, xs, ys)
        rows = np.asarray(rows, dtype=int)
        cols = np.asarray(cols, dtype=int)
        inside = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width)
        out = out.loc[inside].copy()
        rows = rows[inside]
        cols = cols[inside]
        if out.empty:
            return out

        arr = src.read(1).astype("float64")
        pred = arr[rows, cols]
        if src.nodata is not None:
            pred = np.where(pred == src.nodata, np.nan, pred)
        centers = [rasterio.transform.xy(src.transform, int(r), int(c), offset="center") for r, c in zip(rows, cols)]
        center_x = np.asarray([p[0] for p in centers], dtype=float)
        center_y = np.asarray([p[1] for p in centers], dtype=float)
        to_wgs84 = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
        center_lon, center_lat = to_wgs84.transform(center_x, center_y)

        out["grid_row"] = rows
        out["grid_col"] = cols
        out["grid_cell_id"] = [f"tarrawarra_grid_r{r:03d}_c{c:03d}" for r, c in zip(rows, cols)]
        out["grid_x"] = center_x
        out["grid_y"] = center_y
        out["grid_lon"] = center_lon
        out["grid_lat"] = center_lat
        out["raster_pred_sm_pct"] = pred
        out["raster_crs"] = str(src.crs)
        out["raster_cell_width_m"] = float(abs(src.transform.a))
        out["raster_cell_height_m"] = float(abs(src.transform.e))
    return out


def aggregate_group(group: pd.DataFrame) -> pd.Series:
    row: dict[str, object] = {
        "model_name": group["model_name"].iloc[0],
        "point_id": group["grid_cell_id"].iloc[0],
        "date": group["date"].iloc[0],
        "lon": float(group["grid_lon"].iloc[0]),
        "lat": float(group["grid_lat"].iloc[0]),
        "obs_sm_pct": float(group["obs_sm_pct"].mean()),
        "pred_sm_pct": float(group["raster_pred_sm_pct"].iloc[0]),
        "n_raw_points": int(len(group)),
        "obs_sm_sd": float(group["obs_sm_pct"].std(ddof=1)) if len(group) > 1 else 0.0,
        "obs_sm_min": float(group["obs_sm_pct"].min()),
        "obs_sm_max": float(group["obs_sm_pct"].max()),
        "raw_point_id_examples": ",".join(group["point_id"].astype(str).head(5)),
        "grid_row": int(group["grid_row"].iloc[0]),
        "grid_col": int(group["grid_col"].iloc[0]),
        "grid_x": float(group["grid_x"].iloc[0]),
        "grid_y": float(group["grid_y"].iloc[0]),
        "raster_crs": group["raster_crs"].iloc[0],
        "raster_cell_width_m": float(group["raster_cell_width_m"].iloc[0]),
        "raster_cell_height_m": float(group["raster_cell_height_m"].iloc[0]),
    }
    for col in MODEL_INPUT_COLUMNS:
        if col in group.columns:
            row[col] = float(pd.to_numeric(group[col], errors="coerce").mean())
    return pd.Series(row)


def aggregate(df: pd.DataFrame, map_dir: Path, models: list[str]) -> tuple[pd.DataFrame, dict]:
    work = df[df["model_name"].astype(str).isin(models)].copy()
    work["date"] = pd.to_datetime(work["date"]).dt.date.astype(str)
    required = {"model_name", "date", "point_id", "lon", "lat", "obs_sm_pct"}
    missing = required.difference(work.columns)
    if missing:
        raise ValueError(f"Input table missing columns: {sorted(missing)}")

    pieces = []
    logs = []
    for (model_name, day), group in work.groupby(["model_name", "date"], sort=True):
        raster_path = model_raster_path(map_dir, str(model_name), str(day))
        gridded = attach_grid_indices(group, raster_path)
        gridded = gridded.dropna(subset=["raster_pred_sm_pct", "grid_cell_id", "obs_sm_pct"])
        if gridded.empty:
            logs.append(
                {
                    "model_name": model_name,
                    "date": day,
                    "raw_rows": int(len(group)),
                    "gridcell_rows": 0,
                    "status": "empty_after_grid_assignment",
                }
            )
            continue
        aggregated = pd.DataFrame(
            [
                aggregate_group(cell_group)
                for _, cell_group in gridded.groupby(["model_name", "date", "grid_cell_id"], sort=True)
            ]
        ).reset_index(drop=True)
        pieces.append(aggregated)
        logs.append(
            {
                "model_name": model_name,
                "date": day,
                "raw_rows": int(len(group)),
                "gridcell_rows": int(len(aggregated)),
                "mean_raw_points_per_gridcell": float(aggregated["n_raw_points"].mean()),
                "max_raw_points_per_gridcell": int(aggregated["n_raw_points"].max()),
                "status": "ok",
            }
        )

    out = pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()
    leading = [
        "model_name",
        "point_id",
        "date",
        "lon",
        "lat",
        "obs_sm_pct",
        "pred_sm_pct",
        "n_raw_points",
        "obs_sm_sd",
        "obs_sm_min",
        "obs_sm_max",
        "grid_row",
        "grid_col",
        "grid_x",
        "grid_y",
    ]
    out = out[[c for c in leading if c in out.columns] + [c for c in out.columns if c not in leading]]

    summary = {
        "input_rows": int(len(work)),
        "output_rows": int(len(out)),
        "models": sorted(work["model_name"].astype(str).unique()),
        "dates": int(work["date"].nunique()),
        "raw_unique_points": int(work["point_id"].nunique()),
        "gridcell_unique_points": int(out["point_id"].nunique()) if not out.empty else 0,
        "raw_rows_by_model": work["model_name"].astype(str).value_counts().to_dict(),
        "gridcell_rows_by_model": out["model_name"].astype(str).value_counts().to_dict() if not out.empty else {},
        "aggregation": "mean observed soil moisture per model/date/model-grid-cell; prediction sampled from corresponding model GeoTIFF cell",
        "logs": logs,
    }
    return out, summary


def main() -> int:
    args = parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    df = pd.read_csv(args.input)
    out, summary = aggregate(df, args.map_dir, models)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "logs"}, indent=2), flush=True)
    print(f"wrote {args.output}", flush=True)
    print(f"wrote {args.summary}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
