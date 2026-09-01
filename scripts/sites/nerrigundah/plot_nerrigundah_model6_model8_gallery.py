#!/usr/bin/env python3
"""Create Nerrigundah dry/wet gridded prediction overview for the manuscript."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")

DEFAULT_MAP_DIR = ROOT / "outputs/nerrigundah_model6_vs_model8/maps"
DEFAULT_TABLE = ROOT / (
    "outputs/nerrigundah_model6_vs_model8/"
    "model6_model8_combined_predictions_valid_30m_gridcell.csv"
)
DEFAULT_OUT = ROOT / (
    "reports/analyses/unified_dense_validation/figures/stage1/"
    "nerrigundah_dry_wet_model6_model8_gallery.png"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-dir", type=Path, default=DEFAULT_MAP_DIR)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--dpi", type=int, default=200)
    return parser.parse_args()


def select_dates(table: Path) -> tuple[str, str, pd.DataFrame]:
    df = pd.read_csv(table)
    obs_by_support = (
        df.groupby(["date", "point_id"], as_index=False)["obs_sm_pct"]
        .mean()
        .dropna(subset=["obs_sm_pct"])
    )
    date_mean = obs_by_support.groupby("date", as_index=False)["obs_sm_pct"].mean()
    dry = str(date_mean.loc[date_mean["obs_sm_pct"].idxmin(), "date"])
    wet = str(date_mean.loc[date_mean["obs_sm_pct"].idxmax(), "date"])
    return dry, wet, df


def read_raster(path: Path) -> np.ndarray:
    import rasterio

    with rasterio.open(path) as src:
        arr = src.read(1).astype("float32")
        nodata = src.nodata
    if nodata is not None:
        arr = np.where(arr == nodata, np.nan, arr)
    return arr


def finite_limits(arrays: list[np.ndarray]) -> tuple[float, float]:
    vals = np.concatenate([a[np.isfinite(a)] for a in arrays if np.isfinite(a).any()])
    lo, hi = np.percentile(vals, [2, 98])
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        lo, hi = float(np.nanmin(vals)), float(np.nanmax(vals))
    if lo == hi:
        hi = lo + 1.0
    return float(lo), float(hi)


def means_for_date(df: pd.DataFrame, day: str) -> dict[str, float]:
    sub = df[df["date"].astype(str) == day].copy()
    out = {
        "observed": float(
            sub.groupby("point_id", as_index=False)["obs_sm_pct"].mean()["obs_sm_pct"].mean()
        )
    }
    out.update({str(k): float(v) for k, v in sub.groupby("model_name")["pred_sm_pct"].mean().items()})
    return out


def plot(args: argparse.Namespace) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dry, wet, df = select_dates(args.table)
    dates = [dry, wet]
    arrays = {}
    for day in dates:
        arrays[(day, "model6_rf")] = read_raster(args.map_dir / f"model6_rf_{day}.tif")
        arrays[(day, "model8_process")] = read_raster(args.map_dir / f"model8_process_{day}.tif")
    vmin, vmax = finite_limits(list(arrays.values()))

    fig, axes = plt.subplots(2, 2, figsize=(7.6, 7.0))
    model_titles = {"model6_rf": "model6 RF", "model8_process": "model8 process"}
    last = None
    for row, day in enumerate(dates):
        stats = means_for_date(df, day)
        for col, model in enumerate(["model6_rf", "model8_process"]):
            ax = axes[row, col]
            last = ax.imshow(arrays[(day, model)], origin="upper", cmap="YlGnBu", vmin=vmin, vmax=vmax)
            ax.set_xticks([])
            ax.set_yticks([])
            if row == 0:
                ax.set_title(model_titles[model], fontsize=11)
            pred = stats.get(model, np.nan)
            row_label = "Driest" if row == 0 else "Wettest"
            ax.set_ylabel(
                f"{row_label}: {pd.Timestamp(day).strftime('%d %b %Y')}\n"
                f"obs {stats['observed']:.1f}%, pred {pred:.1f}%",
                fontsize=9,
            )
    if last is not None:
        cbar = fig.colorbar(last, ax=axes, shrink=0.82, pad=0.03)
        cbar.set_label("Root-zone soil moisture (%)")
    fig.suptitle("Nerrigundah gridded prediction overview", fontsize=13, fontweight="bold", y=0.985)
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, dpi=args.dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {args.out}")


def main() -> int:
    plot(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
