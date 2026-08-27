#!/usr/bin/env python3
"""Tarrawarra campaign gallery: coarse estimate, model6 RF and model8 process.

The dense Esdale gallery uses the prediction raster grid directly. Tarrawarra is
slightly different because the campaign has its own converted 5 m DEM footprint.
This script therefore reprojects each panel to that DEM grid before plotting:

1. coarse SMIPS TotalBucket estimate;
2. model6 RF map;
3. model8 process map.

By default, nine campaign dates are chosen evenly across the available
Tarrawarra model6/model8 map dates. The coarse panels are cached as GeoTIFFs so
reruns do not refetch/reproject them unless ``--overwrite-coarse`` is supplied.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO / "outputs" / "tarrawarra_model6_vs_model8"
DEFAULT_MAP_DIR = DEFAULT_OUTPUT_ROOT / "maps"
DEFAULT_CONVERSION_DIR = REPO / "outputs" / "tarrawarra_conversion"
DEFAULT_TEMPLATE = DEFAULT_CONVERSION_DIR / "tarrawarra_5m_dem_agd66_amg55.tif"
DEFAULT_FEATURE_TABLE = DEFAULT_OUTPUT_ROOT / "tarrawarra_sampled_model_inputs.csv"
DEFAULT_COARSE_DIR = DEFAULT_OUTPUT_ROOT / "coarse_smips_tifs_5m_dem_bounds"
DEFAULT_FIG = (
    REPO
    / "reports"
    / "sites"
    / "tarrawarra_model6_vs_model8"
    / "figures"
    / "tarrawarra_coarse_model6_model8_gallery_5m_dem_bounds.png"
)
NODATA = -9999.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-dir", type=Path, default=DEFAULT_MAP_DIR)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--coarse-dir", type=Path, default=DEFAULT_COARSE_DIR)
    parser.add_argument("--feature-table", type=Path, default=DEFAULT_FEATURE_TABLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_FIG)
    parser.add_argument("--n-dates", type=int, default=9)
    parser.add_argument(
        "--dates",
        nargs="+",
        default=None,
        help="Optional explicit campaign dates, e.g. 1995-09-25 1996-05-02.",
    )
    parser.add_argument("--overwrite-coarse", action="store_true")
    parser.add_argument(
        "--downscaling-model-repo",
        type=Path,
        default=Path("/Volumes/Dmitry_work/borevitz_projects/DownscalingMoistureModel"),
        help="Path to DownscalingMoistureModel, needed for emt.smips if coarse TIFs are missing.",
    )
    return parser.parse_args()


def date_from_name(path: Path) -> str:
    return path.stem[-10:]


def discover_map_triplets(map_dir: Path) -> list[tuple[str, Path, Path]]:
    model6 = {
        date_from_name(path): path
        for path in map_dir.glob("model6_rf_*.tif")
        if not path.name.startswith("._")
    }
    model8 = {
        date_from_name(path): path
        for path in map_dir.glob("model8_process_*.tif")
        if not path.name.startswith("._")
    }
    dates = sorted(set(model6).intersection(model8))
    if not dates:
        raise SystemExit(f"No matched Tarrawarra model6/model8 TIF dates found in {map_dir}")
    return [(day, model6[day], model8[day]) for day in dates]


def select_dates(
    triplets: list[tuple[str, Path, Path]],
    n_dates: int,
    explicit_dates: list[str] | None,
) -> list[tuple[str, Path, Path]]:
    by_date = {day: (day, model6_path, model8_path) for day, model6_path, model8_path in triplets}
    if explicit_dates:
        missing = [day for day in explicit_dates if day not in by_date]
        if missing:
            raise SystemExit(f"Requested dates have no paired Tarrawarra maps: {missing}")
        return [by_date[day] for day in explicit_dates]

    if n_dates <= 0:
        raise SystemExit("--n-dates must be positive")
    if len(triplets) <= n_dates:
        return triplets

    indices = np.round(np.linspace(0, len(triplets) - 1, n_dates)).astype(int)
    selected: list[tuple[str, Path, Path]] = []
    seen: set[int] = set()
    for idx in indices:
        idx = int(idx)
        if idx not in seen:
            selected.append(triplets[idx])
            seen.add(idx)

    # Guard against duplicate rounded indices if a different n_dates is used.
    for idx, triplet in enumerate(triplets):
        if len(selected) >= n_dates:
            break
        if idx not in seen:
            selected.append(triplet)
    return sorted(selected, key=lambda item: item[0])


def open_template(path: Path):
    import rioxarray  # noqa: F401

    return rioxarray.open_rasterio(path, masked=True).squeeze("band", drop=True).load()


def template_mask(template) -> np.ndarray:
    values = np.asarray(template.values)
    mask = ~np.isfinite(values)
    nodata = template.rio.nodata
    if nodata is not None:
        mask |= values == nodata
    return mask


def template_wgs84_bbox(template_path: Path) -> tuple[float, float, float, float]:
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(template_path) as src:
        return tuple(transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21))


def read_raster_on_template(
    path: Path,
    template,
    mask: np.ndarray,
    *,
    resampling,
) -> np.ndarray:
    import rioxarray  # noqa: F401

    da = rioxarray.open_rasterio(path, masked=True).squeeze("band", drop=True)
    arr = da.rio.reproject_match(template, resampling=resampling).values.astype("float32")
    return np.where(mask, np.nan, arr)


def write_raster_like(path: Path, array: np.ndarray, template_path: Path, description: str) -> None:
    import rasterio

    with rasterio.open(template_path) as src:
        profile = src.profile.copy()
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=NODATA, compress="deflate", predictor=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(array), array, NODATA).astype("float32"), 1)
        dst.set_band_description(1, description)


def fallback_coarse_value(day: str, feature_table: Path) -> float:
    if not feature_table.exists():
        return np.nan
    df = pd.read_csv(feature_table, usecols=lambda col: col in {"date", "smips_totalbucket"})
    if "date" not in df or "smips_totalbucket" not in df:
        return np.nan
    vals = pd.to_numeric(df.loc[df["date"].astype(str) == day, "smips_totalbucket"], errors="coerce")
    if vals.notna().any():
        return float(vals.median())
    return np.nan


def ensure_coarse_smips_tifs(
    dates: list[str],
    coarse_dir: Path,
    template_path: Path,
    template,
    mask: np.ndarray,
    downscaling_model_repo: Path,
    feature_table: Path,
    overwrite: bool,
) -> dict[str, Path]:
    from rasterio.enums import Resampling

    coarse_dir.mkdir(parents=True, exist_ok=True)
    out = {day: coarse_dir / f"coarse_smips_totalbucket_{day}.tif" for day in dates}
    if all(path.exists() for path in out.values()) and not overwrite:
        print(f"using cached coarse SMIPS TIFs in {coarse_dir}", flush=True)
        return out

    if str(downscaling_model_repo) not in sys.path:
        sys.path.insert(0, str(downscaling_model_repo))

    try:
        from emt.smips import smips_cube

        bbox = template_wgs84_bbox(template_path)
        print(f"fetching coarse SMIPS TotalBucket over DEM-derived WGS84 bbox {bbox} ...", flush=True)
        smips = smips_cube(
            dates[0],
            dates[-1],
            bbox,
            var="totalbucket",
            days=[pd.Timestamp(day).date() for day in dates],
        ).sortby("time")

        for day in dates:
            path = out[day]
            if path.exists() and not overwrite:
                continue
            da = smips.sel(time=pd.Timestamp(day)).rio.write_crs(4326)
            coarse_on_template = da.rio.reproject_match(template, resampling=Resampling.nearest)
            arr = np.where(mask, np.nan, coarse_on_template.values.astype("float32"))
            write_raster_like(path, arr, template_path, "smips_totalbucket_mm")
            print(f"  wrote {path}", flush=True)
        return out
    except Exception as exc:
        print(
            "warning: could not fetch/reproject SMIPS coarse grids; "
            f"falling back to per-date median smips_totalbucket from {feature_table}: {exc}",
            flush=True,
        )

    for day in dates:
        path = out[day]
        if path.exists() and not overwrite:
            continue
        value = fallback_coarse_value(day, feature_table)
        arr = np.full(mask.shape, value, dtype="float32")
        arr = np.where(mask, np.nan, arr)
        write_raster_like(path, arr, template_path, "smips_totalbucket_mm_fallback_median")
        print(f"  wrote fallback coarse panel {path}", flush=True)
    return out


def read_cached_raster(path: Path, mask: np.ndarray) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return np.where(mask, np.nan, arr)


def finite_percentile(arrays: list[np.ndarray], pct: tuple[float, float]) -> tuple[float, float]:
    pieces = [arr[np.isfinite(arr)] for arr in arrays if np.isfinite(arr).any()]
    if not pieces:
        return 0.0, 1.0
    vals = np.concatenate(pieces)
    lo, hi = np.percentile(vals, pct)
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
    if lo == hi:
        hi = lo + 1
    return float(lo), float(hi)


def plot_gallery(
    triplets: list[tuple[str, Path, Path]],
    coarse_paths: dict[str, Path],
    template,
    mask: np.ndarray,
    out: Path,
) -> None:
    import matplotlib
    from rasterio.enums import Resampling

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    coarse_arrays = [read_cached_raster(coarse_paths[day], mask) for day, _, _ in triplets]
    model6_arrays = [
        read_raster_on_template(model6_path, template, mask, resampling=Resampling.bilinear)
        for _, model6_path, _ in triplets
    ]
    model8_arrays = [
        read_raster_on_template(model8_path, template, mask, resampling=Resampling.bilinear)
        for _, _, model8_path in triplets
    ]

    cvmin, cvmax = finite_percentile(coarse_arrays, (2, 98))
    mvmin, mvmax = finite_percentile(model6_arrays + model8_arrays, (2, 98))

    n = len(triplets)
    fig, axes = plt.subplots(n, 3, figsize=(10.4, max(2.0 * n, 6.5)))
    axes = np.atleast_2d(axes)
    coarse_im = None
    model_im = None

    for i, (day, _, _) in enumerate(triplets):
        specs = [
            ("Coarse SMIPS\nTotalBucket (mm)", coarse_arrays[i], cvmin, cvmax),
            ("model6 RF\nuntrained (%)", model6_arrays[i], mvmin, mvmax),
            ("model8 process\n(%)", model8_arrays[i], mvmin, mvmax),
        ]
        for j, (title, arr, vmin, vmax) in enumerate(specs):
            im = axes[i, j].imshow(arr, origin="upper", cmap="YlGnBu", vmin=vmin, vmax=vmax)
            if j == 0:
                coarse_im = im
                axes[i, j].set_ylabel(pd.Timestamp(day).strftime("%d %b %Y"), fontsize=10)
            else:
                model_im = im
            if i == 0:
                axes[i, j].set_title(title, fontsize=10)
            axes[i, j].set_xticks([])
            axes[i, j].set_yticks([])

    fig.subplots_adjust(left=0.075, right=0.86, top=0.935, bottom=0.035, wspace=0.04, hspace=0.06)
    fig.colorbar(coarse_im, cax=fig.add_axes([0.885, 0.54, 0.018, 0.34]), label="SMIPS TotalBucket (mm)")
    fig.colorbar(model_im, cax=fig.add_axes([0.885, 0.12, 0.018, 0.34]), label="Root-zone soil moisture (%)")
    fig.suptitle(
        "Tarrawarra campaign maps in the converted 5 m DEM footprint",
        fontsize=13,
        y=0.985,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}", flush=True)


def main() -> int:
    args = parse_args()
    triplets_all = discover_map_triplets(args.map_dir)
    triplets = select_dates(triplets_all, args.n_dates, args.dates)
    dates = [day for day, _, _ in triplets]
    print("selected campaign dates:", ", ".join(dates), flush=True)

    template = open_template(args.template)
    mask = template_mask(template)
    coarse_paths = ensure_coarse_smips_tifs(
        dates,
        args.coarse_dir,
        args.template,
        template,
        mask,
        args.downscaling_model_repo,
        args.feature_table,
        args.overwrite_coarse,
    )
    plot_gallery(triplets, coarse_paths, template, mask, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
