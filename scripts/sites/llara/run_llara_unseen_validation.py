#!/usr/bin/env python3
"""Run unseen model6/model8 validation on the Llara soil-moisture probes.

This script is an adapter between the Llara Landscape Rehydration Project CSVs
and the model-agnostic DMM_validation protocol. It keeps Llara-specific parsing,
depth-channel handling, and DownscalingMoistureModel inference out of the core
validation package.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
import re
import shutil
import sys
from datetime import date as _date
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
from pyproj import Transformer


os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_DIR = Path("/Volumes/Dmitry_work/borevitz_projects/Data/Llara_data")
DEFAULT_DMM_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel")
DEFAULT_OUTDIR = DMM_VALIDATION_ROOT / "outputs/llara_unseen_model6_vs_model8"
DEFAULT_REPORT_DIR = DMM_VALIDATION_ROOT / "reports" / "sites" / "llara_unseen_model6_vs_model8"

MODEL_LABELS = {"model6": "model6 boosted ML", "model8_process": "model8 process"}
MODEL_ORDER = ["model6", "model8_process"]
SOURCE_CRS = "EPSG:32755"  # UTM zone 55S; Llara coordinates are metres.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--dmm-repo", type=Path, default=DEFAULT_DMM_REPO)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--model6-name", default="model6")
    parser.add_argument("--model8-name", default="model8")
    parser.add_argument("--bbox-padding-deg", type=float, default=0.01)
    parser.add_argument("--model8-step-deg", type=float, default=0.05)
    parser.add_argument("--min-depth-channels", type=int, default=3)
    parser.add_argument("--smips-lookback-days", type=int, default=365)
    parser.add_argument("--smips-workers", type=int, default=4)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def _add_paths_and_chdir(dmm_repo: Path) -> None:
    sys.path.insert(0, str(DMM_VALIDATION_ROOT / "src"))
    sys.path.insert(0, str(dmm_repo))
    os.chdir(dmm_repo)


def _channel_num(channel: str) -> int:
    match = re.search(r"(\d+)", str(channel))
    return int(match.group(1)) if match else -1


def _device_to_probe(device: str) -> tuple[str | None, str | None, str | None]:
    """Return physical probe id, field, and probe-depth group from a device name."""
    match = re.match(r"^(WE|WW)\s+(12|16)-(\d{2})", str(device).strip())
    if not match:
        return None, None, None
    field, depth_group, probe_num = match.groups()
    return f"{field} MP {depth_group}{probe_num}", field, depth_group


def _valid_channel(depth_group: str, ch_num: int) -> bool:
    # The 12-series probes have usable channels v2-v12; v13-v16 are mostly
    # zero-filled absent channels. The 16-series probes use v2-v16.
    if depth_group == "12":
        return 2 <= ch_num <= 12
    if depth_group == "16":
        return 2 <= ch_num <= 16
    return False


def load_probe_locations(data_dir: Path) -> pd.DataFrame:
    loc = pd.read_csv(data_dir / "sm_probe_locs.csv")
    loc = loc.rename(
        columns={
            "Name": "probe_id",
            "Elevation": "probe_elevation_m",
            "Easting": "probe_easting_utm55s",
            "Northing": "probe_northing_utm55s",
        }
    )
    transformer = Transformer.from_crs(SOURCE_CRS, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(loc["probe_easting_utm55s"].to_numpy(), loc["probe_northing_utm55s"].to_numpy())
    loc["lon"] = lon
    loc["lat"] = lat
    loc["field"] = loc["probe_id"].str.extract(r"^(WE|WW)", expand=False)
    loc["probe_depth_group"] = loc["probe_id"].str.extract(r"MP\s+(12|16)", expand=False)
    loc["point_id"] = loc["probe_id"].str.replace(" ", "_", regex=False)
    return loc


def load_profile_mean_observations(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    loc = load_probe_locations(args.data_dir)
    frames = []
    source_rows = 0
    for fname in ["WW_cleanedData_20241022.csv", "WE_cleanedData_20241022.csv"]:
        raw = pd.read_csv(args.data_dir / fname)
        source_rows += len(raw)
        mapped = raw["device"].map(_device_to_probe)
        raw["probe_id"] = [v[0] for v in mapped]
        raw["field"] = [v[1] for v in mapped]
        raw["probe_depth_group"] = [v[2] for v in mapped]
        raw["ch_num"] = raw["channel"].map(_channel_num)
        raw["depth_cm_approx"] = (raw["ch_num"] - 1) * 10
        raw = raw[raw["probe_id"].notna()].copy()
        raw = raw[
            [
                _valid_channel(str(group), int(ch))
                for group, ch in zip(raw["probe_depth_group"], raw["ch_num"])
            ]
        ].copy()
        raw["soil_moisture"] = pd.to_numeric(raw["soil_moisture"], errors="coerce")
        frames.append(raw)

    long = pd.concat(frames, ignore_index=True)
    before_value_filter = len(long)
    # Zero/negative values are used heavily as absent-channel or bad-sensor
    # placeholders. Values above 100% VWC are physically implausible and removed.
    long = long[long["soil_moisture"].between(1e-6, 100.0)].copy()
    after_value_filter = len(long)
    long["date"] = pd.to_datetime(long["Date"]).dt.date.astype(str)

    by_channel = (
        long.groupby(["probe_id", "date", "channel", "depth_cm_approx"], as_index=False)
        .agg(
            soil_moisture=("soil_moisture", "mean"),
            n_device_records=("soil_moisture", "size"),
        )
    )
    profile = (
        by_channel.groupby(["probe_id", "date"], as_index=False)
        .agg(
            obs_sm_pct=("soil_moisture", "mean"),
            obs_depth_sd=("soil_moisture", "std"),
            obs_depth_min=("soil_moisture", "min"),
            obs_depth_max=("soil_moisture", "max"),
            n_depth_channels=("soil_moisture", "size"),
            depth_cm_min=("depth_cm_approx", "min"),
            depth_cm_max=("depth_cm_approx", "max"),
            n_device_records=("n_device_records", "sum"),
        )
    )
    profile["obs_depth_sd"] = profile["obs_depth_sd"].fillna(0.0)
    profile = profile[profile["n_depth_channels"] >= args.min_depth_channels].copy()
    if args.start:
        profile = profile[profile["date"] >= args.start].copy()
    if args.end:
        profile = profile[profile["date"] <= args.end].copy()

    profile = profile.merge(loc, on="probe_id", how="left", suffixes=("", "_loc"))
    missing = profile[profile["lon"].isna()]["probe_id"].unique()
    if len(missing):
        raise ValueError(f"Missing coordinates for probes: {missing}")

    profile["model_name"] = "observation_only"
    profile["pred_sm_pct"] = np.nan
    cols = [
        "model_name",
        "point_id",
        "date",
        "lon",
        "lat",
        "obs_sm_pct",
        "pred_sm_pct",
        "probe_id",
        "field",
        "probe_depth_group",
        "probe_elevation_m",
        "probe_easting_utm55s",
        "probe_northing_utm55s",
        "obs_depth_sd",
        "obs_depth_min",
        "obs_depth_max",
        "n_depth_channels",
        "depth_cm_min",
        "depth_cm_max",
        "n_device_records",
    ]
    profile = profile[cols].sort_values(["point_id", "date"]).reset_index(drop=True)

    summary = {
        "source_rows": int(source_rows),
        "rows_after_channel_filter": int(before_value_filter),
        "rows_after_value_filter": int(after_value_filter),
        "profile_rows": int(len(profile)),
        "n_probes": int(profile["point_id"].nunique()),
        "n_dates": int(profile["date"].nunique()),
        "date_min": str(profile["date"].min()),
        "date_max": str(profile["date"].max()),
        "min_depth_channels": int(args.min_depth_channels),
        "value_filter": "0 < soil_moisture <= 100",
        "profile_mean_policy": "mean across valid depth channels after collapsing replacement devices by probe/date/channel",
    }
    return profile, summary


def bbox_from_points(points: pd.DataFrame, padding_deg: float) -> tuple[float, float, float, float]:
    return (
        float(points["lon"].min() - padding_deg),
        float(points["lat"].min() - padding_deg),
        float(points["lon"].max() + padding_deg),
        float(points["lat"].max() + padding_deg),
    )


def _doy(day: str) -> tuple[float, float]:
    d = pd.Timestamp(day).dayofyear
    return float(np.sin(2 * np.pi * d / 365.25)), float(np.cos(2 * np.pi * d / 365.25))


def _sample_dataarray_at_points(da, points: pd.DataFrame, value_name: str) -> pd.DataFrame:
    from emt.covariates import sample_points

    rows = []
    for point in points.itertuples(index=False):
        try:
            val = sample_points(da, float(point.lon), float(point.lat)).values
            rows.append({"point_id": point.point_id, value_name: float(np.asarray(val))})
        except Exception:
            rows.append({"point_id": point.point_id, value_name: np.nan})
    return pd.DataFrame(rows)


def sample_static_features(q, points: pd.DataFrame, quiet: bool = False) -> pd.DataFrame:
    from emt.covariates import TERRAIN_VARS, terrain_covariates
    from emt.slga import SOIL_VARS

    if not quiet:
        print("sampling terrain covariates ...", flush=True)
    terr = terrain_covariates(q)

    static = points[["point_id", "lon", "lat", "probe_id", "field", "probe_depth_group"]].copy()
    for var in TERRAIN_VARS:
        static = static.merge(_sample_dataarray_at_points(terr[var], points, var), on="point_id", how="left")
    if not quiet:
        print("sampling SLGA soil covariates at probe points ...", flush=True)
    soil = sample_slga_soil_at_points(points, quiet=quiet)
    for var in SOIL_VARS:
        static = static.merge(soil[["point_id", var]], on="point_id", how="left")
    return static


def sample_slga_soil_at_points(points: pd.DataFrame, quiet: bool = False) -> pd.DataFrame:
    """Depth-average SLGA soil attributes by sampling COGs directly at points."""
    import rasterio
    from rasterio.transform import rowcol
    from rasterio.windows import from_bounds

    from emt.slga import DEPTHS, SLGA_ATTR, SOIL_VARS
    from PaddockTS.Environmental.SLGASoils.utils import load_tern_api_key, _setup_tern_auth, get_cog_url

    api_key = load_tern_api_key()
    _setup_tern_auth(api_key)
    out = points[["point_id", "lon", "lat"]].copy()

    for var in SOIL_VARS:
        if not quiet:
            print(f"  SLGA {var} ...", flush=True)
        attr = SLGA_ATTR[var]
        values = []
        weights = []
        for depth, thickness in DEPTHS:
            url = get_cog_url(attr, depth, api_key)
            with rasterio.open(f"/vsicurl/{url}") as src:
                if src.crs is not None and src.crs.to_epsg() != 4326:
                    transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                    xs, ys = transformer.transform(points["lon"].to_numpy(), points["lat"].to_numpy())
                else:
                    xs = points["lon"].to_numpy(dtype=float)
                    ys = points["lat"].to_numpy(dtype=float)
                res_x = abs(src.transform.a)
                res_y = abs(src.transform.e)
                pad_x = res_x * 2
                pad_y = res_y * 2
                window = from_bounds(
                    float(np.nanmin(xs) - pad_x),
                    float(np.nanmin(ys) - pad_y),
                    float(np.nanmax(xs) + pad_x),
                    float(np.nanmax(ys) + pad_y),
                    transform=src.transform,
                ).round_offsets().round_lengths()
                data = src.read(1, window=window, masked=True)
                win_transform = src.window_transform(window)
                sampled = []
                for x, y in zip(xs, ys):
                    r, c = rowcol(win_transform, float(x), float(y))
                    if r < 0 or c < 0 or r >= data.shape[0] or c >= data.shape[1]:
                        sampled.append(np.nan)
                    else:
                        value = data[r, c]
                        sampled.append(np.nan if np.ma.is_masked(value) else float(value))
                sampled = np.asarray(sampled, dtype=float)
                nodata = src.nodata
                if nodata is not None:
                    sampled = np.where(sampled == nodata, np.nan, sampled)
                values.append(sampled)
                weights.append(float(thickness))
        arr = np.vstack(values)
        w = np.asarray(weights, dtype=float)[:, None]
        valid = np.isfinite(arr)
        numerator = np.nansum(np.where(valid, arr, 0.0) * w, axis=0)
        denominator = np.sum(np.where(valid, w, 0.0), axis=0)
        out[var] = np.where(denominator > 0, numerator / denominator, np.nan)
    return out


def sample_antecedent_features(q, points: pd.DataFrame, dates: list[str], quiet: bool = False) -> pd.DataFrame:
    from emt.antecedent import ANTECEDENT_VARS, antecedent_grid
    from emt.covariates import sample_points

    start = _date.fromisoformat(min(dates))
    end = _date.fromisoformat(max(dates))
    if not quiet:
        print("sampling SILO antecedent meteorology ...", flush=True)
    ante = antecedent_grid(q, start, end, verbose=not quiet)
    target_dates = pd.to_datetime(sorted(dates))
    rows = []
    for point in points.itertuples(index=False):
        frame = pd.DataFrame({"date": target_dates.date.astype(str)})
        for var in ANTECEDENT_VARS:
            series = sample_points(ante[var], float(point.lon), float(point.lat)).to_series()
            series.index = pd.to_datetime(series.index)
            frame[var] = series.reindex(target_dates).to_numpy(dtype=float)
        frame["point_id"] = point.point_id
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def sample_smips_features(
    q,
    points: pd.DataFrame,
    dates: list[str],
    bbox: tuple[float, float, float, float],
    workers: int = 8,
    quiet: bool = False,
    cache_path: Path | None = None,
    force: bool = False,
    lookback_days: int = 365,
) -> pd.DataFrame:
    import rasterio
    from rasterio.transform import rowcol
    from rasterio.windows import from_bounds
    from PaddockTS.config import config

    first = pd.Timestamp(min(dates))
    last = pd.Timestamp(max(dates))
    start = (first - pd.Timedelta(days=lookback_days)).date()
    if not quiet:
        print(f"fetching/sampling SMIPS COG lookbacks {start} → {last.date()} ...", flush=True)

    all_days = pd.date_range(start, last.date(), freq="D")
    target_dates = pd.to_datetime(sorted(dates))

    if cache_path is not None and cache_path.exists() and not force:
        cached = pd.read_csv(cache_path)
        cached["date"] = pd.to_datetime(cached["date"]).dt.date.astype(str)
        have_days = set(cached["date"].unique())
        have_points = set(cached["point_id"].unique())
        need_days = {d.date().isoformat() for d in all_days}
        need_points = set(points["point_id"])
        if need_days.issubset(have_days) and need_points.issubset(have_points):
            raw = cached[cached["date"].isin(need_days) & cached["point_id"].isin(need_points)].copy()
        else:
            raw = None
    else:
        raw = None

    api_key = config.tern_api_key
    if not api_key:
        raise ValueError("Set tern_api_key in ~/.config/PaddockTS.json for direct SMIPS COG access")
    os.environ["GDAL_HTTP_USERPWD"] = f"apikey:{api_key}"
    safe_key = quote(api_key, safe="")

    def cog_url(day: pd.Timestamp) -> str:
        ymd = day.strftime("%Y%m%d")
        return f"https://apikey:{safe_key}@data.tern.org.au/model-derived/smips/v1_0/totalbucket/{day.year}/smips_totalbucket_mm_{ymd}.tif"

    def sanitize_error(exc: Exception) -> str:
        msg = str(exc)
        if api_key:
            msg = msg.replace(api_key, "<redacted>")
        return msg[:300]

    def sample_one_day(day: pd.Timestamp) -> list[dict]:
        url = cog_url(day)
        with rasterio.open(f"/vsicurl/{url}") as src:
            if src.crs is not None and src.crs.to_epsg() != 4326:
                transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                xs, ys = transformer.transform(points["lon"].to_numpy(), points["lat"].to_numpy())
            else:
                xs = points["lon"].to_numpy(dtype=float)
                ys = points["lat"].to_numpy(dtype=float)
            res_x = abs(src.transform.a)
            res_y = abs(src.transform.e)
            window = from_bounds(
                float(np.nanmin(xs) - 2 * res_x),
                float(np.nanmin(ys) - 2 * res_y),
                float(np.nanmax(xs) + 2 * res_x),
                float(np.nanmax(ys) + 2 * res_y),
                transform=src.transform,
            ).round_offsets().round_lengths()
            data = src.read(1, window=window, masked=True)
            win_transform = src.window_transform(window)
            rows = []
            for point_id, x, y in zip(points["point_id"], xs, ys):
                r, c = rowcol(win_transform, float(x), float(y))
                if r < 0 or c < 0 or r >= data.shape[0] or c >= data.shape[1]:
                    value = np.nan
                else:
                    cell = data[r, c]
                    value = np.nan if np.ma.is_masked(cell) else float(cell)
                if src.nodata is not None and value == src.nodata:
                    value = np.nan
                rows.append(
                    {
                        "point_id": point_id,
                        "date": day.date().isoformat(),
                        "smips_totalbucket": value,
                        "smips_source": "TERN SMIPS v1.0 COG",
                    }
                )
            return rows

    if raw is None:
        rows = []
        failures = []
        def missing_rows(day: pd.Timestamp) -> list[dict]:
            return [
                {
                    "point_id": point_id,
                    "date": day.date().isoformat(),
                    "smips_totalbucket": np.nan,
                    "smips_source": "TERN SMIPS v1.0 COG",
                }
                for point_id in points["point_id"]
            ]

        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            GDAL_HTTP_MAX_RETRY="3",
            GDAL_HTTP_RETRY_DELAY="2",
            GDAL_HTTP_TIMEOUT="30",
        ):
            if workers and workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as ex:
                    futures = {ex.submit(sample_one_day, day): day for day in all_days}
                    for i, fut in enumerate(as_completed(futures), start=1):
                        day = futures[fut]
                        try:
                            rows.extend(fut.result())
                        except Exception as exc:
                            failures.append((day.date().isoformat(), sanitize_error(exc)))
                            rows.extend(missing_rows(day))
                        if not quiet and (i == 1 or i % 100 == 0 or i == len(all_days)):
                            print(f"  SMIPS COG days sampled {i}/{len(all_days)}", flush=True)
            else:
                for i, day in enumerate(all_days, start=1):
                    try:
                        rows.extend(sample_one_day(day))
                    except Exception as exc:
                        failures.append((day.date().isoformat(), sanitize_error(exc)))
                        rows.extend(missing_rows(day))
                    if not quiet and (i == 1 or i % 100 == 0 or i == len(all_days)):
                        print(f"  SMIPS COG days sampled {i}/{len(all_days)}", flush=True)
        raw = pd.DataFrame(rows)
        finite = np.isfinite(pd.to_numeric(raw["smips_totalbucket"], errors="coerce")).sum()
        if finite == 0:
            detail = "; ".join(f"{d}: {msg}" for d, msg in failures[:3])
            raise RuntimeError(f"No finite SMIPS COG samples were retrieved. First failures: {detail}")
        if failures and not quiet:
            print(f"  warning: {len(failures)} SMIPS COG day(s) failed; continuing with NaNs", flush=True)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            raw.to_csv(cache_path, index=False)

    target_dates = pd.to_datetime(sorted(dates))
    rows = []
    raw["date"] = pd.to_datetime(raw["date"])
    for point_id, group in raw.groupby("point_id"):
        s = group.sort_values("date").set_index("date")["smips_totalbucket"].astype(float)
        s = s.sort_index()
        out = pd.DataFrame(index=s.index)
        out["smips_totalbucket"] = s
        out["smips_7d"] = s.rolling(7, min_periods=1).mean()
        out["smips_30d"] = s.rolling(30, min_periods=1).mean()
        out["smips_365d"] = s.rolling(365, min_periods=1).mean()
        out["smips_anom"] = out["smips_totalbucket"] - out["smips_365d"]
        sub = out.reindex(target_dates).reset_index(names="date")
        sub["date"] = sub["date"].dt.date.astype(str)
        sub["point_id"] = point_id
        rows.append(sub)
    return pd.concat(rows, ignore_index=True)


def build_feature_table(
    args: argparse.Namespace,
    obs: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    dataset_prefix: str = "llara",
) -> pd.DataFrame:
    from PaddockTS.query import Query

    path = args.outdir / f"{dataset_prefix}_model_input_features.csv"
    if path.exists() and not args.force:
        return pd.read_csv(path)

    points = obs.drop_duplicates("point_id")[["point_id", "probe_id", "field", "probe_depth_group", "lon", "lat"]].copy()
    dates = sorted(obs["date"].unique())
    q = Query(
        bbox=list(bbox),
        start=_date.fromisoformat(min(dates)),
        end=_date.fromisoformat(max(dates)),
        stub=f"{dataset_prefix}_unseen_" + "_".join(f"{v:.3f}" for v in bbox).replace(".", "p").replace("-", "m"),
    )

    static = sample_static_features(q, points, quiet=args.quiet)
    ante = sample_antecedent_features(q, points, dates, quiet=args.quiet)
    smips = sample_smips_features(
        q,
        points,
        dates,
        bbox,
        quiet=args.quiet,
        cache_path=args.outdir / f"{dataset_prefix}_smips_point_timeseries.csv",
        force=args.force,
        lookback_days=args.smips_lookback_days,
        workers=args.smips_workers,
    )
    dynamic = ante.merge(smips, on=["point_id", "date"], how="outer")
    features = obs[["point_id", "date"]].merge(static, on="point_id", how="left").merge(dynamic, on=["point_id", "date"], how="left")
    for day in sorted(features["date"].unique()):
        idx = features["date"] == day
        sin_doy, cos_doy = _doy(day)
        features.loc[idx, "doy_sin"] = sin_doy
        features.loc[idx, "doy_cos"] = cos_doy
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(path, index=False)
    return features


def predict_model6(
    args: argparse.Namespace,
    obs: pd.DataFrame,
    features: pd.DataFrame,
    output_name: str = "model6_model_agnostic_predictions.csv",
    model_label: str = "model6",
) -> pd.DataFrame:
    from emt.model6 import model as model6_module
    from emt.persist import load_model

    path = args.outdir / output_name
    if path.exists() and not args.force:
        return pd.read_csv(path)

    model = load_model(args.model6_name)
    if model is None:
        raise FileNotFoundError(f"No {args.model6_name}.joblib model found in {Path.cwd() / 'data/models'}")

    table = obs.merge(features, on=["point_id", "date"], how="left", suffixes=("", "_feature"))
    X = table[model6_module.FEATURES].apply(pd.to_numeric, errors="coerce")
    valid = np.isfinite(X.to_numpy(dtype=float)).all(axis=1)
    table["pred_sm_pct"] = np.nan
    if valid.any():
        table.loc[valid, "pred_sm_pct"] = model.predict(X.loc[valid]).astype(float)
    table["model_name"] = model_label
    table["prediction_status"] = np.where(valid, "ok", "missing_feature")
    table.to_csv(path, index=False)
    return table


def predict_model8(
    args: argparse.Namespace,
    obs: pd.DataFrame,
    features: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    output_name: str = "model8_process_model_agnostic_predictions.csv",
    model_label: str = "model8_process",
) -> pd.DataFrame:
    from emt.model8.model import STATIC_VARS
    from emt.model8.predict import _forcing_grid, _load, _simulate, _spinup_start

    path = args.outdir / output_name
    if path.exists() and not args.force:
        return pd.read_csv(path)

    model = _load(None, args.model8_name)
    start = _date.fromisoformat(str(obs["date"].min()))
    end = _date.fromisoformat(str(obs["date"].max()))
    sim_start = _spinup_start(start)
    if not args.quiet:
        print(f"running model8 process storage {sim_start} → {end} ...", flush=True)
    forcing = _forcing_grid(bbox, sim_start, end, args.model8_step_deg, verbose=not args.quiet)
    if len(forcing) == 5:
        rain, pet, aridity, lons, lats = forcing
    else:
        rain, pet, lons, lats = forcing
        aridity = None
    storage = _simulate(rain, pet, model)
    times = pd.date_range(sim_start, periods=storage.shape[0], freq="D")

    import xarray as xr

    stor = xr.DataArray(
        storage.reshape(storage.shape[0], len(lats), len(lons)),
        coords={"time": times, "y": lats, "x": lons},
        dims=("time", "y", "x"),
    )

    table = obs.merge(features, on=["point_id", "date"], how="left", suffixes=("", "_feature"))
    if "aridity" in STATIC_VARS and (aridity is not None) and (
        "aridity" not in table.columns or table["aridity"].isna().all()
    ):
        aridity_grid = xr.DataArray(
            np.asarray(aridity, dtype=float).reshape(len(lats), len(lons)),
            coords={"y": lats, "x": lons},
            dims=("y", "x"),
        )
        aridity_vals = []
        for row in table.itertuples(index=False):
            try:
                val = aridity_grid.interp(x=float(row.lon), y=float(row.lat)).values
                aridity_vals.append(float(np.asarray(val)))
            except Exception:
                aridity_vals.append(np.nan)
        table["aridity"] = aridity_vals
    for col in STATIC_VARS:
        if col not in table.columns:
            table[col] = np.nan
    statics = table[STATIC_VARS].apply(pd.to_numeric, errors="coerce")
    stor_vals = []
    for row in table.itertuples(index=False):
        try:
            val = stor.sel(time=pd.Timestamp(row.date)).interp(x=float(row.lon), y=float(row.lat)).values
            stor_vals.append(float(np.asarray(val)))
        except Exception:
            stor_vals.append(np.nan)
    table["model8_storage_mm"] = stor_vals
    valid = np.isfinite(statics.to_numpy(dtype=float)).all(axis=1) & np.isfinite(table["model8_storage_mm"].to_numpy(dtype=float))
    table["pred_sm_pct"] = np.nan
    if valid.any():
        table.loc[valid, "pred_sm_pct"] = model.readout(
            table.loc[valid, "model8_storage_mm"].to_numpy(dtype=float),
            statics.loc[valid, STATIC_VARS].to_numpy(dtype=float),
        ).astype(float)
    table["model_name"] = model_label
    table["prediction_status"] = np.where(valid, "ok", "missing_feature")
    table.to_csv(path, index=False)
    return table


def run_validation(args: argparse.Namespace, prediction_path: Path) -> None:
    from dmm_validation.cli import main as validate_main

    validate_main(
        [
            "--predictions",
            str(prediction_path),
            "--outdir",
            str(args.outdir / "validation_report"),
            "--bootstrap",
            str(args.bootstrap),
        ]
    )


def _metric_table(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    from dmm_validation.metrics import metric_table
    from dmm_validation.schema import prepare_prediction_table

    return metric_table(prepare_prediction_table(df), group_cols)


def write_extra_metric_tables(args: argparse.Namespace, combined: pd.DataFrame) -> None:
    out = args.outdir / "validation_report"
    _metric_table(combined, ["model_name", "field"]).to_csv(out / "metrics_by_field.csv", index=False)
    _metric_table(combined, ["model_name", "probe_depth_group"]).to_csv(out / "metrics_by_probe_depth_group.csv", index=False)
    _metric_table(combined, ["model_name", "field", "probe_depth_group"]).to_csv(
        out / "metrics_by_field_and_probe_depth_group.csv", index=False
    )


def write_spatial_outputs(args: argparse.Namespace) -> None:
    import geopandas as gpd
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_origin

    report_dir = args.outdir / "validation_report"
    spatial = args.outdir / "spatial"
    shp_dir = spatial / "shapefiles"
    tif_dir = spatial / "tifs"
    shp_dir.mkdir(parents=True, exist_ok=True)
    tif_dir.mkdir(parents=True, exist_ok=True)

    def make_gdf(csv_name: str) -> "gpd.GeoDataFrame":
        df = pd.read_csv(report_dir / csv_name)
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["lon"], df["lat"]), crs="EPSG:4326")

    point_metrics = make_gdf("metrics_by_point.csv")
    point_metrics.to_file(shp_dir / "llara_point_metrics.shp", driver="ESRI Shapefile")
    if (report_dir / "paired_point_error_differences.csv").exists():
        paired = make_gdf("paired_point_error_differences.csv")
        paired.to_file(shp_dir / "llara_paired_point_error_differences.shp", driver="ESRI Shapefile")
    else:
        paired = gpd.GeoDataFrame()

    def rasterize_metric(gdf, value_col: str, out_path: Path, resolution: float = 30.0) -> None:
        sub = gdf[np.isfinite(pd.to_numeric(gdf[value_col], errors="coerce"))].copy()
        if sub.empty:
            return
        sub = sub.to_crs(SOURCE_CRS)
        minx, miny, maxx, maxy = sub.total_bounds
        pad = resolution * 2
        minx -= pad
        miny -= pad
        maxx += pad
        maxy += pad
        width = max(1, int(math.ceil((maxx - minx) / resolution)))
        height = max(1, int(math.ceil((maxy - miny) / resolution)))
        transform = from_origin(minx, maxy, resolution, resolution)
        shapes = ((geom, float(value)) for geom, value in zip(sub.geometry, sub[value_col]))
        arr = rasterize(shapes, out_shape=(height, width), transform=transform, fill=np.nan, dtype="float32", all_touched=True)
        with rasterio.open(
            out_path,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype="float32",
            crs=SOURCE_CRS,
            transform=transform,
            nodata=np.nan,
            compress="deflate",
        ) as dst:
            dst.write(arr, 1)

    for model_name, sub in point_metrics.groupby("model_name"):
        safe = str(model_name).replace(" ", "_")
        for metric in ["rmse", "bias", "nse", "mae"]:
            if metric in sub.columns:
                rasterize_metric(sub, metric, tif_dir / f"llara_{safe}_{metric}.tif")
    if not paired.empty and "mean_delta_abs_error" in paired.columns:
        rasterize_metric(paired, "mean_delta_abs_error", tif_dir / "llara_model6_minus_model8_mean_delta_abs_error.tif")


def _md_table(df: pd.DataFrame, cols: list[str], max_rows: int = 20) -> str:
    show = df[cols].head(max_rows).copy()
    for col in show.columns:
        if pd.api.types.is_numeric_dtype(show[col]):
            show[col] = show[col].map(lambda x: "" if pd.isna(x) else f"{float(x):.3f}")
    lines = ["| " + " | ".join(show.columns) + " |", "| " + " | ".join(["---"] * len(show.columns)) + " |"]
    for _, row in show.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.to_list()) + " |")
    if len(df) > max_rows:
        lines.append(f"\n_Showing first {max_rows} of {len(df)} rows._")
    return "\n".join(lines)


def copy_report_figures(args: argparse.Namespace) -> None:
    fig_src = args.outdir / "validation_report" / "figures"
    fig_dst = args.report_dir / "figures"
    fig_dst.mkdir(parents=True, exist_ok=True)
    for path in fig_src.glob("*.png"):
        if not path.name.startswith("._"):
            shutil.copy2(path, fig_dst / path.name)


def write_github_report(args: argparse.Namespace, obs_summary: dict, bbox: tuple[float, float, float, float]) -> None:
    report = args.outdir / "validation_report"
    args.report_dir.mkdir(parents=True, exist_ok=True)
    copy_report_figures(args)

    overall = pd.read_csv(report / "metrics_overall.csv")
    season = pd.read_csv(report / "metrics_by_season.csv")
    field = pd.read_csv(report / "metrics_by_field.csv")
    group = pd.read_csv(report / "metrics_by_probe_depth_group.csv")
    paired = pd.read_csv(report / "paired_model_comparison_overall.csv")
    paired_season = pd.read_csv(report / "paired_model_comparison_by_season.csv")
    moisture = pd.read_csv(report / "bias_by_moisture_quantile.csv")
    terrain = pd.read_csv(report / "paired_model_comparison_by_terrain.csv")
    run_summary = json.loads((report / "run_summary.json").read_text(encoding="utf-8"))

    for table in [overall, season, field, group]:
        table["model"] = table["model_name"].map(MODEL_LABELS).fillna(table["model_name"])

    terrain_cols = ["terrain_var", "terrain_stratum", "n_matched", "mean_delta_abs_error", "rmse_a", "rmse_b", "bias_a", "bias_b"]
    model8_best = terrain.sort_values("mean_delta_abs_error", ascending=False)[terrain_cols].head(8)
    model6_best = terrain.sort_values("mean_delta_abs_error", ascending=True)[terrain_cols].head(8)

    m6 = overall[overall["model_name"] == "model6"].iloc[0]
    m8 = overall[overall["model_name"] == "model8_process"].iloc[0]
    paired_row = paired.iloc[0] if not paired.empty else None

    md = [
        "# Llara unseen validation — model6 boosted ML vs model8 process",
        "",
        "This report validates the global DownscalingMoistureModel outputs against the 32 in-situ soil-moisture probes from the Llara Landscape Rehydration Project. The validation is independent and unseen: no Llara observations are used for local calibration or spiking.",
        "",
        "The Llara CSVs contain daily depth-channel records. For comparability with the model root-zone/profile-style outputs, observations are converted to a daily profile mean for each physical probe. Replacement device records are collapsed onto the same physical probe before profile means are calculated.",
        "",
        "## Data preparation and assumptions",
        "",
        f"- Source folder: `{args.data_dir}`",
        f"- Physical probes with coordinates: {obs_summary['n_probes']}",
        f"- Profile-mean probe-date observations after filtering: {obs_summary['profile_rows']}",
        f"- Dates used: {obs_summary['date_min']} to {obs_summary['date_max']} ({obs_summary['n_dates']} dates)",
        f"- Feature/prediction bbox W/S/E/N: `{bbox}`",
        "- Coordinate source: `sm_probe_locs.csv`, interpreted as EPSG:32755 / UTM zone 55S and transformed to WGS84 lon/lat.",
        "- Profile mean policy: valid depth channels are averaged per probe/date after replacement devices are collapsed by probe/date/channel.",
        "- Sensor filtering: zero/negative values are treated as missing; values above 100% VWC are treated as physically implausible and removed.",
        f"- SMIPS lookback window used for model6 dynamic features: {args.smips_lookback_days} days.",
        "- Depth-channel assumption: 12-series probes use channels `v2`–`v12`; 16-series probes use `v2`–`v16`. The exact channel-depth metadata should be checked by a human if available.",
        "",
        "## Overall skill",
        "",
        _md_table(overall, ["model", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae", "pred_vs_obs_slope"]),
        "",
        f"Overall, model8 has RMSE {m8['rmse']:.2f}% and R² {m8['r2']:.2f}, compared with model6 boosted ML RMSE {m6['rmse']:.2f}% and R² {m6['r2']:.2f}. Bias is prediction minus observation, so negative values indicate dry bias.",
        "",
    ]
    if paired_row is not None:
        md += [
            "The paired comparison below uses the same probe-date observations for both models. Positive mean Δ absolute error means model8 has lower absolute error than model6.",
            "",
            _md_table(paired, ["n_matched", "mean_delta_abs_error", "mean_delta_abs_error_ci95_low", "mean_delta_abs_error_ci95_high", "rmse_a", "rmse_b", "fraction_model_a_better_abs_error"]),
            "",
        ]

    md += [
        "## Seasonal skill and bias",
        "",
        _md_table(season, ["model", "season", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"], max_rows=12),
        "",
        "![Observed vs predicted by season](figures/scatter_observed_vs_predicted_by_season.png)",
        "",
        "![Seasonal bias](figures/seasonal_bias_boxplot.png)",
        "",
        "![Mean observed and predicted time series](figures/timeseries_observed_vs_predicted_mean.png)",
        "",
        "![Mean residual time series](figures/timeseries_residuals_mean.png)",
        "",
        "## Field and probe-depth-group diagnostics",
        "",
        _md_table(field, ["model", "field", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "",
        _md_table(group, ["model", "probe_depth_group", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "",
        "## Dry/wet regime bias",
        "",
        _md_table(moisture.assign(model=moisture["model_name"].map(MODEL_LABELS).fillna(moisture["model_name"])), ["model", "obs_moisture_quantile", "n", "obs_mean", "pred_mean", "bias", "rmse", "mae"]),
        "",
        "## Spatial diagnostics",
        "",
        "Point-level spatial diagnostics are exported as PNG figures, shapefiles, and rasterized GeoTIFFs. The shapefiles are useful for GIS inspection; the GeoTIFFs are simple point-raster products in EPSG:32755 for quick overlay.",
        "",
        "![Model6 point RMSE](figures/point_map_model6_rmse.png)",
        "",
        "![Model8 point RMSE](figures/point_map_model8_process_rmse.png)",
        "",
        "![Paired model error difference](figures/paired_error_difference_map_model6_minus_model8_process.png)",
        "",
        "Spatial files:",
        "",
        f"- Shapefiles: `{args.outdir / 'spatial/shapefiles'}`",
        f"- GeoTIFF point rasters: `{args.outdir / 'spatial/tifs'}`",
        "",
        "## Terrain and meteorology stratification",
        "",
        "These strata use model-input style variables sampled over the Llara point-derived bbox. They are diagnostic strata, not evidence of local calibration.",
        "",
        "### Strata where model8 gains most relative to model6",
        "",
        _md_table(model8_best, terrain_cols),
        "",
        "### Strata where model6 is closest to, or better than, model8",
        "",
        _md_table(model6_best, terrain_cols),
        "",
        "![Residuals by TWI stratum](figures/terrain_residual_boxplot_twi.png)",
        "",
        "![Residuals by HLI stratum](figures/terrain_residual_boxplot_hli.png)",
        "",
        "![Residuals by soil clay stratum](figures/terrain_residual_boxplot_soil_clay.png)",
        "",
        "## Data inference notes",
        "",
        "- This validation is temporally rich: unlike the dense campaign, it spans hundreds of daily observations per probe.",
        "- It is spatially sparse relative to Tarrawarra, with 32 fixed probes across two 40 ha fields, so spatial maps should be interpreted as point-support diagnostics rather than continuous surfaces.",
        "- The observations are described by the source metadata as uncalibrated probe data. Absolute bias should therefore be interpreted carefully; correlation, seasonality, and relative wet/dry dynamics are especially informative.",
        "- The strongest scientific use here is seasonal transfer testing: do model6 boosted-ML and process-model predictions track daily/seasonal dynamics at unseen probes without local calibration?",
        "",
        "## Output files",
        "",
        f"- Model-agnostic prediction table: `{args.outdir / 'llara_model6_model8_predictions.csv'}`",
        f"- Prepared profile-mean observations: `{args.outdir / 'llara_profile_mean_observations.csv'}`",
        f"- Full validation outputs: `{args.outdir / 'validation_report'}`",
        f"- GitHub-readable report folder: `{args.report_dir}`",
        "",
        f"Validator row count: {run_summary['n_rows']}; models: {', '.join(run_summary['models'])}.",
        "",
    ]
    out = args.report_dir / "llara_unseen_model6_vs_model8_report_2026-08-11.md"
    out.write_text("\n".join(md), encoding="utf-8")


def main() -> int:
    args = parse_args()
    _add_paths_and_chdir(args.dmm_repo)
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    obs_path = args.outdir / "llara_profile_mean_observations.csv"
    summary_path = args.outdir / "llara_observation_preparation_summary.json"
    if obs_path.exists() and summary_path.exists() and not args.force:
        obs = pd.read_csv(obs_path)
        obs_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        obs, obs_summary = load_profile_mean_observations(args)
        obs.to_csv(obs_path, index=False)
        summary_path.write_text(json.dumps(obs_summary, indent=2), encoding="utf-8")

    bbox = bbox_from_points(obs.drop_duplicates("point_id"), args.bbox_padding_deg)
    (args.outdir / "llara_points_bbox.json").write_text(
        json.dumps({"west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3], "order": "west,south,east,north"}, indent=2),
        encoding="utf-8",
    )

    pred_path = args.outdir / "llara_model6_model8_predictions.csv"
    if pred_path.exists() and not args.force:
        combined = pd.read_csv(pred_path)
    else:
        features = build_feature_table(args, obs, bbox)
        model6 = predict_model6(args, obs, features)
        model8 = predict_model8(args, obs, features, bbox)
        combined = pd.concat([model6, model8], ignore_index=True, sort=False)
        combined = combined.dropna(subset=["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]).copy()
        combined.to_csv(pred_path, index=False)

    run_validation(args, pred_path)
    write_extra_metric_tables(args, combined)
    write_spatial_outputs(args)
    write_github_report(args, obs_summary, bbox)
    print(f"wrote {pred_path}")
    print(f"wrote {args.outdir / 'validation_report'}")
    print(f"wrote {args.report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
