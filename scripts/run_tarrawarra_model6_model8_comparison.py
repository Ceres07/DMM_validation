#!/usr/bin/env python3
"""Run model6/model8 predictions over converted Tarrawarra observations.

This is intentionally a script-side adapter: Tarrawarra coordinate conversion,
DownscalingMoistureModel imports, and cached map generation stay out of the
universal `dmm_validation` package.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd


os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
# The current paddockts environment can raise a pysheds/numba caching error when
# importing terrain utilities. Disabling JIT avoids that import-time cache path.
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")

DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATIONS = DMM_VALIDATION_ROOT / "outputs/tarrawarra_conversion/tarrawarra_dmm_observation_template.csv"
DEFAULT_BBOX = DMM_VALIDATION_ROOT / "outputs/tarrawarra_conversion/tarrawarra_points_bbox.json"
DEFAULT_OUTDIR = DMM_VALIDATION_ROOT / "outputs/tarrawarra_model6_vs_model8"
DEFAULT_DMM_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", type=Path, default=DEFAULT_OBSERVATIONS)
    parser.add_argument("--bbox-json", type=Path, default=DEFAULT_BBOX)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--dmm-repo", type=Path, default=DEFAULT_DMM_REPO)
    parser.add_argument("--model6-name", default="model6")
    parser.add_argument("--model8-name", default="model8")
    parser.add_argument("--model8-step-deg", type=float, default=0.1)
    parser.add_argument("--bootstrap", type=int, default=1000)
    parser.add_argument("--limit-dates", type=int, default=None, help="Debug helper: only run the first N dates.")
    parser.add_argument("--force", action="store_true", help="Ignore cached model prediction tables.")
    parser.add_argument("--no-feature-sampling", action="store_true")
    parser.add_argument("--no-validation", action="store_true")
    parser.add_argument("--no-map-tifs", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def _repo_imports(args: argparse.Namespace) -> None:
    sys.path.insert(0, str(DMM_VALIDATION_ROOT / "src"))
    sys.path.insert(0, str(args.dmm_repo))


def _read_bbox(path: Path) -> tuple[float, float, float, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return (float(payload["west"]), float(payload["south"]), float(payload["east"]), float(payload["north"]))


def _tag(*parts: object) -> str:
    return "_".join(str(p) for p in parts).replace(".", "p").replace("-", "m").replace("/", "_")


def _sample_dataarray(da, rows: pd.DataFrame) -> np.ndarray:
    from emt.covariates import sample_points

    vals: list[float] = []
    for row in rows.itertuples(index=False):
        try:
            val = sample_points(da, float(row.lon), float(row.lat)).values
            vals.append(float(np.asarray(val)))
        except Exception:
            vals.append(np.nan)
    return np.asarray(vals, dtype=float)


def _sample_dataset(ds, rows: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = pd.DataFrame(index=rows.index)
    for col in columns:
        out[col] = _sample_dataarray(ds[col], rows)
    return out


def _write_map(ds, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ds["sm_pred"].rio.to_raster(path)


def _predict_model_maps(
    obs: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    outdir: Path,
    model_label: str,
    model_name: str,
    model_kind: str,
    model8_step_deg: float,
    write_map_tifs: bool,
    force: bool,
    quiet: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pred_path = outdir / f"{model_label}_model_agnostic_predictions.csv"
    log_path = outdir / f"{model_label}_prediction_log.csv"
    if pred_path.exists() and log_path.exists() and not force:
        return pd.read_csv(pred_path), pd.read_csv(log_path)

    if model_kind == "model6":
        from emt.predict import predict as predict_map
    elif model_kind == "model8":
        from emt.model8.predict import predict_map
    else:
        raise ValueError(f"unknown model kind: {model_kind}")

    out = obs.copy()
    out["model_name"] = model_label
    out["pred_sm_pct"] = np.nan
    logs: list[dict] = []
    dates = sorted(out["date"].unique())

    for i, day in enumerate(dates, start=1):
        if not quiet:
            print(f"{model_label} map {i}/{len(dates)}: {day}", flush=True)
        idx = out["date"] == day
        sub = out.loc[idx]
        try:
            if model_kind == "model6":
                ds = predict_map(
                    bbox,
                    day,
                    model_name=model_name,
                    save=False,
                    plot=False,
                    verbose=not quiet,
                )
            else:
                ds = predict_map(
                    bbox,
                    day,
                    model_name=model_name,
                    step_deg=model8_step_deg,
                    save=False,
                    plot=False,
                    verbose=not quiet,
                )
            out.loc[idx, "pred_sm_pct"] = _sample_dataarray(ds["sm_pred"], sub)
            if write_map_tifs:
                _write_map(ds, outdir / "maps" / f"{model_label}_{day}.tif")
            logs.append(
                {
                    "model_name": model_label,
                    "date": day,
                    "status": "ok",
                    "n_rows": int(idx.sum()),
                    "n_predicted": int(np.isfinite(out.loc[idx, "pred_sm_pct"]).sum()),
                    "message": "",
                }
            )
        except Exception as e:  # noqa: BLE001 - preserve per-date failures
            logs.append(
                {
                    "model_name": model_label,
                    "date": day,
                    "status": "failed",
                    "n_rows": int(idx.sum()),
                    "n_predicted": 0,
                    "message": f"{type(e).__name__}: {e}",
                }
            )
            print(f"{model_label} {day} failed: {type(e).__name__}: {e}", flush=True)

    log = pd.DataFrame(logs)
    out.to_csv(pred_path, index=False)
    log.to_csv(log_path, index=False)
    return out, log


def _attach_model_input_samples(
    obs: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    outdir: Path,
    force: bool,
    quiet: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    feature_path = outdir / "tarrawarra_sampled_model_inputs.csv"
    log_path = outdir / "feature_sampling_log.csv"
    if feature_path.exists() and log_path.exists() and not force:
        features = pd.read_csv(feature_path)
        out = obs.copy()
        if len(features) == len(out):
            for col in [c for c in features.columns if c not in out.columns and c != "_tarrawarra_row_id"]:
                out[col] = features[col].values
            return out, pd.read_csv(log_path)
        leading = ["point_id", "date"]
        merge_cols = leading + [c for c in features.columns if c not in obs.columns or c in leading]
        return out.merge(features[merge_cols], on=leading, how="left"), pd.read_csv(log_path)

    from PaddockTS.query import Query
    from emt.antecedent import ANTECEDENT_VARS, antecedent_day_layers, antecedent_grid
    from emt.covariates import TERRAIN_VARS, terrain_covariates
    from emt.slga import SOIL_VARS, soil_covariates

    logs: list[dict] = []
    row_id_col = "_tarrawarra_row_id"
    work = obs.copy()
    work[row_id_col] = np.arange(len(work), dtype=int)
    features = work[[row_id_col, "point_id", "date", "lon", "lat"]].copy()
    unique_points = obs.drop_duplicates("point_id")[["point_id", "lon", "lat"]].reset_index(drop=True)
    min_day = _date.fromisoformat(str(obs["date"].min()))
    max_day = _date.fromisoformat(str(obs["date"].max()))

    q = Query(
        bbox=list(bbox),
        start=min_day,
        end=max_day,
        stub=_tag("tarrawarra_features", *[f"{v:.4f}" for v in bbox], min_day, max_day),
    )

    try:
        if not quiet:
            print("sampling terrain model inputs from point bbox ...", flush=True)
        terr = terrain_covariates(q)
        sampled = _sample_dataset(terr, unique_points, list(TERRAIN_VARS))
        sampled.insert(0, "point_id", unique_points["point_id"].values)
        features = features.merge(sampled, on="point_id", how="left")
        logs.append({"feature_group": "terrain", "status": "ok", "message": ""})
    except Exception as e:  # noqa: BLE001
        logs.append({"feature_group": "terrain", "status": "failed", "message": f"{type(e).__name__}: {e}"})
        print(f"terrain feature sampling failed: {type(e).__name__}: {e}", flush=True)

    try:
        if not quiet:
            print("sampling SLGA soil model inputs from point bbox ...", flush=True)
        soil = soil_covariates(q)
        sampled = _sample_dataset(soil, unique_points, list(SOIL_VARS))
        sampled.insert(0, "point_id", unique_points["point_id"].values)
        features = features.merge(sampled, on="point_id", how="left")
        logs.append({"feature_group": "soil", "status": "ok", "message": ""})
    except Exception as e:  # noqa: BLE001
        logs.append({"feature_group": "soil", "status": "failed", "message": f"{type(e).__name__}: {e}"})
        print(f"soil feature sampling failed: {type(e).__name__}: {e}", flush=True)

    try:
        if not quiet:
            print("sampling SILO antecedent model inputs from point bbox ...", flush=True)
        ante = antecedent_grid(q, min_day, max_day, verbose=not quiet)
        dynamic_rows: list[pd.DataFrame] = []
        for day in sorted(features["date"].unique()):
            idx = features["date"] == day
            sub = features.loc[idx, [row_id_col, "point_id", "date", "lon", "lat"]]
            layers = antecedent_day_layers(ante, day)
            sampled = pd.DataFrame(index=sub.index)
            for var in ANTECEDENT_VARS:
                sampled[var] = _sample_dataarray(layers[var], sub)
            sampled.insert(0, row_id_col, sub[row_id_col].values)
            dynamic_rows.append(sampled)
        dynamic = pd.concat(dynamic_rows, ignore_index=True)
        features = features.merge(dynamic, on=row_id_col, how="left")
        logs.append({"feature_group": "antecedent_weather", "status": "ok", "message": ""})
    except Exception as e:  # noqa: BLE001
        logs.append({"feature_group": "antecedent_weather", "status": "failed", "message": f"{type(e).__name__}: {e}"})
        print(f"antecedent feature sampling failed: {type(e).__name__}: {e}", flush=True)

    # SMIPS is model6-specific and may not cover historical Tarrawarra dates.
    try:
        if not quiet:
            print("sampling SMIPS model inputs from point bbox ...", flush=True)
        import xarray as xr
        from emt.smips import smips_cube

        start = (pd.Timestamp(min_day) - pd.Timedelta(days=365)).date()
        cube = smips_cube(start, max_day, bbox).sortby("time")
        smips_rows: list[pd.DataFrame] = []
        for day in sorted(features["date"].unique()):
            ts = pd.Timestamp(day)
            upto = cube.sel(time=slice(None, ts))
            if upto.sizes.get("time", 0) == 0:
                continue
            today = upto.isel(time=-1)
            layers = {
                "smips_totalbucket": today,
                "smips_7d": upto.isel(time=slice(-7, None)).mean("time"),
                "smips_30d": upto.isel(time=slice(-30, None)).mean("time"),
                "smips_365d": upto.isel(time=slice(-365, None)).mean("time"),
            }
            layers["smips_anom"] = layers["smips_totalbucket"] - layers["smips_365d"]
            layers = {name: da.rio.write_crs(4326) if da.rio.crs is None else da for name, da in layers.items()}
            idx = features["date"] == day
            sub = features.loc[idx, [row_id_col, "point_id", "date", "lon", "lat"]]
            sampled = pd.DataFrame(index=sub.index)
            for var, da in layers.items():
                sampled[var] = _sample_dataarray(da, sub)
            sampled.insert(0, row_id_col, sub[row_id_col].values)
            smips_rows.append(sampled)
        if smips_rows:
            smips = pd.concat(smips_rows, ignore_index=True)
            features = features.merge(smips, on=row_id_col, how="left")
        logs.append({"feature_group": "smips", "status": "ok", "message": ""})
    except Exception as e:  # noqa: BLE001
        logs.append({"feature_group": "smips", "status": "failed", "message": f"{type(e).__name__}: {e}"})
        print(f"SMIPS feature sampling failed: {type(e).__name__}: {e}", flush=True)

    feature_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(feature_path, index=False)
    log = pd.DataFrame(logs)
    log.to_csv(log_path, index=False)
    out = obs.copy()
    feature_cols = [c for c in features.columns if c not in out.columns and c != row_id_col]
    for col in feature_cols:
        out[col] = features[col].values
    return out, log


def _run_validation(predictions: Path, outdir: Path, bootstrap: int) -> None:
    from dmm_validation.cli import main as validate_main

    validate_main(
        [
            "--predictions",
            str(predictions),
            "--outdir",
            str(outdir),
            "--bootstrap",
            str(bootstrap),
        ]
    )


def main() -> int:
    args = parse_args()
    _repo_imports(args)
    args.outdir.mkdir(parents=True, exist_ok=True)

    obs = pd.read_csv(args.observations)
    obs["date"] = pd.to_datetime(obs["date"]).dt.date.astype(str)
    if "measurement_id" not in obs.columns:
        if {"source_file", "source_row"}.issubset(obs.columns):
            obs["measurement_id"] = obs["source_file"].astype(str) + ":" + obs["source_row"].astype(str)
        else:
            obs["measurement_id"] = np.arange(len(obs), dtype=int).astype(str)
    if args.limit_dates:
        keep = sorted(obs["date"].unique())[: args.limit_dates]
        obs = obs[obs["date"].isin(keep)].copy()
    bbox = _read_bbox(args.bbox_json)

    base = obs.copy()
    if not args.no_feature_sampling:
        base, feature_log = _attach_model_input_samples(base, bbox, args.outdir, args.force, args.quiet)
    else:
        feature_log = pd.DataFrame([{"feature_group": "all", "status": "skipped", "message": ""}])

    model6, log6 = _predict_model_maps(
        base,
        bbox,
        args.outdir,
        model_label="model6_rf",
        model_name=args.model6_name,
        model_kind="model6",
        model8_step_deg=args.model8_step_deg,
        write_map_tifs=not args.no_map_tifs,
        force=args.force,
        quiet=args.quiet,
    )
    model8, log8 = _predict_model_maps(
        base,
        bbox,
        args.outdir,
        model_label="model8_process",
        model_name=args.model8_name,
        model_kind="model8",
        model8_step_deg=args.model8_step_deg,
        write_map_tifs=not args.no_map_tifs,
        force=args.force,
        quiet=args.quiet,
    )

    combined = pd.concat([model6, model8], ignore_index=True, sort=False)
    combined_path = args.outdir / "model6_model8_combined_predictions.csv"
    valid_path = args.outdir / "model6_model8_combined_predictions_valid.csv"
    combined.to_csv(combined_path, index=False)
    valid = combined.dropna(subset=["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]).copy()
    valid.to_csv(valid_path, index=False)

    run_log = pd.concat([feature_log, log6, log8], ignore_index=True, sort=False)
    run_log.to_csv(args.outdir / "tarrawarra_run_log.csv", index=False)

    summary = {
        "observations": str(args.observations),
        "bbox_json": str(args.bbox_json),
        "bbox_wsen": bbox,
        "n_observation_rows": int(len(obs)),
        "n_valid_prediction_rows": int(len(valid)),
        "rows_by_model": valid["model_name"].value_counts().to_dict(),
        "dates_by_model": valid.groupby("model_name")["date"].nunique().to_dict() if not valid.empty else {},
        "outputs": {
            "combined_predictions": str(combined_path),
            "valid_predictions": str(valid_path),
            "run_log": str(args.outdir / "tarrawarra_run_log.csv"),
            "maps": str(args.outdir / "maps"),
        },
    }
    (args.outdir / "tarrawarra_comparison_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if not args.no_validation and not valid.empty:
        _run_validation(valid_path, args.outdir / "validation_report", args.bootstrap)

    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
