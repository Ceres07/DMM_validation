#!/usr/bin/env python3
"""Run separate model6/model8 validation on Mulloon Rehydration Initiative probes.

This adapter keeps the MRI soil-moisture probes out of the unified dense report
for now, while reusing the same model-agnostic validation and local-spiking
figure machinery used by the dense validation pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Transformer


os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")


DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[3]
LLARA_SCRIPT_DIR = DMM_VALIDATION_ROOT / "scripts" / "sites" / "llara"
LOCAL_CALIBRATION_DIR = DMM_VALIDATION_ROOT / "scripts" / "analyses" / "local_calibration"
UNIFIED_DENSE_DIR = DMM_VALIDATION_ROOT / "scripts" / "analyses" / "unified_dense"
SRC = DMM_VALIDATION_ROOT / "src"
for path in (LLARA_SCRIPT_DIR, LOCAL_CALIBRATION_DIR, UNIFIED_DENSE_DIR, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_llara_unseen_validation as llara  # noqa: E402
import run_local_spiking_experiment as spiking  # noqa: E402
import run_unified_dense_validation as unified  # noqa: E402
from dmm_validation.reporting import markdown_table  # noqa: E402


DEFAULT_DATA_DIR = Path("/Volumes/Dmitry_work/borevitz_projects/Data/MRI_data")
DEFAULT_DMM_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel")
DEFAULT_PADDOCKTS_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/paddock-ts-local")
DEFAULT_OUTDIR = DMM_VALIDATION_ROOT / "outputs" / "mri_dense_validation"
DEFAULT_REPORT_DIR = DMM_VALIDATION_ROOT / "reports" / "sites" / "mri_dense_validation"

SOIL_LAYER = "Soil_Moisture_Probes"
HT_LAYER = "HT_Measurement_Point_Matrix"
SENSOR_RE = re.compile(r"^(?P<serial>\d+)_SM_(?P<depth_cm>\d+)cm$")

STAGE1_FIGURES = [
    (
        "figures/stage1/site_model_overall_skill.png",
        "Stage 1 overall model skill",
        "Independent MRI probe-date validation before local calibration.",
    ),
    (
        "figures/stage1/seasonal_bias_by_site_model.png",
        "Seasonal bias",
        "Mean residual by southern-hemisphere season; positive values mean overprediction.",
    ),
    (
        "figures/stage1/wetness_quantile_bias.png",
        "Dry/wet observed-state bias",
        "Bias in observed soil-moisture quartiles.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/scatter_observed_vs_predicted_by_season.png",
        "Observed vs predicted by season",
        "Point-date observations compared with model predictions by season.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/timeseries_observed_vs_predicted_mean.png",
        "Spatial-mean time series",
        "Date-wise MRI observed soil moisture compared with model6 and model8 spatial means.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/timeseries_residuals_mean.png",
        "Mean residual time series",
        "Date-wise mean prediction residuals.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/seasonal_bias_boxplot.png",
        "Seasonal residual distributions",
        "Residual spread by season and model.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/point_map_model6_rf_rmse.png",
        "Model6 point RMSE",
        "Point-level model6 RMSE at MRI probe coordinates.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/point_map_model8_process_rmse.png",
        "Model8 point RMSE",
        "Point-level model8 RMSE at MRI probe coordinates.",
    ),
    (
        "figures/stage1/site_diagnostics/mri/paired_error_difference_map_model6_rf_minus_model8_process.png",
        "Paired model error difference",
        "Mean paired absolute-error difference at MRI probe coordinates.",
    ),
    (
        "figures/stage1/quality_surfaces/mri_model6_rf_rmse_idw_surface.png",
        "Model6 interpolated RMSE surface",
        "IDW interpolation of point-level RMSE for visual diagnosis only.",
    ),
    (
        "figures/stage1/quality_surfaces/mri_model8_process_rmse_idw_surface.png",
        "Model8 interpolated RMSE surface",
        "IDW interpolation of point-level RMSE for visual diagnosis only.",
    ),
]

STAGE2_FIGURES = [
    (f"figures/stage2_local_spiking/{filename}", title, caption)
    for filename, title, caption in spiking.REPORT_FIGURES
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run separate MRI model6/model8 soil-moisture validation."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--dmm-repo", type=Path, default=DEFAULT_DMM_REPO)
    parser.add_argument("--paddockts-repo", type=Path, default=DEFAULT_PADDOCKTS_REPO)
    parser.add_argument("--paddockts-tmp-dir", type=Path, default=None)
    parser.add_argument("--paddockts-out-dir", type=Path, default=None)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--gpkg", type=Path, default=None)
    parser.add_argument("--percent-csv", type=Path, default=None)
    parser.add_argument("--metadata-pdf", type=Path, default=None)
    parser.add_argument("--model6-name", default="model6")
    parser.add_argument("--model8-name", default="model8")
    parser.add_argument("--bbox-padding-deg", type=float, default=0.01)
    parser.add_argument("--model8-step-deg", type=float, default=0.05)
    parser.add_argument("--time-zone", default="Australia/Sydney")
    parser.add_argument("--min-sm-pct", type=float, default=1e-6)
    parser.add_argument("--max-sm-pct", type=float, default=100.0)
    parser.add_argument("--min-depth-channels", type=int, default=3)
    parser.add_argument("--smips-lookback-days", type=int, default=365)
    parser.add_argument("--smips-workers", type=int, default=4)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--limit-dates", type=int, default=None)
    parser.add_argument("--bootstrap", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stage2-budgets", default="3,5,10,25%,50%,all")
    parser.add_argument("--stage2-random-reps", type=int, default=20)
    parser.add_argument("--train-date-fraction", type=float, default=0.33)
    parser.add_argument("--min-train-dates", type=int, default=3)
    parser.add_argument("--skip-stage2", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def resolve_default_paths(args: argparse.Namespace) -> None:
    if args.gpkg is None:
        args.gpkg = args.data_dir / "MulloonRehydrationInitiative.gpkg"
    if args.percent_csv is None:
        args.percent_csv = args.data_dir / "SM_combined_cleaned" / "SM(%)_combined_cleaned.csv"
    if args.metadata_pdf is None:
        args.metadata_pdf = args.data_dir / "SM_metadata.pdf"


def add_dmm_paths_and_chdir(dmm_repo: Path, paddockts_repo: Path | None = None) -> None:
    sys.path.insert(0, str(DMM_VALIDATION_ROOT / "src"))
    if paddockts_repo is not None and paddockts_repo.exists():
        sys.path.insert(0, str(paddockts_repo))
    sys.path.insert(0, str(dmm_repo))
    os.chdir(dmm_repo)


def configure_paddockts_cache(args: argparse.Namespace) -> None:
    import PaddockTS.config as paddock_config

    tmp_dir = args.paddockts_tmp_dir or (args.outdir / "paddockts_cache" / "tmp")
    out_dir = args.paddockts_out_dir or (args.outdir / "paddockts_cache" / "out")
    current = paddock_config.config
    paddock_config.config = paddock_config.Config(
        out_dir=str(out_dir),
        tmp_dir=str(tmp_dir),
        email=current.email,
        tern_api_key=current.tern_api_key,
    )
    if "PaddockTS.query" in sys.modules:
        sys.modules["PaddockTS.query"].config = paddock_config.config
    import PaddockTS.query as paddock_query

    paddock_query.config = paddock_config.config
    if not hasattr(paddock_query.Query, "terrain_path"):
        paddock_query.Query.terrain_path = property(
            lambda q: f"{q.tmp_dir}/Environmental/{q.stub}_terrain.tif"
        )
    import PaddockTS.Environmental.SLGASoils.utils as slga_utils
    from functools import lru_cache

    @lru_cache(maxsize=None)
    def list_slga_cogs(code: str, version: str) -> str:
        import requests

        url = (
            "https://data.tern.org.au/model-derived/slga/NationalMaps/"
            f"SoilAndLandscapeGrid/{code}/{version}/"
        )
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.text

    def get_cog_url_compat(attribute: str, depth: str, api_key: str | None = None) -> str:
        soils = slga_utils.slga_soils
        code = soils.attribute_codes.get(attribute)
        if code is None:
            raise KeyError(attribute)
        depth_start, depth_end = soils.depth_codes.get(depth)
        pattern = re.compile(rf'({code}_{depth_start}_{depth_end}_EV_[^"<>]*?\.tif)')
        for version in ["v2", "v1"]:
            hits = sorted(set(pattern.findall(list_slga_cogs(code, version))))
            if hits:
                return (
                    "https://data.tern.org.au/model-derived/slga/NationalMaps/"
                    f"SoilAndLandscapeGrid/{code}/{version}/{hits[-1]}"
                )
        raise RuntimeError(f"No SLGA COG found for {attribute} {depth}")

    slga_utils.get_cog_url = get_cog_url_compat
    if "emt.slga" in sys.modules:
        sys.modules["emt.slga"].get_cog_url = get_cog_url_compat


def serial_norm(value: object) -> str:
    text = str(value).strip()
    stripped = text.lstrip("0")
    return stripped if stripped else text


def read_point_layer(gpkg: Path, layer: str) -> pd.DataFrame:
    import fiona

    rows: list[dict] = []
    with fiona.open(gpkg, layer=layer) as src:
        transformer = Transformer.from_crs(src.crs, "EPSG:4326", always_xy=True)
        for feat in src:
            props = dict(feat["properties"])
            geom = feat["geometry"]
            if geom is None:
                continue
            coords = geom["coordinates"]
            lon, lat = transformer.transform(float(coords[0]), float(coords[1]))
            props["_x"] = float(coords[0])
            props["_y"] = float(coords[1])
            props["_z"] = float(coords[2]) if len(coords) > 2 else np.nan
            props["_lon"] = float(lon)
            props["_lat"] = float(lat)
            rows.append(props)
    return pd.DataFrame(rows)


def load_probe_crosswalk(gpkg: Path, sensor_serials: list[str]) -> pd.DataFrame:
    soil = read_point_layer(gpkg, SOIL_LAYER)
    ht = read_point_layer(gpkg, HT_LAYER)

    soil = soil.copy()
    soil["measurement_point_id"] = soil["Irrimax_ID"].fillna("").astype(str).str.split("/")
    soil = soil.explode("measurement_point_id")
    soil["measurement_point_id"] = soil["measurement_point_id"].astype(str).str.strip()
    soil = soil[soil["measurement_point_id"] != ""].copy()
    soil = soil.rename(
        columns={
            "id": "soil_probe_numeric_id",
            "site": "soil_probe_site",
            "Name": "probe_name",
            "piezo": "piezo",
            "Irrimax_ID": "soil_layer_irrimax_id",
            "_x": "soil_layer_easting_mga55",
            "_y": "soil_layer_northing_mga55",
            "_lon": "soil_layer_lon",
            "_lat": "soil_layer_lat",
        }
    )

    ht = ht[
        (ht["Measurement_Category_ID"].astype(str) == "SOIL")
        | (ht["Measurement_Category"].astype(str) == "Soil Moisture")
    ].copy()
    ht["serial_norm"] = ht["Serial_No"].map(serial_norm)
    requested = {serial_norm(s): s for s in sensor_serials}
    ht = ht[ht["serial_norm"].isin(requested)].copy()
    ht["sensor_serial"] = ht["serial_norm"].map(requested)
    ht = ht.rename(
        columns={
            "Serial_No": "logger_serial_metadata",
            "Measurement_Point_ID": "measurement_point_id",
            "Unique_Instrument_Identifier": "instrument_identifier",
            "Geofabric_Name": "geofabric_name",
            "Geofabric_ID": "geofabric_id",
            "Monitoring_Point_ID": "monitoring_point_id",
            "Management_Area": "management_area",
            "Property_Management_Area": "property_management_area",
            "Property_Managerment_Area_Name": "property_management_area_name",
            "Luke___Tonys_Site_Names": "local_site_name",
            "F2022_Survey_Eastings": "survey_2022_easting_mga55",
            "F2022_Survey_Northings": "survey_2022_northing_mga55",
            "F2022_Survey_Elevation_m": "survey_2022_elevation_m",
            "_lon": "ht_lon",
            "_lat": "ht_lat",
        }
    )

    keep_ht = [
        "sensor_serial",
        "serial_norm",
        "logger_serial_metadata",
        "measurement_point_id",
        "instrument_identifier",
        "geofabric_name",
        "geofabric_id",
        "monitoring_point_id",
        "management_area",
        "property_management_area",
        "property_management_area_name",
        "local_site_name",
        "survey_2022_easting_mga55",
        "survey_2022_northing_mga55",
        "survey_2022_elevation_m",
        "ht_lon",
        "ht_lat",
    ]
    keep_soil = [
        "measurement_point_id",
        "soil_probe_numeric_id",
        "soil_probe_site",
        "probe_name",
        "piezo",
        "soil_layer_irrimax_id",
        "soil_layer_easting_mga55",
        "soil_layer_northing_mga55",
        "soil_layer_lon",
        "soil_layer_lat",
    ]
    merged = ht[keep_ht].merge(soil[keep_soil], on="measurement_point_id", how="left")
    missing = sorted(set(sensor_serials) - set(merged["sensor_serial"]))
    if missing:
        raise ValueError(f"MRI sensors are missing from {HT_LAYER}: {missing}")

    merged["lon"] = merged["soil_layer_lon"].where(merged["soil_layer_lon"].notna(), merged["ht_lon"])
    merged["lat"] = merged["soil_layer_lat"].where(merged["soil_layer_lat"].notna(), merged["ht_lat"])
    missing_coords = merged[merged["lon"].isna() | merged["lat"].isna()]["sensor_serial"].tolist()
    if missing_coords:
        raise ValueError(f"MRI sensors are missing usable coordinates: {missing_coords}")

    merged["point_id"] = "MRI_" + merged["sensor_serial"].astype(str)
    merged["probe_id"] = (
        merged["probe_name"].fillna(merged["piezo"]).fillna(merged["soil_probe_site"]).fillna(merged["point_id"])
    )
    merged["field"] = (
        merged["property_management_area_name"]
        .fillna(merged["property_management_area"])
        .fillna(merged["management_area"])
        .fillna("MRI")
    )
    merged["probe_depth_group"] = "mri_profile"
    return merged.sort_values("sensor_serial").reset_index(drop=True)


def parse_sensor_columns(columns: list[str]) -> pd.DataFrame:
    rows = []
    for col in columns:
        match = SENSOR_RE.match(col)
        if match:
            rows.append(
                {
                    "column": col,
                    "sensor_serial": match.group("serial"),
                    "depth_cm": int(match.group("depth_cm")),
                }
            )
    return pd.DataFrame(rows)


def load_daily_profile_observations(args: argparse.Namespace) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw = pd.read_csv(args.percent_csv)
    sensor_cols = parse_sensor_columns(list(raw.columns))
    if sensor_cols.empty:
        raise ValueError(f"No MRI sensor-depth columns found in {args.percent_csv}")

    timestamps = pd.to_datetime(raw["Date Time"], errors="coerce", utc=True)
    dates = pd.Series(pd.NA, index=raw.index, dtype="object")
    ok_time = timestamps.notna()
    dates.loc[ok_time] = timestamps.loc[ok_time].dt.tz_convert(args.time_zone).dt.date.astype(str)

    if args.start:
        dates = dates.where(dates >= args.start)
    if args.end:
        dates = dates.where(dates <= args.end)

    depth_rows: list[pd.DataFrame] = []
    finite_cells = 0
    valid_cells = 0
    low_or_zero_cells = 0
    high_cells = 0
    for col, sensor_serial, depth_cm in sensor_cols[["column", "sensor_serial", "depth_cm"]].itertuples(index=False):
        values = pd.to_numeric(raw[col], errors="coerce")
        finite = values.notna()
        finite_cells += int(finite.sum())
        low_or_zero_cells += int((finite & (values <= args.min_sm_pct)).sum())
        high_cells += int((finite & (values > args.max_sm_pct)).sum())
        valid = finite & dates.notna() & values.between(args.min_sm_pct, args.max_sm_pct)
        valid_cells += int(valid.sum())
        if not valid.any():
            continue
        tmp = pd.DataFrame({"date": dates.loc[valid].to_numpy(), "obs_sm_pct": values.loc[valid].to_numpy(dtype=float)})
        daily = (
            tmp.groupby("date", as_index=False)
            .agg(depth_mean_sm_pct=("obs_sm_pct", "mean"), n_time_records=("obs_sm_pct", "size"))
        )
        daily["sensor_serial"] = sensor_serial
        daily["depth_cm"] = depth_cm
        depth_rows.append(daily)

    if not depth_rows:
        raise ValueError("No valid MRI soil-moisture observations remain after filtering")

    daily_depth = pd.concat(depth_rows, ignore_index=True)
    profile_before = (
        daily_depth.groupby(["sensor_serial", "date"], as_index=False)
        .agg(
            obs_sm_pct=("depth_mean_sm_pct", "mean"),
            obs_depth_sd=("depth_mean_sm_pct", "std"),
            obs_depth_min=("depth_mean_sm_pct", "min"),
            obs_depth_max=("depth_mean_sm_pct", "max"),
            n_depth_channels=("depth_cm", "nunique"),
            depth_cm_min=("depth_cm", "min"),
            depth_cm_max=("depth_cm", "max"),
            n_time_records=("n_time_records", "sum"),
        )
    )
    profile_before["obs_depth_sd"] = profile_before["obs_depth_sd"].fillna(0.0)
    profile = profile_before[profile_before["n_depth_channels"] >= args.min_depth_channels].copy()
    if args.limit_dates:
        keep_dates = sorted(profile["date"].unique())[: args.limit_dates]
        profile = profile[profile["date"].isin(keep_dates)].copy()
        daily_depth = daily_depth[daily_depth["date"].isin(keep_dates)].copy()

    crosswalk = load_probe_crosswalk(args.gpkg, sorted(sensor_cols["sensor_serial"].unique()))
    profile = profile.merge(crosswalk, on="sensor_serial", how="left")
    missing_coords = profile[profile["lon"].isna() | profile["lat"].isna()]["sensor_serial"].unique()
    if len(missing_coords):
        raise ValueError(f"Missing MRI coordinates after merge: {sorted(missing_coords)}")

    profile["model_name"] = "observation_only"
    profile["pred_sm_pct"] = np.nan
    profile = profile.sort_values(["point_id", "date"]).reset_index(drop=True)
    columns = [
        "model_name",
        "point_id",
        "date",
        "lon",
        "lat",
        "obs_sm_pct",
        "pred_sm_pct",
        "sensor_serial",
        "logger_serial_metadata",
        "probe_id",
        "probe_name",
        "soil_probe_site",
        "piezo",
        "measurement_point_id",
        "soil_layer_irrimax_id",
        "field",
        "probe_depth_group",
        "property_management_area",
        "property_management_area_name",
        "management_area",
        "local_site_name",
        "geofabric_name",
        "geofabric_id",
        "monitoring_point_id",
        "soil_layer_easting_mga55",
        "soil_layer_northing_mga55",
        "soil_layer_lon",
        "soil_layer_lat",
        "ht_lon",
        "ht_lat",
        "survey_2022_easting_mga55",
        "survey_2022_northing_mga55",
        "survey_2022_elevation_m",
        "obs_depth_sd",
        "obs_depth_min",
        "obs_depth_max",
        "n_depth_channels",
        "depth_cm_min",
        "depth_cm_max",
        "n_time_records",
    ]
    profile = profile[[c for c in columns if c in profile.columns]]

    summary = {
        "source_percent_csv": str(args.percent_csv),
        "source_gpkg": str(args.gpkg),
        "source_soil_moisture_probe_layer": SOIL_LAYER,
        "source_serial_crosswalk_layer": HT_LAYER,
        "metadata_pdf": str(args.metadata_pdf),
        "source_rows": int(len(raw)),
        "sensor_depth_columns": int(len(sensor_cols)),
        "sensors_in_csv": int(sensor_cols["sensor_serial"].nunique()),
        "finite_sensor_depth_cells": int(finite_cells),
        "valid_sensor_depth_cells": int(valid_cells),
        "low_or_zero_cells_filtered": int(low_or_zero_cells),
        "above_max_cells_filtered": int(high_cells),
        "daily_sensor_depth_rows": int(len(daily_depth)),
        "daily_profile_rows_before_min_depth_filter": int(len(profile_before)),
        "daily_profile_rows": int(len(profile)),
        "n_probes": int(profile["point_id"].nunique()),
        "n_dates": int(profile["date"].nunique()),
        "date_min": str(profile["date"].min()),
        "date_max": str(profile["date"].max()),
        "time_zone_for_daily_dates": args.time_zone,
        "min_depth_channels": int(args.min_depth_channels),
        "value_filter": f"{args.min_sm_pct} < soil_moisture_percent <= {args.max_sm_pct}",
        "profile_mean_policy": "daily mean per depth channel, then unweighted profile mean across valid depth channels",
        "coordinate_policy": "lon/lat from Soil_Moisture_Probes GPKG layer; HT_Measurement_Point_Matrix used only for logger serial to Irrimax_ID crosswalk",
    }
    return profile, crosswalk, summary


def bbox_from_points(points: pd.DataFrame, padding_deg: float) -> tuple[float, float, float, float]:
    return (
        float(points["lon"].min() - padding_deg),
        float(points["lat"].min() - padding_deg),
        float(points["lon"].max() + padding_deg),
        float(points["lat"].max() + padding_deg),
    )


def build_predictions(
    args: argparse.Namespace,
    obs: pd.DataFrame,
    bbox: tuple[float, float, float, float],
) -> pd.DataFrame:
    pred_path = args.outdir / "mri_model6_model8_predictions.csv"
    if pred_path.exists() and not args.force:
        return pd.read_csv(pred_path)

    features = llara.build_feature_table(args, obs, bbox, dataset_prefix="mri")
    model6 = llara.predict_model6(
        args,
        obs,
        features,
        output_name="mri_model6_model_agnostic_predictions.csv",
        model_label="model6_rf",
    )
    model8 = llara.predict_model8(
        args,
        obs,
        features,
        bbox,
        output_name="mri_model8_process_model_agnostic_predictions.csv",
        model_label="model8_process",
    )
    combined_all = pd.concat([model6, model8], ignore_index=True, sort=False)
    combined_all.to_csv(args.outdir / "mri_model6_model8_predictions_all_rows.csv", index=False)
    valid = combined_all.dropna(
        subset=["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]
    ).copy()
    valid.to_csv(pred_path, index=False)
    return valid


def run_stage1(args: argparse.Namespace, pred_path: Path) -> dict[str, object]:
    df = spiking.load_site("MRI", pred_path)
    unified.spiking.SITE_PATHS["MRI"] = pred_path
    return unified.run_stage1(
        {"MRI": df},
        args.outdir / "stage1_independent_validation",
        args.report_dir / "figures",
        terrain_cols="auto",
        terrain_quantiles=3,
        bootstrap=args.bootstrap,
        seed=args.seed,
        skip_galleries=True,
    )


def run_stage2(args: argparse.Namespace, pred_path: Path) -> dict[str, pd.DataFrame]:
    outdir = args.outdir / "stage2_local_spiking"
    report_figdir = args.report_dir / "figures" / "stage2_local_spiking"
    outdir.mkdir(parents=True, exist_ok=True)
    report_figdir.mkdir(parents=True, exist_ok=True)

    budget_specs = spiking.parse_budget_specs(args.stage2_budgets)
    rng = np.random.default_rng(args.seed)
    site = "MRI"
    df = spiking.load_site(site, pred_path)
    dates = sorted(df["date"].unique())
    train_dates, future_dates = spiking.split_dates(dates, args.train_date_fraction, args.min_train_dates)
    point_summary = spiking.site_point_summary(df, train_dates, future_dates)
    point_summary["site"] = site
    n_eligible = int(point_summary["eligible"].sum())

    site_summaries = pd.DataFrame(
        [
            {
                "site": site,
                "path": str(pred_path),
                "rows": int(len(df)),
                "models": ",".join(sorted(df["base_model"].unique())),
                "points": int(df["point_id"].nunique()),
                "eligible_points_train_and_future": n_eligible,
                "dates": int(len(dates)),
                "date_min": min(dates),
                "date_max": max(dates),
                "train_dates": int(len(train_dates)),
                "future_dates": int(len(future_dates)),
                "seasons": ",".join(sorted(map(str, df["season"].dropna().unique()))),
            }
        ]
    )

    resolved_budgets: list[tuple[str, int]] = []
    seen_budgets: set[tuple[str, int]] = set()
    for spec in budget_specs:
        budget_label, budget = spiking.resolve_budget(spec, n_eligible)
        if budget <= 0:
            continue
        key = (budget_label, budget)
        if key not in seen_budgets:
            resolved_budgets.append(key)
            seen_budgets.add(key)

    selected_rows = []
    metrics_rows: list[dict] = []
    season_rows: list[dict] = []
    representative_frames: list[pd.DataFrame] = []
    fit_rows: list[dict] = []
    for budget_label, budget in resolved_budgets:
        for strategy in spiking.SELECTION_STRATEGIES:
            reps = args.stage2_random_reps if strategy == "random" and budget < n_eligible else 1
            for rep in range(reps):
                selected = spiking.select_points(point_summary, strategy, budget, rng)
                if not selected:
                    continue
                selected_rows.append(
                    {
                        "site": site,
                        "selection_strategy": strategy,
                        "budget_label": budget_label,
                        "calibration_points": budget,
                        "replicate": rep,
                        "selected_points": ";".join(selected),
                    }
                )
                for block in spiking.BLOCKS:
                    representative = False
                    m_rows, s_rows, p_frames, f_meta = spiking.evaluate_design(
                        df,
                        site,
                        selected,
                        train_dates,
                        future_dates,
                        block,
                        strategy,
                        budget_label,
                        budget,
                        rep,
                        representative,
                    )
                    metrics_rows.extend(m_rows)
                    season_rows.extend(s_rows)
                    representative_frames.extend(p_frames)
                    fit_rows.extend(f_meta)

    selected_points = pd.DataFrame(selected_rows)
    metrics = pd.DataFrame(metrics_rows)
    season_metrics = pd.DataFrame(season_rows)
    fit_metadata = pd.DataFrame(fit_rows)
    baseline = spiking.baseline_metrics({site: df})
    summary = spiking.summarize_metrics(metrics) if not metrics.empty else pd.DataFrame()
    responsiveness = spiking.process_vs_statistical(metrics) if not metrics.empty else pd.DataFrame()

    site_summaries.to_csv(outdir / "site_summaries.csv", index=False)
    point_summary.to_csv(outdir / "point_selection_summaries.csv", index=False)
    selected_points.to_csv(outdir / "selected_calibration_points.csv", index=False)
    metrics.to_csv(outdir / "metrics_by_design.csv", index=False)
    season_metrics.to_csv(outdir / "metrics_by_design_season.csv", index=False)
    fit_metadata.to_csv(outdir / "calibration_fit_metadata.csv", index=False)
    baseline.to_csv(outdir / "global_baseline_metrics_by_site.csv", index=False)
    summary.to_csv(outdir / "local_calibration_summary.csv", index=False)
    responsiveness.to_csv(outdir / "process_vs_statistical_responsiveness.csv", index=False)
    if representative_frames:
        pd.concat(representative_frames, ignore_index=True, sort=False).to_csv(
            outdir / "representative_one_sensor_spatiotemporal_predictions.csv",
            index=False,
        )

    if not summary.empty:
        spiking.make_figures(outdir, baseline, summary, responsiveness)
        spiking.copy_report_figures(outdir, report_figdir)

    run_summary = {
        "outdir": str(outdir),
        "report_figdir": str(report_figdir),
        "prediction_path": str(pred_path),
        "budget_specs": budget_specs,
        "resolved_budgets": [{"label": label, "points": points} for label, points in resolved_budgets],
        "random_reps": args.stage2_random_reps,
        "seed": args.seed,
        "blocks": spiking.BLOCKS,
        "methods": spiking.METHODS,
        "selection_strategies": spiking.SELECTION_STRATEGIES,
    }
    (outdir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return {
        "site_summaries": site_summaries,
        "point_summaries": point_summary,
        "selected_points": selected_points,
        "metrics": metrics,
        "season_metrics": season_metrics,
        "fit_metadata": fit_metadata,
        "baseline": baseline,
        "summary": summary,
        "responsiveness": responsiveness,
    }


def read_csv_or_empty(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if path.exists() else pd.DataFrame()


def report_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    return df[[c for c in cols if c in df.columns]].copy()


def figure_blocks(report_dir: Path, specs: list[tuple[str, str, str]]) -> str:
    blocks = []
    for rel, title, caption in specs:
        path = report_dir / rel
        if not path.exists():
            continue
        blocks.extend([f"### {title}", "", f"![{title}]({Path(rel).as_posix()})", "", caption, ""])
    return "\n".join(blocks).strip()


def write_mri_report(
    args: argparse.Namespace,
    obs_summary: dict,
    bbox: tuple[float, float, float, float],
    stage2: dict[str, pd.DataFrame] | None,
) -> None:
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stage1_dir = args.outdir / "stage1_independent_validation"
    stage2_dir = args.outdir / "stage2_local_spiking"

    inventory = read_csv_or_empty(stage1_dir / "site_inventory.csv")
    overall = read_csv_or_empty(stage1_dir / "metrics_overall_by_site_model.csv")
    seasonal = read_csv_or_empty(stage1_dir / "metrics_by_site_model_season.csv")
    wetness = read_csv_or_empty(stage1_dir / "bias_by_observed_wetness_quantile.csv")
    paired = read_csv_or_empty(stage1_dir / "paired_model_comparison_overall.csv")
    notable_terrain = read_csv_or_empty(stage1_dir / "notable_terrain_error_strata.csv")
    if not notable_terrain.empty:
        notable_terrain = notable_terrain.groupby(["site", "base_model"], as_index=False, observed=True).head(8)

    stage2_summary = (
        stage2["summary"] if stage2 is not None else read_csv_or_empty(stage2_dir / "local_calibration_summary.csv")
    )
    stage2_resp = (
        stage2["responsiveness"]
        if stage2 is not None
        else read_csv_or_empty(stage2_dir / "process_vs_statistical_responsiveness.csv")
    )
    stage2_baseline = (
        stage2["baseline"] if stage2 is not None else read_csv_or_empty(stage2_dir / "global_baseline_metrics_by_site.csv")
    )
    target = unified.target_nse_table(stage2_summary, threshold=0.4) if not stage2_summary.empty else pd.DataFrame()
    best = unified.best_stage2_table(stage2_summary) if not stage2_summary.empty else pd.DataFrame()

    overall_report = report_columns(
        overall,
        ["site", "base_model", "n", "nse", "pearson_r", "rmse", "ubrmse", "bias", "mae"],
    )
    seasonal_report = report_columns(
        seasonal,
        ["site", "base_model", "season", "n", "nse", "pearson_r", "rmse", "ubrmse", "bias", "mae"],
    )
    wetness_report = report_columns(
        wetness,
        ["site", "base_model", "obs_moisture_quantile", "n", "obs_mean", "pred_mean", "rmse", "ubrmse", "bias", "mae"],
    )
    paired_report = report_columns(
        paired,
        [
            "site",
            "model_a",
            "model_b",
            "n_matched",
            "mean_delta_abs_error",
            "rmse_a",
            "rmse_b",
            "bias_a",
            "bias_b",
        ],
    )
    terrain_report = report_columns(
        notable_terrain,
        [
            "site",
            "base_model",
            "terrain_var",
            "n_strata",
            "nse_min",
            "nse_max",
            "rmse_min",
            "rmse_max",
            "bias_min",
            "bias_max",
        ],
    )
    baseline_report = report_columns(
        stage2_baseline,
        ["site", "base_model", "model_track", "n", "nse", "pearson_r", "rmse", "ubrmse", "bias"],
    )
    resp_core = pd.DataFrame()
    if not stage2_resp.empty and {"block", "selection_strategy"}.issubset(stage2_resp.columns):
        resp_core = stage2_resp[
            (stage2_resp["block"] == "spatiotemporal_block")
            & (stage2_resp["selection_strategy"] == "random")
        ].copy()
    resp_report = report_columns(
        resp_core,
        [
            "site",
            "budget_label",
            "calibration_points",
            "method",
            "statistical_rmse_gain_median",
            "process_rmse_gain_median",
            "process_minus_statistical_rmse_gain_median",
            "fraction_process_wins",
            "n_replicates",
        ],
    )

    stage1_figures = figure_blocks(args.report_dir, STAGE1_FIGURES)
    stage2_figures = figure_blocks(args.report_dir, STAGE2_FIGURES)
    if not stage2_figures:
        stage2_figures = "_Stage 2 was skipped or did not produce figure-ready outputs._"

    body = f"""# MRI separate dense validation - model6 RF vs model8 process

This report keeps the Mulloon Rehydration Initiative soil-moisture probes
separate from `reports/analyses/unified_dense_validation` while using the same
model-agnostic validation and local-spiking figure pipeline.

## Data preparation

{markdown_table(inventory, max_rows=10)}

Preparation details:

- Source percent CSV: `{args.percent_csv}`
- Source GPKG: `{args.gpkg}`
- Coordinate and label layer: `{SOIL_LAYER}`
- Logger serial crosswalk layer: `{HT_LAYER}`
- Metadata PDF reference: `{args.metadata_pdf}`
- Daily profile observations: {obs_summary["daily_profile_rows"]} rows from {obs_summary["n_probes"]} probes
- Dates used: {obs_summary["date_min"]} to {obs_summary["date_max"]} ({obs_summary["n_dates"]} dates)
- Feature/prediction bbox W/S/E/N: `{bbox}`
- Daily date policy: UTC timestamps converted to `{args.time_zone}` before daily aggregation
- Observation filter: `{obs_summary["value_filter"]}`
- Profile mean policy: {obs_summary["profile_mean_policy"]}
- Coordinate policy: {obs_summary["coordinate_policy"]}

Filtered cells: {obs_summary["low_or_zero_cells_filtered"]} low/zero and
{obs_summary["above_max_cells_filtered"]} above {args.max_sm_pct}% VWC.

## Stage 1 - independent validation

### Overall skill

{markdown_table(overall_report, max_rows=20)}

### Seasonal skill

{markdown_table(seasonal_report, max_rows=40)}

### Dry/wet observed-state bias

{markdown_table(wetness_report, max_rows=40)}

### Paired model comparison

Positive `mean_delta_abs_error` means model8 has lower absolute error than
model6 on matched probe-date observations.

{markdown_table(paired_report, max_rows=20)}

### Most notable terrain/model-input strata

{markdown_table(terrain_report, max_rows=40)}

## Stage 2 - local-spiking sensitivity

Stage 2 uses the same sparse local-calibration design as the unified dense
validation, but only on MRI probes. The strict `spatiotemporal_block` remains
the main transfer test.

### Uncalibrated baseline

{markdown_table(baseline_report, max_rows=20)}

### NSE target summary

{markdown_table(target, max_rows=20)}

### Best strict-block local calibration design

{markdown_table(best, max_rows=20)}

### Process-vs-statistical response under random placement

{markdown_table(resp_report, max_rows=60)}

## Stage 1 Figures

{stage1_figures}

## Stage 2 Figures

{stage2_figures}

## Output index

- Prepared observations: `{args.outdir / "mri_profile_mean_observations.csv"}`
- Probe coordinate crosswalk: `{args.outdir / "mri_probe_coordinate_crosswalk.csv"}`
- Model input features: `{args.outdir / "mri_model_input_features.csv"}`
- Model-agnostic predictions: `{args.outdir / "mri_model6_model8_predictions.csv"}`
- Stage 1 outputs: `{stage1_dir}`
- Stage 2 outputs: `{stage2_dir}`
- Report figures: `{args.report_dir / "figures"}`

## Interpretation guardrails

- These MRI outputs are intentionally not merged into the unified dense report
  yet.
- Interpolated quality surfaces are diagnostic visualizations of point metrics,
  not gridded model products.
- The MRI source values are treated as volumetric soil water content percent.
  Values above 100% and zero/negative placeholders are filtered before daily
  profile means are computed.
"""
    report_path = args.report_dir / "mri_dense_validation_report.md"
    report_path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    resolve_default_paths(args)
    add_dmm_paths_and_chdir(args.dmm_repo, args.paddockts_repo)
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)
    configure_paddockts_cache(args)

    obs_path = args.outdir / "mri_profile_mean_observations.csv"
    crosswalk_path = args.outdir / "mri_probe_coordinate_crosswalk.csv"
    summary_path = args.outdir / "mri_observation_preparation_summary.json"
    if obs_path.exists() and crosswalk_path.exists() and summary_path.exists() and not args.force:
        obs = pd.read_csv(obs_path)
        obs_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    else:
        obs, crosswalk, obs_summary = load_daily_profile_observations(args)
        obs.to_csv(obs_path, index=False)
        crosswalk.to_csv(crosswalk_path, index=False)
        summary_path.write_text(json.dumps(obs_summary, indent=2), encoding="utf-8")

    bbox = bbox_from_points(obs.drop_duplicates("point_id"), args.bbox_padding_deg)
    (args.outdir / "mri_points_bbox.json").write_text(
        json.dumps(
            {"west": bbox[0], "south": bbox[1], "east": bbox[2], "north": bbox[3], "order": "west,south,east,north"},
            indent=2,
        ),
        encoding="utf-8",
    )

    pred = build_predictions(args, obs, bbox)
    pred_path = args.outdir / "mri_model6_model8_predictions.csv"
    if pred.empty:
        raise SystemExit("No finite MRI model predictions were produced; validation figures cannot be generated.")

    print("running MRI Stage 1 independent validation ...", flush=True)
    run_stage1(args, pred_path)

    stage2 = None
    if args.skip_stage2:
        print("skipping MRI Stage 2 local spiking by request", flush=True)
    else:
        print("running MRI Stage 2 local-spiking calibration ...", flush=True)
        stage2 = run_stage2(args, pred_path)

    write_mri_report(args, obs_summary, bbox, stage2)

    run_summary = {
        "outdir": str(args.outdir),
        "report_dir": str(args.report_dir),
        "prepared_observations": str(obs_path),
        "coordinate_crosswalk": str(crosswalk_path),
        "predictions": str(pred_path),
        "stage1_outdir": str(args.outdir / "stage1_independent_validation"),
        "stage2_outdir": str(args.outdir / "stage2_local_spiking"),
        "report": str(args.report_dir / "mri_dense_validation_report.md"),
    }
    (args.outdir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print(f"wrote MRI report: {args.report_dir / 'mri_dense_validation_report.md'}", flush=True)
    print(f"wrote MRI outputs: {args.outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
