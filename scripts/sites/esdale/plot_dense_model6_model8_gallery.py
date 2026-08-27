#!/usr/bin/env python3
"""Dense-campaign gallery: coarse SMIPS, model6 RF and model8 process.

This mirrors the handout's `plot_downscale_gallery_model6.py` visual style, but
uses the Esdale/Tarrawarra dense-point campaign dates and places three panels on
each row:

1. coarse SMIPS total-bucket estimate, nearest-resampled to the 30 m template;
2. untrained model6 RF 30 m prediction;
3. model8 process 30 m prediction.

The coarse SMIPS panels are cached as GeoTIFFs in the output folder so later
reruns do not need to refetch SMIPS unless `--overwrite-coarse` is supplied.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_ROOT = REPO / "outputs" / "model6_vs_model8_dense"
DEFAULT_MODEL6_DIR = DEFAULT_OUTPUT_ROOT / "model6_tifs"
DEFAULT_MODEL8_DIR = DEFAULT_OUTPUT_ROOT / "model8_tifs"
DEFAULT_COARSE_DIR = DEFAULT_OUTPUT_ROOT / "coarse_smips_tifs"
DEFAULT_FIG = (
    REPO
    / "reports"
    / "sites"
    / "esdale_dense_validation"
    / "figures"
    / "dense_coarse_model6_model8_gallery.png"
)
DEFAULT_MODEL_TABLE = DEFAULT_OUTPUT_ROOT / "model6_model8_combined_predictions.csv"
NODATA = -9999.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model6-dir", type=Path, default=DEFAULT_MODEL6_DIR)
    parser.add_argument("--model8-dir", type=Path, default=DEFAULT_MODEL8_DIR)
    parser.add_argument("--coarse-dir", type=Path, default=DEFAULT_COARSE_DIR)
    parser.add_argument("--model-table", type=Path, default=DEFAULT_MODEL_TABLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_FIG)
    parser.add_argument("--padding-deg", type=float, default=0.002)
    parser.add_argument(
        "--dates",
        nargs="+",
        default=None,
        help="Optional explicit dates to plot, e.g. 2025-05-21 2025-07-11.",
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
    stem = path.stem
    # Handles untrained_model6_2025-04-30 and model8_process_2025-04-30.
    return stem[-10:]


def discover_date_triplets(model6_dir: Path, model8_dir: Path) -> list[tuple[str, Path, Path]]:
    m6 = {date_from_name(path): path for path in model6_dir.glob("untrained_model6_*.tif") if not path.name.startswith("._")}
    m8 = {date_from_name(path): path for path in model8_dir.glob("model8_process_*.tif") if not path.name.startswith("._")}
    dates = sorted(set(m6).intersection(m8))
    if not dates:
        raise SystemExit(f"No matched model6/model8 TIF dates found in {model6_dir} and {model8_dir}")
    missing6 = sorted(set(m8) - set(m6))
    missing8 = sorted(set(m6) - set(m8))
    if missing6:
        print(f"warning: model8 dates missing model6 TIFs: {missing6}", flush=True)
    if missing8:
        print(f"warning: model6 dates missing model8 TIFs: {missing8}", flush=True)
    return [(day, m6[day], m8[day]) for day in dates]


def select_dates(
    triplets: list[tuple[str, Path, Path]],
    explicit_dates: list[str] | None,
) -> list[tuple[str, Path, Path]]:
    if not explicit_dates:
        return triplets
    by_date = {day: (day, model6_path, model8_path) for day, model6_path, model8_path in triplets}
    missing = [day for day in explicit_dates if day not in by_date]
    if missing:
        raise SystemExit(f"Requested dates have no paired Esdale maps: {missing}")
    return [by_date[day] for day in explicit_dates]


def bbox_from_model_table(path: Path, padding_deg: float) -> tuple[float, float, float, float]:
    df = pd.read_csv(path).dropna(subset=["lon", "lat"])
    return (
        float(df["lon"].min() - padding_deg),
        float(df["lat"].min() - padding_deg),
        float(df["lon"].max() + padding_deg),
        float(df["lat"].max() + padding_deg),
    )


def open_template(path: Path):
    import rioxarray  # noqa: F401

    return rioxarray.open_rasterio(path, masked=True).squeeze("band", drop=True).load()


def read_raster(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr


def write_raster_like(path: Path, array: np.ndarray, template_path: Path, description: str) -> None:
    import rasterio

    with rasterio.open(template_path) as src:
        profile = src.profile.copy()
    profile.update(driver="GTiff", count=1, dtype="float32", nodata=NODATA, compress="deflate", predictor=3)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(np.where(np.isfinite(array), array, NODATA).astype("float32"), 1)
        dst.set_band_description(1, description)


def ensure_coarse_smips_tifs(
    dates: list[str],
    coarse_dir: Path,
    template_path: Path,
    bbox: tuple[float, float, float, float],
    downscaling_model_repo: Path,
    overwrite: bool,
) -> dict[str, Path]:
    coarse_dir.mkdir(parents=True, exist_ok=True)
    out = {day: coarse_dir / f"coarse_smips_totalbucket_{day}.tif" for day in dates}
    if all(path.exists() for path in out.values()) and not overwrite:
        print(f"using cached coarse SMIPS TIFs in {coarse_dir}", flush=True)
        return out

    if str(downscaling_model_repo) not in sys.path:
        sys.path.insert(0, str(downscaling_model_repo))

    from rasterio.enums import Resampling
    from emt.smips import smips_cube

    template = open_template(template_path)
    print("fetching coarse SMIPS totalbucket for gallery dates ...", flush=True)
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
        # Nearest keeps the coarse pixel blocks visible, matching the intent of
        # a "coarse estimate" panel rather than smoothing it into a fine field.
        coarse_on_template = da.rio.reproject_match(template, resampling=Resampling.nearest)
        write_raster_like(path, coarse_on_template.values.astype("float32"), template_path, "smips_totalbucket_mm")
        print(f"  wrote {path}", flush=True)
    return out


def finite_percentile(arrays: list[np.ndarray], pct: tuple[float, float]) -> tuple[float, float]:
    vals = np.concatenate([arr[np.isfinite(arr)] for arr in arrays if np.isfinite(arr).any()])
    if vals.size == 0:
        return 0.0, 1.0
    lo, hi = np.percentile(vals, pct)
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
    if lo == hi:
        hi = lo + 1
    return float(lo), float(hi)


def plot_gallery(triplets: list[tuple[str, Path, Path]], coarse_paths: dict[str, Path], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    coarse_arrays = [read_raster(coarse_paths[day]) for day, _, _ in triplets]
    model6_arrays = [read_raster(model6_path) for _, model6_path, _ in triplets]
    model8_arrays = [read_raster(model8_path) for _, _, model8_path in triplets]

    cvmin, cvmax = finite_percentile(coarse_arrays, (2, 98))
    mvmin, mvmax = finite_percentile(model6_arrays + model8_arrays, (2, 98))

    n = len(triplets)
    fig, axes = plt.subplots(n, 3, figsize=(10.2, max(2.05 * n, 6.5)))
    axes = np.atleast_2d(axes)
    coarse_im = None
    model_im = None
    for i, (day, _, _) in enumerate(triplets):
        arrays = [coarse_arrays[i], model6_arrays[i], model8_arrays[i]]
        specs = [
            ("Coarse SMIPS\nTotalBucket (mm)", arrays[0], "YlGnBu", cvmin, cvmax),
            ("model6 RF\nuntrained 30 m (%)", arrays[1], "YlGnBu", mvmin, mvmax),
            ("model8 process\n30 m (%)", arrays[2], "YlGnBu", mvmin, mvmax),
        ]
        for j, (title, arr, cmap, vmin, vmax) in enumerate(specs):
            im = axes[i, j].imshow(arr, origin="upper", cmap=cmap, vmin=vmin, vmax=vmax)
            if j == 0:
                coarse_im = im
                axes[i, j].set_ylabel(pd.Timestamp(day).strftime("%d %b %Y"), fontsize=10)
            else:
                model_im = im
            if i == 0:
                axes[i, j].set_title(title, fontsize=10)
            axes[i, j].set_xticks([])
            axes[i, j].set_yticks([])

    fig.subplots_adjust(left=0.075, right=0.86, top=0.935, bottom=0.035, wspace=0.035, hspace=0.055)
    fig.colorbar(coarse_im, cax=fig.add_axes([0.885, 0.54, 0.018, 0.34]), label="SMIPS TotalBucket (mm)")
    fig.colorbar(model_im, cax=fig.add_axes([0.885, 0.12, 0.018, 0.34]), label="Root-zone soil moisture (%)")
    fig.suptitle(
        "Dense campaign soil-moisture maps: coarse estimate vs model6 RF vs model8 process",
        fontsize=13,
        y=0.985,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out}", flush=True)


def main() -> int:
    args = parse_args()
    triplets = select_dates(discover_date_triplets(args.model6_dir, args.model8_dir), args.dates)
    dates = [day for day, _, _ in triplets]
    bbox = bbox_from_model_table(args.model_table, args.padding_deg)
    coarse_paths = ensure_coarse_smips_tifs(
        dates,
        args.coarse_dir,
        triplets[0][1],
        bbox,
        args.downscaling_model_repo,
        args.overwrite_coarse,
    )
    plot_gallery(triplets, coarse_paths, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
