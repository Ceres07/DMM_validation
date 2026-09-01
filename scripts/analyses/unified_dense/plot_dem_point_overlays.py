#!/usr/bin/env python3
"""Create true DEM + soil-moisture point overlay maps for dense validation sites.

The maps produced here are presentation figures backed by the actual DEM rasters
used for terrain/model-grid products where available. Tarrawarra uses the
converted 5 m campaign DEM. Llara uses the saved model-terrain-grid DEMs for the
WE and WW paddocks. Esdale is regenerated through the DownscalingMoistureModel
terrain pipeline if its model-grid DEM has not already been cached.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
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
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DMM_REPO = Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel")
DEFAULT_FIGDIR = ROOT / "reports/analyses/unified_dense_validation/figures/stage1/dem_point_overlays"
DEFAULT_ESDALE_DEM = (
    ROOT
    / "outputs/unified_dense_validation/native_prediction_rasters/esdale/ancillary/"
    / "esdale_dem_30m_model_terrain_grid.tif"
)
DEFAULT_ESDALE_MODEL_TEMPLATE = ROOT / "outputs/model6_vs_model8_dense/model6_tifs/untrained_model6_2025-04-30.tif"
DEFAULT_ESDALE_TABLE = ROOT / "outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv"
DEFAULT_TARRAWARRA_DEM = ROOT / "outputs/tarrawarra_conversion/tarrawarra_5m_dem_agd66_amg55.tif"
DEFAULT_TARRAWARRA_TABLE = (
    ROOT / "outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv"
)
DEFAULT_LLARA_TABLE = ROOT / "outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv"
DEFAULT_LLARA_DEM_ROOT = ROOT / "outputs/unified_dense_validation/native_prediction_rasters/llara/ancillary"
DEFAULT_NERRIGUNDAH_TABLE = (
    ROOT / "outputs/nerrigundah_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv"
)
DEFAULT_NERRIGUNDAH_DEM = (
    ROOT
    / "outputs/unified_dense_validation/native_prediction_rasters/nerrigundah/ancillary/"
    / "nerrigundah_dem_30m_model_terrain_grid.tif"
)
DEFAULT_MRI_TABLE = ROOT / "outputs/mri_dense_validation/mri_model6_model8_predictions.csv"
DEFAULT_MRI_DEM = (
    ROOT
    / "outputs/unified_dense_validation/native_prediction_rasters/mri/ancillary/"
    / "mri_dem_30m_model_terrain_grid.tif"
)
DEFAULT_GLOBAL_PADDOCKTS_TMP = Path("/Users/dmitrygrishin/Downloads/PaddockTSTmp")


@dataclass(frozen=True)
class MapSpec:
    site: str
    title: str
    dem_path: Path
    points: pd.DataFrame
    point_x_col: str | None = None
    point_y_col: str | None = None
    point_crs: str | None = "EPSG:4326"
    source_note: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dmm-repo", type=Path, default=DEFAULT_DMM_REPO)
    parser.add_argument("--figdir", type=Path, default=DEFAULT_FIGDIR)
    parser.add_argument("--esdale-dem", type=Path, default=DEFAULT_ESDALE_DEM)
    parser.add_argument("--esdale-template", type=Path, default=DEFAULT_ESDALE_MODEL_TEMPLATE)
    parser.add_argument("--esdale-table", type=Path, default=DEFAULT_ESDALE_TABLE)
    parser.add_argument("--tarrawarra-dem", type=Path, default=DEFAULT_TARRAWARRA_DEM)
    parser.add_argument("--tarrawarra-table", type=Path, default=DEFAULT_TARRAWARRA_TABLE)
    parser.add_argument("--llara-table", type=Path, default=DEFAULT_LLARA_TABLE)
    parser.add_argument("--llara-dem-root", type=Path, default=DEFAULT_LLARA_DEM_ROOT)
    parser.add_argument("--nerrigundah-table", type=Path, default=DEFAULT_NERRIGUNDAH_TABLE)
    parser.add_argument("--nerrigundah-dem", type=Path, default=DEFAULT_NERRIGUNDAH_DEM)
    parser.add_argument("--mri-table", type=Path, default=DEFAULT_MRI_TABLE)
    parser.add_argument("--mri-dem", type=Path, default=DEFAULT_MRI_DEM)
    parser.add_argument("--global-paddockts-tmp", type=Path, default=DEFAULT_GLOBAL_PADDOCKTS_TMP)
    parser.add_argument("--force-esdale-dem", action="store_true")
    parser.add_argument("--force-site-dems", action="store_true")
    parser.add_argument("--bbox-padding-deg", type=float, default=0.01)
    parser.add_argument("--dpi", type=int, default=220)
    return parser.parse_args()


def load_unique_points(path: Path, extra_subset: pd.Series | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    if extra_subset is not None:
        df = df[extra_subset].copy()
    required = {"point_id", "lon", "lat"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path} is missing required columns: {sorted(missing)}")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df = df.dropna(subset=["point_id", "lon", "lat"]).copy()
    preferred_cols = [
        "point_id",
        "lon",
        "lat",
        "field",
        "easting_agd66_amg55",
        "northing_agd66_amg55",
        "probe_easting_utm55s",
        "probe_northing_utm55s",
        "elevation",
        "probe_elevation_m",
    ]
    cols = [col for col in preferred_cols if col in df.columns]
    return df[cols].drop_duplicates("point_id").reset_index(drop=True)


def esdale_bbox_from_template_or_points(args: argparse.Namespace, points: pd.DataFrame) -> tuple[float, float, float, float]:
    if args.esdale_template.exists():
        import rasterio
        from rasterio.warp import transform_bounds

        with rasterio.open(args.esdale_template) as src:
            return tuple(float(v) for v in transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21))
    return (
        float(points["lon"].min() - args.bbox_padding_deg),
        float(points["lat"].min() - args.bbox_padding_deg),
        float(points["lon"].max() + args.bbox_padding_deg),
        float(points["lat"].max() + args.bbox_padding_deg),
    )


def bbox_from_points(points: pd.DataFrame, padding_deg: float) -> tuple[float, float, float, float]:
    return (
        float(points["lon"].min() - padding_deg),
        float(points["lat"].min() - padding_deg),
        float(points["lon"].max() + padding_deg),
        float(points["lat"].max() + padding_deg),
    )


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


def ensure_model_grid_dem(
    *,
    site: str,
    dem_path: Path,
    points: pd.DataFrame,
    args: argparse.Namespace,
    start_day: str,
    stub: str,
    source: str,
) -> Path:
    """Regenerate a true Copernicus/model terrain DEM for a validation site.

    If a matching global PaddockTS terrain cache exists, copy it into the local
    validation cache before calling the terrain-covariate function. This avoids
    replacing a real gridded DEM with an interpolated point surface.
    """

    if dem_path.exists() and not args.force_site_dems:
        return dem_path

    if not args.dmm_repo.exists():
        raise FileNotFoundError(args.dmm_repo)
    sys.path.insert(0, str(args.dmm_repo))
    dem_path.parent.mkdir(parents=True, exist_ok=True)

    from PaddockTS.query import Query
    from emt.covariates import terrain_covariates

    local_config = make_local_paddockts_config(
        ROOT / "outputs/unified_dense_validation/native_prediction_rasters" / site / "_paddockts_cache"
    )
    bbox = bbox_from_points(points, args.bbox_padding_deg)
    day = date.fromisoformat(start_day)
    q = Query(bbox=list(bbox), start=day, end=day, stub=stub, config=local_config)

    local_aoi = Path(q.aoi_dir)
    global_aoi = args.global_paddockts_tmp / "aoi" / q.bbox_hash
    for name in ["terrain.tif", "terrain.tif._SUCCESS", "terrain_utm.tif"]:
        src = global_aoi / name
        dst = local_aoi / name
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)

    terr = terrain_covariates(q)
    terr["elevation"].rio.to_raster(dem_path)
    metadata = {
        "site": site,
        "dem_path": str(dem_path),
        "bbox_wsen": bbox,
        "bbox_hash": q.bbox_hash,
        "source": source,
        "copied_from_global_cache": str(global_aoi) if global_aoi.exists() else None,
    }
    (dem_path.parent / f"{site}_dem_30m_model_terrain_grid_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    return dem_path


def ensure_esdale_dem(args: argparse.Namespace, points: pd.DataFrame) -> Path:
    """Regenerate Esdale's true Copernicus/model terrain DEM when not cached."""
    out_path = args.esdale_dem
    if out_path.exists() and not args.force_esdale_dem:
        return out_path

    if not args.dmm_repo.exists():
        raise FileNotFoundError(args.dmm_repo)
    sys.path.insert(0, str(args.dmm_repo))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from PaddockTS.query import Query
    from emt.covariates import terrain_covariates

    local_config = make_local_paddockts_config(
        ROOT / "outputs/unified_dense_validation/native_prediction_rasters/esdale/_paddockts_cache"
    )
    bbox = esdale_bbox_from_template_or_points(args, points)
    q = Query(
        bbox=list(bbox),
        start=date.fromisoformat("2025-04-30"),
        end=date.fromisoformat("2025-04-30"),
        stub="esdale_dem_model_terrain_grid",
        config=local_config,
    )
    terr = terrain_covariates(q)
    terr["elevation"].rio.to_raster(out_path)

    metadata = {
        "site": "Esdale",
        "dem_path": str(out_path),
        "bbox_wsen": bbox,
        "source": "DownscalingMoistureModel emt.covariates.terrain_covariates / PaddockTS Copernicus DEM",
        "template": str(args.esdale_template) if args.esdale_template.exists() else None,
    }
    (out_path.parent / "esdale_dem_30m_model_terrain_grid_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    return out_path


def read_dem(path: Path) -> tuple[np.ndarray, object, object, tuple[float, float, float, float]]:
    import rasterio

    if not path.exists():
        raise FileNotFoundError(path)
    with rasterio.open(path) as src:
        arr = src.read(1, masked=True).astype("float64")
        data = np.asarray(arr.filled(np.nan), dtype=float)
        if src.nodata is not None:
            data = np.where(data == src.nodata, np.nan, data)
        return data, src.transform, src.crs, tuple(src.bounds)


def raster_edges(transform, height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    rows, cols = np.meshgrid(np.arange(height + 1), np.arange(width + 1), indexing="ij")
    xs = transform.c + transform.a * cols + transform.b * rows
    ys = transform.f + transform.d * cols + transform.e * rows
    return xs, ys


def transform_points(points: pd.DataFrame, spec: MapSpec, raster_crs) -> tuple[np.ndarray, np.ndarray]:
    from pyproj import Transformer

    if spec.point_x_col and spec.point_y_col:
        xs = pd.to_numeric(points[spec.point_x_col], errors="coerce").to_numpy(dtype=float)
        ys = pd.to_numeric(points[spec.point_y_col], errors="coerce").to_numpy(dtype=float)
        src_crs = spec.point_crs
    else:
        xs = points["lon"].to_numpy(dtype=float)
        ys = points["lat"].to_numpy(dtype=float)
        src_crs = "EPSG:4326"

    if src_crs and raster_crs and str(src_crs) != str(raster_crs):
        transformer = Transformer.from_crs(src_crs, raster_crs, always_xy=True)
        xs, ys = transformer.transform(xs, ys)
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def nice_scalebar_length(span_m: float) -> float:
    candidates = np.array([25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000], dtype=float)
    target = max(span_m * 0.22, 1.0)
    good = candidates[candidates <= target]
    return float(good[-1] if len(good) else candidates[0])


def add_scalebar(ax, bounds: tuple[float, float, float, float]) -> None:
    left, bottom, right, top = bounds
    span_x = right - left
    span_y = top - bottom
    length = nice_scalebar_length(span_x)
    x0 = left + 0.06 * span_x
    y0 = bottom + 0.06 * span_y
    ax.plot([x0, x0 + length], [y0, y0], color="black", linewidth=3.0, solid_capstyle="butt", zorder=6)
    ax.plot([x0, x0 + length], [y0, y0], color="white", linewidth=1.2, solid_capstyle="butt", zorder=7)
    label = f"{int(length)} m" if length < 1000 else f"{length / 1000:g} km"
    ax.text(
        x0 + length / 2,
        y0 + 0.025 * span_y,
        label,
        ha="center",
        va="bottom",
        fontsize=8,
        color="black",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1.5},
        zorder=8,
    )


def add_north_arrow(ax, bounds: tuple[float, float, float, float]) -> None:
    left, bottom, right, top = bounds
    span_x = right - left
    span_y = top - bottom
    x = right - 0.08 * span_x
    y0 = bottom + 0.08 * span_y
    y1 = y0 + 0.12 * span_y
    ax.annotate(
        "",
        xy=(x, y1),
        xytext=(x, y0),
        arrowprops={"arrowstyle": "-|>", "color": "black", "lw": 1.6, "mutation_scale": 13},
        zorder=8,
    )
    ax.text(
        x,
        y1 + 0.018 * span_y,
        "N",
        ha="center",
        va="bottom",
        fontsize=9,
        fontweight="bold",
        color="black",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1.0},
        zorder=8,
    )


def setup_plot_style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "0.15",
            "axes.linewidth": 0.8,
            "font.size": 10,
            "axes.titlesize": 13,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
            "savefig.facecolor": "white",
        }
    )
    return plt


def draw_dem_map(spec: MapSpec, out: Path, dpi: int) -> Path:
    plt = setup_plot_style()
    import matplotlib.patheffects as pe
    from matplotlib.colors import LightSource, LinearSegmentedColormap
    from matplotlib.ticker import FuncFormatter

    data, transform, raster_crs, bounds = read_dem(spec.dem_path)
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        raise ValueError(f"{spec.dem_path} contains no finite DEM cells")
    vmin, vmax = np.percentile(finite, [2, 98])
    if vmin == vmax:
        vmin, vmax = float(np.nanmin(finite)), float(np.nanmax(finite))
    if vmin == vmax:
        vmax = vmin + 1.0
    x_edges, y_edges = raster_edges(transform, data.shape[0], data.shape[1])
    xs, ys = transform_points(spec.points, spec, raster_crs)
    valid_points = np.isfinite(xs) & np.isfinite(ys)
    point_count = int(valid_points.sum())
    point_size = 34 if point_count < 120 else 9
    point_alpha = 0.92 if point_count < 120 else 0.56

    fig, ax = plt.subplots(figsize=(7.1, 6.2))
    dem_cmap = LinearSegmentedColormap.from_list(
        "clean_dem",
        ["#315b8c", "#2f8f7a", "#77a95b", "#c5b65f", "#d6a374", "#f3ece7"],
        N=256,
    )
    mesh = ax.pcolormesh(
        x_edges,
        y_edges,
        data,
        shading="flat",
        cmap=dem_cmap,
        vmin=vmin,
        vmax=vmax,
        zorder=1,
    )

    try:
        pixel_x = float(np.hypot(transform.a, transform.d))
        pixel_y = float(np.hypot(transform.b, transform.e))
        shade = LightSource(azdeg=315, altdeg=45).hillshade(
            np.where(np.isfinite(data), data, np.nanmedian(finite)),
            vert_exag=1.25,
            dx=max(pixel_x, 1.0),
            dy=max(pixel_y, 1.0),
        )
        ax.pcolormesh(x_edges, y_edges, shade, shading="flat", cmap="gray", alpha=0.10, zorder=2)
    except Exception:
        pass

    ax.scatter(
        xs[valid_points],
        ys[valid_points],
        s=point_size,
        c="#dc2626",
        edgecolors="white",
        linewidths=0.65 if point_count < 120 else 0.25,
        alpha=point_alpha,
        label=f"Soil moisture points (n={point_count:,})",
        zorder=5,
    )

    ax.set_aspect("equal")
    left, bottom, right, top = bounds
    pad_x = (right - left) * 0.035
    pad_y = (top - bottom) * 0.035
    ax.set_xlim(left - pad_x, right + pad_x)
    ax.set_ylim(bottom - pad_y, top + pad_y)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _pos: f"{x / 1000:.1f}"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _pos: f"{y / 1000:.1f}"))
    ax.set_xlabel("Easting (km)")
    ax.set_ylabel("Northing (km)")
    ax.grid(color="white", alpha=0.28, linewidth=0.5)
    ax.set_title(spec.title, pad=10, fontweight="semibold")
    elev_range = f"DEM elevation: {np.nanmin(finite):.1f}–{np.nanmax(finite):.1f} m"
    note = f"{elev_range}\n{spec.source_note}" if spec.source_note else elev_range
    label = ax.text(
        0.015,
        0.985,
        note,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=8.4,
        color="0.08",
        bbox={"facecolor": "white", "edgecolor": "0.85", "alpha": 0.82, "pad": 4.0},
        zorder=9,
    )
    label.set_path_effects([pe.withStroke(linewidth=1.0, foreground="white")])
    add_scalebar(ax, (left, bottom, right, top))
    add_north_arrow(ax, (left, bottom, right, top))
    ax.legend(loc="lower right", frameon=True, framealpha=0.86, facecolor="white", edgecolor="0.82")
    cbar = fig.colorbar(mesh, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label("Elevation (m)")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def draw_gallery(specs: Iterable[MapSpec], outputs: dict[str, Path], out: Path, dpi: int) -> Path:
    plt = setup_plot_style()
    import matplotlib.pyplot as plt

    specs = list(specs)
    images = []
    for spec in specs:
        data, _transform, _crs, _bounds = read_dem(spec.dem_path)
        images.append((spec, data))

    ncols = 3 if len(specs) > 4 else 2
    nrows = int(np.ceil(len(specs) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.6 * ncols, 4.8 * nrows))
    axes = axes.ravel()
    for ax, (spec, _data) in zip(axes, images):
        img = plt.imread(outputs[spec.site])
        ax.imshow(img)
        ax.axis("off")
    for ax in axes[len(images) :]:
        ax.axis("off")
    fig.suptitle("Dense validation site terrain context", fontsize=16, fontweight="semibold", y=0.99)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out


def build_specs(args: argparse.Namespace) -> list[MapSpec]:
    esdale_points = load_unique_points(args.esdale_table)
    tarrawarra_points = load_unique_points(args.tarrawarra_table)
    nerrigundah_points = load_unique_points(args.nerrigundah_table)
    mri_points = load_unique_points(args.mri_table)
    llara_all = pd.read_csv(args.llara_table)
    specs = [
        MapSpec(
            site="esdale",
            title="Esdale dense validation terrain",
            dem_path=ensure_esdale_dem(args, esdale_points),
            points=esdale_points,
            source_note="30 m Copernicus/model terrain grid",
        ),
        MapSpec(
            site="tarrawarra",
            title="Tarrawarra terrain and 30 m validation cells",
            dem_path=args.tarrawarra_dem,
            points=tarrawarra_points,
            source_note="5 m converted campaign DEM; raw probes aggregated to model grid cells",
        ),
        MapSpec(
            site="nerrigundah",
            title="Nerrigundah terrain and 30 m validation cells",
            dem_path=ensure_model_grid_dem(
                site="nerrigundah",
                dem_path=args.nerrigundah_dem,
                points=nerrigundah_points,
                args=args,
                start_day="1997-08-27",
                stub="nerrigundah_dem_model_terrain_grid",
                source="DownscalingMoistureModel emt.covariates.terrain_covariates / PaddockTS Copernicus DEM",
            ),
            points=nerrigundah_points,
            source_note="30 m Copernicus/model terrain grid; raw probes aggregated to model grid cells",
        ),
        MapSpec(
            site="mri",
            title="MRI probe-network terrain",
            dem_path=ensure_model_grid_dem(
                site="mri",
                dem_path=args.mri_dem,
                points=mri_points,
                args=args,
                start_day="2021-07-01",
                stub="mri_dem_model_terrain_grid",
                source="DownscalingMoistureModel emt.covariates.terrain_covariates / PaddockTS Copernicus DEM",
            ),
            points=mri_points,
            source_note="30 m Copernicus/model terrain grid",
        ),
    ]
    for field in ["WE", "WW"]:
        field_points = load_unique_points(args.llara_table, llara_all["field"].astype(str) == field)
        specs.append(
            MapSpec(
                site=f"llara_{field.lower()}",
                title=f"Llara {field} paddock terrain",
                dem_path=args.llara_dem_root / field / f"llara_{field}_dem_30m_model_terrain_grid.tif",
                points=field_points,
                point_x_col="probe_easting_utm55s",
                point_y_col="probe_northing_utm55s",
                point_crs="EPSG:32755",
                source_note="30 m Copernicus/model terrain grid",
            )
        )
    return specs


def write_manifest(figdir: Path, outputs: dict[str, Path], specs: list[MapSpec], gallery: Path) -> Path:
    rows = []
    for spec in specs:
        rows.append(
            {
                "site_map": spec.site,
                "figure": str(outputs[spec.site]),
                "dem": str(spec.dem_path),
                "n_points": int(spec.points["point_id"].nunique()),
                "source_note": spec.source_note,
            }
        )
    manifest = figdir / "dem_point_overlays_manifest.md"
    lines = [
        "# DEM + soil-moisture point overlays",
        "",
        "These maps use gridded DEM rasters, not interpolated point elevations.",
        "",
        f"- Combined gallery: `{gallery}`",
        "",
        "| Site map | Points | DEM source | Figure | DEM raster |",
        "|---|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['site_map']} | {row['n_points']} | {row['source_note']} | "
            f"`{row['figure']}` | `{row['dem']}` |"
        )
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    args = parse_args()
    args.figdir.mkdir(parents=True, exist_ok=True)
    specs = build_specs(args)
    outputs: dict[str, Path] = {}
    for spec in specs:
        out = args.figdir / f"{spec.site}_dem_points_overlay.png"
        outputs[spec.site] = draw_dem_map(spec, out, args.dpi)
        print(f"wrote {out}", flush=True)
    gallery = draw_gallery(specs, outputs, args.figdir / "dem_points_overlay_gallery.png", args.dpi)
    print(f"wrote {gallery}", flush=True)
    manifest = write_manifest(args.figdir, outputs, specs, gallery)
    print(f"wrote {manifest}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
