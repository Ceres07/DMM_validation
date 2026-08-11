#!/usr/bin/env python3
"""Generate native gridded Llara prediction rasters from DownscalingMoistureModel.

The Llara validation tables already contain point-sampled predictions. This
script produces the map product needed for interpretation: actual
30 m model output rasters over each Llara paddock. It keeps the two Llara fields
(`WE`, `WW`) separate, writes model6/model8 GeoTIFFs, saves the DEM used to
derive terrain metrics, and creates small gallery figures from the true rasters.

By default the script selects the driest and wettest well-sampled date per
paddock from the observation table. Use ``--date-mode all`` or ``--dates`` for
larger batches.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date as _date
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Iterable

import numpy as np
import pandas as pd


os.environ.setdefault("AWS_NO_SIGN_REQUEST", "YES")
os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
os.environ.setdefault("NUMBA_CACHE_DIR", "/private/tmp/numba_cache")
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib")

DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DMM_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel")
DEFAULT_PREDICTION_TABLE = (
    DMM_VALIDATION_ROOT
    / "outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv"
)
DEFAULT_OUTDIR = DMM_VALIDATION_ROOT / "outputs/unified_dense_validation/native_prediction_rasters/llara"
DEFAULT_FIGDIR = DMM_VALIDATION_ROOT / "reports/unified_dense_validation/figures/stage1/llara_native_prediction_maps"


@dataclass(frozen=True)
class RasterTask:
    field: str
    date: str
    selection: str
    bbox: tuple[float, float, float, float]
    n_points: int
    obs_mean: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prediction-table", type=Path, default=DEFAULT_PREDICTION_TABLE)
    parser.add_argument("--dmm-repo", type=Path, default=DEFAULT_DMM_REPO)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--figdir", type=Path, default=DEFAULT_FIGDIR)
    parser.add_argument("--fields", default="WE,WW", help="Comma-separated Llara fields/paddocks.")
    parser.add_argument("--models", default="model6,model8_process")
    parser.add_argument(
        "--date-mode",
        choices=["selected", "all"],
        default="selected",
        help="selected = driest/wettest well-sampled date per field; all = every observed field/date.",
    )
    parser.add_argument(
        "--dates",
        default=None,
        help="Optional comma-separated dates. When supplied, these dates override --date-mode for every field.",
    )
    parser.add_argument("--bbox-padding-deg", type=float, default=0.003)
    parser.add_argument(
        "--min-date-points",
        type=int,
        default=8,
        help="Minimum probes needed when selecting dry/wet representative dates.",
    )
    parser.add_argument("--model6-name", default="model6")
    parser.add_argument("--model8-name", default="model8")
    parser.add_argument("--model8-step-deg", type=float, default=0.05)
    parser.add_argument(
        "--smips-source",
        choices=["cog", "wcs"],
        default="cog",
        help="Source for model6 SMIPS lookback rasters. COG is authenticated TERN COG; WCS is DMM's public WCS path.",
    )
    parser.add_argument("--smips-workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-figures", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args()


def add_dmm_to_path(dmm_repo: Path) -> None:
    sys.path.insert(0, str(dmm_repo))
    os.chdir(dmm_repo)


def load_unique_observations(prediction_table: Path) -> pd.DataFrame:
    if not prediction_table.exists():
        raise FileNotFoundError(prediction_table)
    df = pd.read_csv(prediction_table)
    required = {"point_id", "date", "lon", "lat", "field", "obs_sm_pct"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{prediction_table} is missing columns: {sorted(missing)}")
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    df["obs_sm_pct"] = pd.to_numeric(df["obs_sm_pct"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    obs = (
        df.dropna(subset=["point_id", "date", "lon", "lat", "field", "obs_sm_pct"])
        .drop_duplicates(["point_id", "date", "field"])
        .copy()
    )
    return obs


def padded_bbox(points: pd.DataFrame, padding_deg: float) -> tuple[float, float, float, float]:
    return (
        float(points["lon"].min() - padding_deg),
        float(points["lat"].min() - padding_deg),
        float(points["lon"].max() + padding_deg),
        float(points["lat"].max() + padding_deg),
    )


def select_tasks(obs: pd.DataFrame, args: argparse.Namespace) -> list[RasterTask]:
    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    requested_dates = None
    if args.dates:
        requested_dates = {
            pd.Timestamp(d.strip()).date().isoformat()
            for d in args.dates.split(",")
            if d.strip()
        }

    tasks: list[RasterTask] = []
    for field in fields:
        field_obs = obs[obs["field"].astype(str) == field].copy()
        if field_obs.empty:
            raise ValueError(f"No observations found for field {field!r}")
        bbox = padded_bbox(field_obs.drop_duplicates("point_id"), args.bbox_padding_deg)
        by_date = (
            field_obs.groupby("date")
            .agg(obs_mean=("obs_sm_pct", "mean"), n_points=("point_id", "nunique"))
            .reset_index()
        )
        if requested_dates is not None:
            selected = by_date[by_date["date"].isin(requested_dates)].copy()
            selected["selection"] = "requested"
        elif args.date_mode == "all":
            selected = by_date.copy()
            selected["selection"] = "all_dates"
        else:
            eligible = by_date[by_date["n_points"] >= args.min_date_points].copy()
            if eligible.empty:
                eligible = by_date.copy()
            dry = eligible.sort_values(["obs_mean", "date"], ascending=[True, True]).head(1).copy()
            wet = eligible.sort_values(["obs_mean", "date"], ascending=[False, True]).head(1).copy()
            dry["selection"] = "driest_well_sampled"
            wet["selection"] = "wettest_well_sampled"
            selected = pd.concat([dry, wet], ignore_index=True).drop_duplicates("date")

        for row in selected.itertuples(index=False):
            tasks.append(
                RasterTask(
                    field=field,
                    date=str(row.date),
                    selection=str(row.selection),
                    bbox=bbox,
                    n_points=int(row.n_points),
                    obs_mean=float(row.obs_mean),
                )
            )
    return tasks


def make_local_paddockts_config(cache_root: Path):
    from PaddockTS.config import Config, config as base_config

    out_dir = cache_root / "PaddockTSOut"
    tmp_dir = cache_root / "PaddockTSTmp"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        out_dir=str(out_dir),
        tmp_dir=str(tmp_dir),
        email=getattr(base_config, "email", None),
        tern_api_key=getattr(base_config, "tern_api_key", None),
    )


def query_proxy_class(local_config):
    from PaddockTS.query import Query as OriginalQuery

    class QueryProxy:
        def __new__(cls, *args, **kwargs):
            kwargs.setdefault("config", local_config)
            return OriginalQuery(*args, **kwargs)

        @classmethod
        def from_lat_lon(cls, *args, **kwargs):
            kwargs.setdefault("config", local_config)
            return OriginalQuery.from_lat_lon(*args, **kwargs)

    return QueryProxy


def patch_dmm_queries(dmm_repo: Path, local_config, smips_source: str, smips_workers: int) -> None:
    import emt.antecedent as antecedent
    import emt.persist as persist
    import emt.predict as predict6
    import emt.queries as queries
    import emt.model8.predict as predict8
    from PaddockTS.Environmental.SLGASoils import utils as slga_utils

    QueryProxy = query_proxy_class(local_config)
    persist.MODELS_DIR = dmm_repo / "data/models"
    predict6.Query = QueryProxy
    predict8.Query = QueryProxy
    queries.Query = QueryProxy
    slga_utils.config = local_config

    def query_for_station_custom(station, lat, lon, start, end, buffer_km=1.5):
        period = f"{start:%Y%m%d}_{end:%Y%m%d}"
        stub = f"llara_grid_{station}_{period}".replace(".", "p").replace("-", "m")
        return QueryProxy.from_lat_lon(
            lat=lat,
            lon=lon,
            buffer_km=buffer_km,
            start=start,
            end=end,
            stub=stub,
        )

    antecedent.query_for_station = query_for_station_custom
    if smips_source == "cog":
        predict6.smips_lookback_day = make_smips_lookback_day_cog(local_config, workers=smips_workers)


def make_smips_lookback_day_cog(local_config, workers: int = 8):
    """Return a model6-compatible SMIPS lookback function using TERN COGs."""

    def smips_lookback_day_cog(query, day, var: str = "totalbucket", windows=(7, 30, 365), workers=workers):
        if var != "totalbucket":
            raise ValueError("COG SMIPS fallback currently supports totalbucket only")

        import rasterio
        from rasterio.windows import Window, from_bounds
        import rioxarray  # noqa: F401
        import xarray as xr

        api_key = getattr(query.config, "tern_api_key", None) or getattr(local_config, "tern_api_key", None)
        if not api_key:
            raise ValueError("TERN API key is required for SMIPS COG access")

        target = pd.Timestamp(day)
        start = (target - pd.Timedelta(days=max(windows))).date()
        days = [d.date() for d in pd.date_range(start, target.date(), freq="D")]
        bbox = tuple(float(v) for v in query.bbox)

        os.environ["GDAL_HTTP_USERPWD"] = f"apikey:{api_key}"
        os.environ["GDAL_HTTP_AUTH"] = "BASIC"

        def url_for(d: _date) -> str:
            ymd = d.strftime("%Y%m%d")
            return f"https://data.tern.org.au/model-derived/smips/v1_0/totalbucket/{d.year}/smips_totalbucket_mm_{ymd}.tif"

        def read_one(d: _date):
            url = url_for(d)
            with rasterio.Env(
                GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
                GDAL_HTTP_MAX_RETRY="3",
                GDAL_HTTP_RETRY_DELAY="2",
                GDAL_HTTP_TIMEOUT="45",
            ):
                with rasterio.open(f"/vsicurl/{url}") as src:
                    win = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
                    win = Window(
                        max(0, int(win.col_off) - 1),
                        max(0, int(win.row_off) - 1),
                        int(win.width) + 2,
                        int(win.height) + 2,
                    )
                    arr = src.read(1, window=win, masked=True).astype("float32")
                    data = np.asarray(arr.filled(np.nan), dtype="float32")
                    if src.nodata is not None:
                        data = np.where(data == src.nodata, np.nan, data)
                    transform = src.window_transform(win)
                    xs = transform.c + (np.arange(data.shape[1]) + 0.5) * transform.a
                    ys = transform.f + (np.arange(data.shape[0]) + 0.5) * transform.e
                    da = xr.DataArray(data, coords={"y": ys, "x": xs}, dims=("y", "x"))
                    da = da.rio.write_crs(src.crs or "EPSG:4326")
                    da.name = "smips_totalbucket"
                    return d, da

        slices: dict[_date, object] = {}
        failures: list[tuple[str, str]] = []
        max_workers = max(1, int(workers or 1))
        if max_workers == 1:
            for d in days:
                try:
                    key, da = read_one(d)
                    slices[key] = da
                except Exception as exc:  # noqa: BLE001
                    failures.append((d.isoformat(), str(exc)[:240]))
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(read_one, d): d for d in days}
                for future in as_completed(futures):
                    d = futures[future]
                    try:
                        key, da = future.result()
                        slices[key] = da
                    except Exception as exc:  # noqa: BLE001
                        failures.append((d.isoformat(), str(exc)[:240]))

        if not slices:
            detail = "; ".join(f"{d}: {msg}" for d, msg in failures[:3])
            raise RuntimeError(f"No SMIPS COG days returned data. First failures: {detail}")

        ordered = sorted(slices.items())
        times = pd.to_datetime([d for d, _ in ordered])
        cube = xr.concat([da for _, da in ordered], dim=pd.Index(times, name="time")).sortby("time")
        out = {}
        for window in windows:
            out[f"smips_{window}d"] = cube.isel(time=slice(-window, None)).mean("time")
        today = cube.isel(time=-1)
        out["smips_totalbucket"] = today
        out["smips_anom"] = today - out["smips_365d"]
        return {k: v.rio.write_crs(4326) for k, v in out.items()}

    return smips_lookback_day_cog


def model_output_path(outdir: Path, model_label: str, task: RasterTask) -> Path:
    return outdir / model_label / task.field / f"llara_{task.field}_{task.date}_{model_label}.tif"


def terrain_dem_path(outdir: Path, task: RasterTask) -> Path:
    return outdir / "ancillary" / task.field / f"llara_{task.field}_dem_30m_model_terrain_grid.tif"


def generate_one_model(task: RasterTask, model_label: str, args: argparse.Namespace, model_cache: dict) -> dict:
    result = {
        "field": task.field,
        "date": task.date,
        "selection": task.selection,
        "model_name": model_label,
        "bbox_wsen": json.dumps(task.bbox),
        "n_points_for_date": task.n_points,
        "obs_mean_pct": task.obs_mean,
        "status": "not_run",
        "path": "",
        "error": "",
    }
    out_path = model_output_path(args.outdir, model_label, task)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.force:
        result.update(status="exists", path=str(out_path))
        return result

    try:
        if model_label == "model6":
            import emt.predict as predict6
            from emt.persist import load_model

            model = model_cache.setdefault("model6", load_model(args.model6_name))
            if model is None:
                raise FileNotFoundError(f"Could not load {args.model6_name}.joblib")
            ds = predict6.predict(
                task.bbox,
                task.date,
                model=model,
                model_name=args.model6_name,
                verbose=not args.quiet,
                save=False,
                plot=False,
            )
        elif model_label == "model8_process":
            import emt.model8.predict as predict8
            from emt.persist import load_model

            model = model_cache.setdefault("model8", load_model(args.model8_name))
            if model is None:
                raise FileNotFoundError(f"Could not load {args.model8_name}.joblib")
            ds = predict8.predict_map(
                task.bbox,
                task.date,
                model=model,
                model_name=args.model8_name,
                step_deg=args.model8_step_deg,
                verbose=not args.quiet,
                save=False,
                plot=False,
            )
        else:
            raise ValueError(f"Unknown model label: {model_label}")
        ds["sm_pred"].rio.to_raster(out_path)
        result.update(status="ok", path=str(out_path))
    except Exception as exc:  # noqa: BLE001
        result.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:700]}")
    return result


def generate_dem_for_task(task: RasterTask, args: argparse.Namespace, local_config) -> dict:
    result = {
        "field": task.field,
        "date": task.date,
        "selection": task.selection,
        "model_name": "terrain_dem",
        "bbox_wsen": json.dumps(task.bbox),
        "n_points_for_date": task.n_points,
        "obs_mean_pct": task.obs_mean,
        "status": "not_run",
        "path": "",
        "error": "",
    }
    out_path = terrain_dem_path(args.outdir, task)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists() and not args.force:
        result.update(status="exists", path=str(out_path))
        return result
    try:
        from PaddockTS.query import Query
        from emt.covariates import terrain_covariates

        day = _date.fromisoformat(task.date)
        q = Query(
            bbox=list(task.bbox),
            start=day,
            end=day,
            stub=f"llara_{task.field}_dem_" + "_".join(f"{v:.3f}" for v in task.bbox).replace(".", "p").replace("-", "m"),
            config=local_config,
        )
        terr = terrain_covariates(q)
        terr["elevation"].rio.to_raster(out_path)
        result.update(status="ok", path=str(out_path))
    except Exception as exc:  # noqa: BLE001
        result.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:700]}")
    return result


def write_selected_dates(tasks: Iterable[RasterTask], outdir: Path) -> Path:
    rows = [
        {
            "field": t.field,
            "date": t.date,
            "selection": t.selection,
            "n_points": t.n_points,
            "obs_mean_pct": t.obs_mean,
            "west": t.bbox[0],
            "south": t.bbox[1],
            "east": t.bbox[2],
            "north": t.bbox[3],
        }
        for t in tasks
    ]
    out = outdir / "selected_llara_raster_dates.csv"
    pd.DataFrame(rows).drop_duplicates(["field", "date"]).to_csv(out, index=False)
    return out


def make_gallery_figures(args: argparse.Namespace, obs: pd.DataFrame, tasks: list[RasterTask], log: pd.DataFrame) -> list[Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pyproj import Transformer
    import rasterio

    args.figdir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    successful = log[log["status"].isin(["ok", "exists"])].copy()
    successful = successful[successful["model_name"].isin(["model6", "model8_process"])]

    for field in sorted({task.field for task in tasks}):
        field_tasks = [task for task in tasks if task.field == field]
        if not field_tasks:
            continue
        models = [m for m in ["model6", "model8_process"] if m in set(successful["model_name"])]
        if not models:
            continue
        rasters = []
        values = []
        for task in field_tasks:
            for model in models:
                path = model_output_path(args.outdir, model, task)
                if path.exists():
                    with rasterio.open(path) as src:
                        arr = src.read(1, masked=True).astype("float32")
                        vals = np.asarray(arr.filled(np.nan), dtype=float)
                        values.append(vals[np.isfinite(vals)])
                    rasters.append((task, model, path))
        if not rasters:
            continue
        finite = np.concatenate([v for v in values if len(v)]) if any(len(v) for v in values) else np.array([])
        vmin, vmax = (np.nanpercentile(finite, [2, 98]) if finite.size else (0, 60))

        rows = len(field_tasks)
        cols = len(models)
        fig, axes = plt.subplots(rows, cols, figsize=(4.8 * cols, 4.2 * rows), squeeze=False)
        for r, task in enumerate(field_tasks):
            points = obs[(obs["field"].astype(str) == field) & (obs["date"] == task.date)].copy()
            for c, model in enumerate(models):
                ax = axes[r, c]
                path = model_output_path(args.outdir, model, task)
                if not path.exists():
                    ax.axis("off")
                    ax.set_title(f"{model}\nmissing")
                    continue
                with rasterio.open(path) as src:
                    arr = src.read(1, masked=True).astype("float32")
                    bounds = src.bounds
                    extent = [bounds.left, bounds.right, bounds.bottom, bounds.top]
                    im = ax.imshow(
                        arr,
                        extent=extent,
                        origin="upper",
                        cmap="YlGnBu",
                        vmin=vmin,
                        vmax=vmax,
                    )
                    if not points.empty:
                        transformer = Transformer.from_crs("EPSG:4326", src.crs, always_xy=True)
                        xs, ys = transformer.transform(points["lon"].to_numpy(), points["lat"].to_numpy())
                        ax.scatter(xs, ys, s=18, facecolors="none", edgecolors="black", linewidths=0.8)
                    ax.set_title(f"{model}\n{task.date} · {task.selection.replace('_', ' ')}")
                    ax.set_xticks([])
                    ax.set_yticks([])
                    ax.set_aspect("equal")
        fig.suptitle(f"Llara {field}: native gridded model predictions", y=0.995, fontsize=14)
        cbar = fig.colorbar(im, ax=axes.ravel().tolist(), shrink=0.86, pad=0.02)
        cbar.set_label("predicted soil moisture (%)")
        out = args.figdir / f"llara_{field}_native_prediction_gallery.png"
        fig.savefig(out, dpi=180, bbox_inches="tight")
        plt.close(fig)
        outputs.append(out)
    return outputs


def copy_key_outputs_to_report(args: argparse.Namespace) -> None:
    """Keep a tiny manifest in the report figure folder for human navigation."""
    args.figdir.mkdir(parents=True, exist_ok=True)
    manifest = args.figdir / "llara_native_prediction_rasters_manifest.md"
    rel_outdir = args.outdir
    lines = [
        "# Llara native prediction rasters",
        "",
        "These figures and rasters are generated from the native DownscalingMoistureModel map functions, not from point interpolation.",
        "",
        f"- Raster output folder: `{rel_outdir}`",
        f"- Selected dates table: `{args.outdir / 'selected_llara_raster_dates.csv'}`",
        f"- Run log: `{args.outdir / 'native_raster_generation_log.csv'}`",
        "",
        "Main raster subfolders:",
        "",
        f"- Model6: `{args.outdir / 'model6'}`",
        f"- Model8 process: `{args.outdir / 'model8_process'}`",
        f"- Terrain DEMs: `{args.outdir / 'ancillary'}`",
        "",
    ]
    manifest.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.figdir.mkdir(parents=True, exist_ok=True)

    obs = load_unique_observations(args.prediction_table)
    tasks = select_tasks(obs, args)
    selected_path = write_selected_dates(tasks, args.outdir)
    if not args.quiet:
        print(f"selected {len(tasks)} field/date raster tasks")
        print(f"wrote {selected_path}")

    add_dmm_to_path(args.dmm_repo)
    local_config = make_local_paddockts_config(args.outdir / "_paddockts_cache")
    patch_dmm_queries(args.dmm_repo, local_config, args.smips_source, args.smips_workers)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    model_cache: dict = {}
    rows = []
    unique_field_tasks = list({(t.field, t.bbox): t for t in tasks}.values())
    for task in unique_field_tasks:
        if not args.quiet:
            print(f"DEM {task.field} {task.bbox}", flush=True)
        rows.append(generate_dem_for_task(task, args, local_config))

    for task in tasks:
        for model_label in models:
            if not args.quiet:
                print(f"{model_label} {task.field} {task.date} ({task.selection})", flush=True)
            rows.append(generate_one_model(task, model_label, args, model_cache))

    log = pd.DataFrame(rows)
    log_path = args.outdir / "native_raster_generation_log.csv"
    log.to_csv(log_path, index=False)
    if not args.quiet:
        print(f"wrote {log_path}")
        print(log[["field", "date", "model_name", "status", "path", "error"]].to_string(index=False))

    if not args.skip_figures:
        figures = make_gallery_figures(args, obs, tasks, log)
        for figure in figures:
            if not args.quiet:
                print(f"wrote {figure}")

    copy_key_outputs_to_report(args)

    failed = log[log["status"] == "failed"]
    if not failed.empty:
        print(f"{len(failed)} raster task(s) failed; see {log_path}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
