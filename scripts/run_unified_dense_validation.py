#!/usr/bin/env python3
"""Unified dense-point validation protocol for DMM model comparisons.

This is the top-level runner for the PDF plan in
``docs/Downscaling moisture validation plan.pdf``.  It keeps the two scientific
questions separate:

Stage 1
    Independent model-agnostic validation on dense point datasets.

Stage 2
    Local calibration / local training-data "spiking" sensitivity, with strict
    spatial+temporal blocking treated as the primary transfer test.

The script intentionally uses existing cached model prediction tables and
GeoTIFF products.  It does not retrain or refetch model rasters unless a helper
gallery script needs a cached coarse panel that is not already present.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT_DIR = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_local_spiking_experiment as spiking  # noqa: E402
from dmm_validation.metrics import metric_table  # noqa: E402
from dmm_validation.paired import paired_model_comparison, paired_point_differences  # noqa: E402
from dmm_validation.plots import make_all_figures  # noqa: E402
from dmm_validation.reporting import markdown_table, write_geojson_points  # noqa: E402
from dmm_validation.schema import default_pair_keys  # noqa: E402
from dmm_validation.terrain import add_terrain_strata, detect_terrain_columns  # noqa: E402


DEFAULT_OUTDIR = ROOT / "outputs" / "unified_dense_validation"
DEFAULT_REPORT_DIR = ROOT / "reports" / "unified_dense_validation"
PLAN_PDF = ROOT / "docs" / "Downscaling moisture validation plan.pdf"
PLAN_TEXT = ROOT / "docs" / "Downscaling moisture validation plan.txt"

SITE_NOTES = {
    "Esdale": (
        "Autumn/winter 2025 dense campaign. Strongest spatial/terrain coverage "
        "among the modern validation points, but only nine sampling dates are present."
    ),
    "Tarrawarra": (
        "Very dense 1995/96 campaign. The existing model6 run has a known SMIPS-zero "
        "caveat, so model6 skill here should be read partly as a missing coarse-anchor "
        "ablation rather than a normal model6 prediction."
    ),
    "Llara": (
        "Thirty-two profile-mean probes across two paddocks from 2021–2024. Strongest "
        "temporal/seasonal coverage. Point-level SMIPS-derived columns are present, "
        "but full gridded Llara model GeoTIFFs are not currently cached."
    ),
}

MODEL_LABELS = {
    "model6_rf": "model6 RF",
    "model8_process": "model8 process",
}

STAGE1_FIGURES = [
    (
        "figures/stage1/site_model_overall_skill.png",
        "Stage 1 overall model skill by site",
        "Independent pooled skill for each model/site, before any local calibration.",
    ),
    (
        "figures/stage1/seasonal_bias_by_site_model.png",
        "Seasonal bias by site and model",
        "Mean residual by season; positive values mean overprediction.",
    ),
    (
        "figures/stage1/wetness_quantile_bias.png",
        "Dry/wet observed-state bias",
        "Bias in driest and wettest observed moisture quartiles.",
    ),
    (
        "figures/stage1/esdale_coarse_model6_model8_gallery.png",
        "Esdale raster-native dry/wet prediction gallery",
        "Actual cached coarse/model6/model8 gridded products for Esdale dates.",
    ),
    (
        "figures/stage1/tarrawarra_coarse_model6_model8_gallery.png",
        "Tarrawarra raster-native prediction gallery",
        "Actual cached gridded model products plotted in the Tarrawarra 5 m DEM footprint.",
    ),
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the unified dense-point DMM validation protocol.")
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--terrain-cols", default="auto")
    parser.add_argument("--terrain-quantiles", type=int, default=3)
    parser.add_argument("--bootstrap", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--stage2-budgets", default="1,3,5,10,25%,50%,all")
    parser.add_argument("--stage2-random-reps", type=int, default=20)
    parser.add_argument("--train-date-fraction", type=float, default=0.33)
    parser.add_argument("--min-train-dates", type=int, default=3)
    parser.add_argument("--skip-stage2", action="store_true")
    parser.add_argument("--skip-galleries", action="store_true")
    return parser.parse_args(argv)


def safe_name(text: str) -> str:
    return str(text).lower().replace(" ", "_").replace("/", "_")


def load_site_frames() -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for site, path in spiking.SITE_PATHS.items():
        df = spiking.load_site(site, path)
        df["model_name"] = df["base_model"]
        frames[site] = df
    return frames


def site_inventory(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for site, df in frames.items():
        dates = sorted(df["date"].unique())
        train_dates, future_dates = spiking.split_dates(dates, 0.33, 3)
        point_summary = spiking.site_point_summary(df, train_dates, future_dates)
        smips_cols = [c for c in df.columns if c.startswith("smips")]
        smips_present = bool(smips_cols and df[smips_cols].notna().any().any())
        rows.append(
            {
                "site": site,
                "source_table": str(spiking.SITE_PATHS[site]),
                "rows": int(len(df)),
                "models": ",".join(sorted(df["base_model"].unique())),
                "points_unique": int(df["point_id"].nunique()),
                "dates": int(len(dates)),
                "date_min": min(dates),
                "date_max": max(dates),
                "seasons": ",".join(sorted(map(str, df["season"].dropna().unique()))),
                "eligible_points_stage2": int(point_summary["eligible"].sum()),
                "smips_columns_present": "yes" if smips_present else "no",
                "note": SITE_NOTES.get(site, ""),
            }
        )
    return pd.DataFrame(rows)


def point_metrics_with_location(df: pd.DataFrame) -> pd.DataFrame:
    metrics = metric_table(df, ["site", "base_model", "point_id"])
    loc = (
        df.groupby(["site", "base_model", "point_id"], as_index=False, observed=True)
        .agg(lon=("lon", "mean"), lat=("lat", "mean"))
    )
    return loc.merge(metrics, on=["site", "base_model", "point_id"], how="left")


def moisture_quantile_bias(df: pd.DataFrame) -> pd.DataFrame:
    pieces = []
    for site, g in df.groupby("site", observed=True):
        tmp = g.copy()
        try:
            tmp["obs_moisture_quantile"] = pd.qcut(
                tmp["obs_sm_pct"],
                q=4,
                labels=["dry_q1", "q2", "q3", "wet_q4"],
                duplicates="drop",
            )
        except ValueError:
            continue
        table = (
            tmp.groupby(["site", "base_model", "obs_moisture_quantile"], as_index=False, observed=True)
            .agg(
                n=("residual", "size"),
                obs_mean=("obs_sm_pct", "mean"),
                pred_mean=("pred_sm_pct", "mean"),
                bias=("residual", "mean"),
                rmse=("sq_error", lambda x: float(np.sqrt(np.mean(x)))),
                ubrmse=(
                    "residual",
                    lambda x: float(
                        np.sqrt(max(np.mean(np.square(x)) - np.square(np.mean(x)), 0.0))
                    ),
                ),
                mae=("abs_error", "mean"),
            )
        )
        pieces.append(table)
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def terrain_metric_tables(
    frames: dict[str, pd.DataFrame],
    requested_cols: str,
    q: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, list[dict]], dict[str, pd.DataFrame]]:
    metric_pieces = []
    notable_rows = []
    metadata_by_site: dict[str, list[dict]] = {}
    stratified_frames: dict[str, pd.DataFrame] = {}

    for site, df in frames.items():
        terrain_cols = detect_terrain_columns(df, requested_cols)
        stratified, metadata = add_terrain_strata(df, terrain_cols, q=q)
        metadata_by_site[site] = metadata
        stratified_frames[site] = stratified

        for meta in metadata:
            stratum_col = meta["stratum_col"]
            table = metric_table(stratified.dropna(subset=[stratum_col]), ["site", "base_model", stratum_col])
            if table.empty:
                continue
            table.insert(2, "terrain_var", meta["terrain_var"])
            table = table.rename(columns={stratum_col: "terrain_stratum"})
            metric_pieces.append(table)

            spread = (
                table.groupby(["site", "base_model", "terrain_var"], as_index=False, observed=True)
                .agg(
                    n_strata=("terrain_stratum", "nunique"),
                    bias_min=("bias", "min"),
                    bias_max=("bias", "max"),
                    rmse_min=("rmse", "min"),
                    rmse_max=("rmse", "max"),
                    nse_min=("nse", "min"),
                    nse_max=("nse", "max"),
                )
            )
            spread["bias_range"] = spread["bias_max"] - spread["bias_min"]
            spread["rmse_range"] = spread["rmse_max"] - spread["rmse_min"]
            spread["nse_range"] = spread["nse_max"] - spread["nse_min"]
            spread["notability_score"] = spread["bias_range"].abs() + spread["rmse_range"].abs()
            notable_rows.append(spread)

    terrain_metrics = pd.concat(metric_pieces, ignore_index=True) if metric_pieces else pd.DataFrame()
    notable = pd.concat(notable_rows, ignore_index=True) if notable_rows else pd.DataFrame()
    if not notable.empty:
        notable = notable.sort_values(["site", "base_model", "notability_score"], ascending=[True, True, False])
    return terrain_metrics, notable, metadata_by_site, stratified_frames


def paired_tables(frames: dict[str, pd.DataFrame], n_boot: int, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    overall = []
    by_season = []
    point_diff = []
    for site, df in frames.items():
        key_cols = default_pair_keys(df)
        p_all = paired_model_comparison(df, key_cols, n_boot=n_boot, seed=seed)
        p_season = paired_model_comparison(df, key_cols, ["season"], n_boot=n_boot, seed=seed)
        p_point = paired_point_differences(df, key_cols)
        for table in [p_all, p_season, p_point]:
            if not table.empty:
                table.insert(0, "site", site)
        overall.append(p_all)
        by_season.append(p_season)
        point_diff.append(p_point)
    return (
        pd.concat(overall, ignore_index=True) if overall else pd.DataFrame(),
        pd.concat(by_season, ignore_index=True) if by_season else pd.DataFrame(),
        pd.concat(point_diff, ignore_index=True) if point_diff else pd.DataFrame(),
    )


def _setup_plotting():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "legend.fontsize": 8,
        }
    )
    return plt


def plot_stage1_site_skill(overall: pd.DataFrame, fig_dir: Path) -> Path:
    plt = _setup_plotting()
    fig_dir.mkdir(parents=True, exist_ok=True)
    sites = [s for s in ["Esdale", "Tarrawarra", "Llara"] if s in set(overall["site"])]
    models = [m for m in ["model6_rf", "model8_process"] if m in set(overall["base_model"])]
    x = np.arange(len(sites))
    width = 0.34
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    metrics = [("nse", "NSE / R²"), ("rmse", "RMSE (%)"), ("bias", "Bias: pred - obs (%)")]
    colors = {"model6_rf": "#64748b", "model8_process": "#0f766e"}
    for ax, (metric, label) in zip(axes, metrics):
        for i, model in enumerate(models):
            vals = overall[overall["base_model"] == model].set_index("site").reindex(sites)[metric]
            ax.bar(x + (i - 0.5) * width, vals, width=width, color=colors.get(model), label=MODEL_LABELS.get(model, model))
        ax.axhline(0, color="0.25", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(sites, rotation=20, ha="right")
        ax.set_ylabel(label)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(frameon=False)
    fig.suptitle("Stage 1 independent dense-point validation: pooled skill")
    fig.tight_layout()
    out = fig_dir / "site_model_overall_skill.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_seasonal_bias(seasonal: pd.DataFrame, fig_dir: Path) -> Path:
    plt = _setup_plotting()
    fig_dir.mkdir(parents=True, exist_ok=True)
    core = seasonal.copy()
    core["label"] = core["site"].astype(str) + "\n" + core["base_model"].map(lambda x: MODEL_LABELS.get(x, x))
    seasons = [s for s in ["spring", "summer", "autumn", "winter"] if s in set(core["season"].astype(str))]
    labels = core[["site", "base_model", "label"]].drop_duplicates()["label"].tolist()
    mat = np.full((len(labels), len(seasons)), np.nan)
    for i, label in enumerate(labels):
        for j, season in enumerate(seasons):
            vals = core[(core["label"] == label) & (core["season"].astype(str) == season)]["bias"]
            if not vals.empty:
                mat[i, j] = float(vals.iloc[0])
    vmax = np.nanmax(np.abs(mat)) if np.isfinite(mat).any() else 1.0
    vmax = max(vmax, 1.0)
    fig, ax = plt.subplots(figsize=(8.5, max(4, 0.45 * len(labels) + 1.8)))
    im = ax.imshow(mat, cmap="RdBu", vmin=-vmax, vmax=vmax)
    ax.set_xticks(np.arange(len(seasons)))
    ax.set_xticklabels(seasons)
    ax.set_yticks(np.arange(len(labels)))
    ax.set_yticklabels(labels)
    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            if np.isfinite(mat[i, j]):
                ax.text(j, i, f"{mat[i, j]:.1f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax, label="Mean residual (%)")
    ax.set_title("Stage 1 seasonal bias: prediction minus observation")
    fig.tight_layout()
    out = fig_dir / "seasonal_bias_by_site_model.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_wetness_bias(wetness: pd.DataFrame, fig_dir: Path) -> Path | None:
    if wetness.empty:
        return None
    plt = _setup_plotting()
    fig_dir.mkdir(parents=True, exist_ok=True)
    core = wetness[wetness["obs_moisture_quantile"].astype(str).isin(["dry_q1", "wet_q4"])].copy()
    if core.empty:
        return None
    sites = [s for s in ["Esdale", "Tarrawarra", "Llara"] if s in set(core["site"])]
    fig, axes = plt.subplots(len(sites), 1, figsize=(10, max(3.0 * len(sites), 4)), sharex=True)
    axes = np.atleast_1d(axes)
    x_labels = ["model6 dry", "model6 wet", "model8 dry", "model8 wet"]
    x = np.arange(len(x_labels))
    for ax, site in zip(axes, sites):
        vals = []
        for model in ["model6_rf", "model8_process"]:
            for q in ["dry_q1", "wet_q4"]:
                sub = core[(core["site"] == site) & (core["base_model"] == model) & (core["obs_moisture_quantile"].astype(str) == q)]
                vals.append(float(sub["bias"].iloc[0]) if not sub.empty else np.nan)
        ax.bar(x, vals, color=["#94a3b8", "#475569", "#5eead4", "#0f766e"])
        ax.axhline(0, color="0.25", linewidth=0.8)
        ax.set_title(site)
        ax.set_ylabel("Bias (%)")
        ax.grid(axis="y", alpha=0.25)
    axes[-1].set_xticks(x)
    axes[-1].set_xticklabels(x_labels, rotation=20, ha="right")
    fig.suptitle("Dry and wet observed-state bias")
    fig.tight_layout()
    out = fig_dir / "wetness_quantile_bias.png"
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    return out


def _idw_grid(x: np.ndarray, y: np.ndarray, z: np.ndarray, n_grid: int = 110) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    x = x[ok]
    y = y[ok]
    z = z[ok]
    if z.size < 3:
        raise ValueError("need at least three finite points for IDW map")
    xi = np.linspace(x.min(), x.max(), n_grid)
    yi = np.linspace(y.min(), y.max(), n_grid)
    xx, yy = np.meshgrid(xi, yi)
    grid = np.empty_like(xx, dtype=float)
    chunk = 1500
    targets = np.column_stack([xx.ravel(), yy.ravel()])
    out = np.empty(targets.shape[0], dtype=float)
    for start in range(0, targets.shape[0], chunk):
        part = targets[start : start + chunk]
        dx = part[:, None, 0] - x[None, :]
        dy = part[:, None, 1] - y[None, :]
        dist2 = dx * dx + dy * dy
        zero = dist2 <= 1e-18
        weights = 1.0 / np.maximum(dist2, 1e-18)
        vals = (weights @ z) / weights.sum(axis=1)
        if zero.any():
            rows, cols = np.where(zero)
            vals[rows] = z[cols]
        out[start : start + chunk] = vals
    grid[:, :] = out.reshape(xx.shape)
    return xi, yi, grid


def plot_interpolated_quality_surfaces(point_metrics: pd.DataFrame, fig_dir: Path) -> list[Path]:
    plt = _setup_plotting()
    out_paths: list[Path] = []
    surf_dir = fig_dir / "quality_surfaces"
    surf_dir.mkdir(parents=True, exist_ok=True)
    for (site, model), sub in point_metrics.groupby(["site", "base_model"], observed=True):
        for metric, cmap in [("nse", "coolwarm"), ("rmse", "viridis"), ("bias", "RdBu")]:
            vals = pd.to_numeric(sub[metric], errors="coerce").to_numpy(dtype=float)
            if np.isfinite(vals).sum() < 3:
                continue
            try:
                xi, yi, grid = _idw_grid(sub["lon"].to_numpy(dtype=float), sub["lat"].to_numpy(dtype=float), vals)
            except ValueError:
                continue
            finite = vals[np.isfinite(vals)]
            if metric == "bias":
                vmax = np.nanpercentile(np.abs(finite), 95)
                vmin, vmax = -max(vmax, 1.0), max(vmax, 1.0)
            else:
                vmin, vmax = np.nanpercentile(finite, [5, 95])
                if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
                    vmin, vmax = float(np.nanmin(finite)), float(np.nanmax(finite))
            fig, ax = plt.subplots(figsize=(6.2, 5.2))
            im = ax.imshow(
                grid,
                extent=[xi.min(), xi.max(), yi.min(), yi.max()],
                origin="lower",
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                aspect="auto",
            )
            ax.scatter(sub["lon"], sub["lat"], s=8 if len(sub) > 500 else 24, facecolor="white", edgecolor="black", linewidth=0.25)
            ax.set_title(f"{site} {MODEL_LABELS.get(model, model)} point-level {metric} (IDW)")
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")
            fig.colorbar(im, ax=ax, label=metric)
            fig.tight_layout()
            out = surf_dir / f"{safe_name(site)}_{safe_name(model)}_{metric}_idw_surface.png"
            fig.savefig(out, dpi=180, bbox_inches="tight")
            plt.close(fig)
            out_paths.append(out)
    return out_paths


def run_gallery(script_name: str, out_path: Path) -> tuple[Path | None, str | None]:
    script = ROOT / "reports" / "figure_generation" / script_name
    if not script.exists():
        return None, f"missing gallery script: {script}"
    cmd = [sys.executable, str(script), "--out", str(out_path)]
    try:
        subprocess.run(cmd, cwd=ROOT, check=True, text=True, capture_output=True)
        return out_path if out_path.exists() else None, None
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or exc.stdout or str(exc)).strip()
        return None, msg[-1000:]


def run_stage1(
    frames: dict[str, pd.DataFrame],
    outdir: Path,
    report_figdir: Path,
    *,
    terrain_cols: str,
    terrain_quantiles: int,
    bootstrap: int,
    seed: int,
    skip_galleries: bool,
) -> dict[str, object]:
    outdir.mkdir(parents=True, exist_ok=True)
    fig_dir = report_figdir / "stage1"
    fig_dir.mkdir(parents=True, exist_ok=True)

    combined = pd.concat(frames.values(), ignore_index=True, sort=False)
    combined.to_csv(outdir / "combined_model_agnostic_predictions.csv", index=False)

    inventory = site_inventory(frames)
    overall = metric_table(combined, ["site", "base_model"])
    seasonal = metric_table(combined, ["site", "base_model", "season"])
    season_year = metric_table(combined, ["site", "base_model", "season", "season_year"])
    point_metrics = point_metrics_with_location(combined)
    point_season = metric_table(combined, ["site", "base_model", "point_id", "season"])
    wetness = moisture_quantile_bias(combined)
    terrain_metrics, notable_terrain, terrain_metadata, stratified_frames = terrain_metric_tables(
        frames,
        terrain_cols,
        terrain_quantiles,
    )
    paired_overall, paired_season, paired_points = paired_tables(frames, bootstrap, seed)

    tables = {
        "site_inventory.csv": inventory,
        "metrics_overall_by_site_model.csv": overall,
        "metrics_by_site_model_season.csv": seasonal,
        "metrics_by_site_model_season_year.csv": season_year,
        "metrics_by_point.csv": point_metrics,
        "metrics_by_point_season.csv": point_season,
        "bias_by_observed_wetness_quantile.csv": wetness,
        "metrics_by_terrain_strata.csv": terrain_metrics,
        "notable_terrain_error_strata.csv": notable_terrain,
        "paired_model_comparison_overall.csv": paired_overall,
        "paired_model_comparison_by_season.csv": paired_season,
        "paired_point_error_differences.csv": paired_points,
    }
    for name, table in tables.items():
        table.to_csv(outdir / name, index=False)
    (outdir / "terrain_strata_metadata.json").write_text(json.dumps(terrain_metadata, indent=2), encoding="utf-8")
    write_geojson_points(point_metrics, outdir / "point_metrics.geojson")
    if not paired_points.empty:
        write_geojson_points(paired_points, outdir / "paired_point_error_differences.geojson")

    figure_paths: list[Path] = []
    figure_paths.append(plot_stage1_site_skill(overall, fig_dir))
    figure_paths.append(plot_seasonal_bias(seasonal, fig_dir))
    wet_fig = plot_wetness_bias(wetness, fig_dir)
    if wet_fig is not None:
        figure_paths.append(wet_fig)
    figure_paths.extend(plot_interpolated_quality_surfaces(point_metrics, fig_dir))

    # Per-site diagnostics using the model-agnostic plotting utilities.
    for site, df in stratified_frames.items():
        site_dir = fig_dir / "site_diagnostics" / safe_name(site)
        site_point = point_metrics[point_metrics["site"] == site].rename(columns={"base_model": "model_name"}).copy()
        site_point["model_name"] = site_point["model_name"].astype(str)
        site_diff = paired_points[paired_points["site"] == site].drop(columns=["site"], errors="ignore")
        plot_df = df.copy()
        plot_df["model_name"] = plot_df["base_model"]
        make_all_figures(plot_df, site_point, site_diff, terrain_metadata.get(site, []), site_dir)

    gallery_warnings: list[str] = []
    if not skip_galleries:
        for script_name, filename in [
            ("plot_dense_model6_model8_gallery.py", "esdale_coarse_model6_model8_gallery.png"),
            ("plot_tarrawarra_model6_model8_gallery.py", "tarrawarra_coarse_model6_model8_gallery.png"),
        ]:
            path, warning = run_gallery(script_name, fig_dir / filename)
            if path is not None:
                figure_paths.append(path)
            if warning:
                gallery_warnings.append(f"{script_name}: {warning}")

    summary = {
        "n_rows": int(len(combined)),
        "sites": sorted(frames),
        "models": sorted(combined["base_model"].unique()),
        "figures": [str(p) for p in figure_paths],
        "gallery_warnings": gallery_warnings,
    }
    (outdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "inventory": inventory,
        "overall": overall,
        "seasonal": seasonal,
        "wetness": wetness,
        "notable_terrain": notable_terrain,
        "paired_overall": paired_overall,
        "figures": figure_paths,
        "gallery_warnings": gallery_warnings,
    }


def run_stage2(args: argparse.Namespace, outdir: Path, report_dir: Path) -> None:
    spiking.main(
        [
            "--outdir",
            str(outdir),
            "--report",
            str(report_dir / "stage2_local_spiking_report.md"),
            "--report-figdir",
            str(report_dir / "figures" / "stage2_local_spiking"),
            "--budgets",
            args.stage2_budgets,
            "--random-reps",
            str(args.stage2_random_reps),
            "--seed",
            str(args.seed),
            "--train-date-fraction",
            str(args.train_date_fraction),
            "--min-train-dates",
            str(args.min_train_dates),
        ]
    )


def target_nse_table(summary: pd.DataFrame, threshold: float = 0.4) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    strict = summary[
        (summary["block"] == "spatiotemporal_block")
        & (summary["method"] != "global")
        & (summary["selection_strategy"].isin(["random", "landscape_wetdry_prior", "global_prediction_extremes"]))
    ].copy()
    if strict.empty:
        return pd.DataFrame()
    strict["meets_target"] = strict["nse_median"] >= threshold
    rows = []
    for (site, model), group in strict.groupby(["site", "base_model"], observed=True):
        hits = group[group["meets_target"]].sort_values(["calibration_points", "rmse_median"])
        if hits.empty:
            best = group.sort_values(["nse_median", "rmse_median"], ascending=[False, True]).iloc[0]
            row = best.to_dict()
            row["target_status"] = f"not reached; best NSE {best['nse_median']:.3f}"
        else:
            best = hits.iloc[0]
            row = best.to_dict()
            row["target_status"] = f"reached NSE ≥ {threshold:.1f}"
        rows.append(row)
    cols = [
        "site",
        "base_model",
        "target_status",
        "selection_strategy",
        "budget_label",
        "calibration_points",
        "method",
        "nse_median",
        "rmse_median",
        "bias_median",
        "rmse_gain_median",
        "delta_nse_median",
        "n_replicates",
    ]
    return pd.DataFrame(rows)[[c for c in cols if c in rows[0]]]


def best_stage2_table(summary: pd.DataFrame) -> pd.DataFrame:
    if summary.empty:
        return pd.DataFrame()
    strict = summary[(summary["block"] == "spatiotemporal_block") & (summary["method"] != "global")].copy()
    if strict.empty:
        return pd.DataFrame()
    best = strict.sort_values(["site", "base_model", "rmse_median"]).groupby(["site", "base_model"], as_index=False).first()
    cols = [
        "site",
        "base_model",
        "selection_strategy",
        "budget_label",
        "calibration_points",
        "method",
        "nse_median",
        "rmse_median",
        "ubrmse_median",
        "bias_median",
        "rmse_gain_median",
        "delta_nse_median",
        "delta_abs_bias_median",
        "n_replicates",
    ]
    return best[[c for c in cols if c in best.columns]]


def render_figures(report_dir: Path, figure_specs: list[tuple[str, str, str]]) -> str:
    blocks = []
    for rel, title, caption in figure_specs:
        path = report_dir / rel
        if not path.exists():
            continue
        blocks.extend([f"### {title}", "", f"![{title}]({Path(rel).as_posix()})", "", caption, ""])
    return "\n".join(blocks).strip()


def write_unified_report(
    report_path: Path,
    stage1: dict[str, object],
    stage2_outdir: Path,
    args: argparse.Namespace,
) -> None:
    report_dir = report_path.parent
    stage2_summary_path = stage2_outdir / "local_calibration_summary.csv"
    stage2_resp_path = stage2_outdir / "process_vs_statistical_responsiveness.csv"
    stage2_summary = pd.read_csv(stage2_summary_path) if stage2_summary_path.exists() else pd.DataFrame()
    stage2_resp = pd.read_csv(stage2_resp_path) if stage2_resp_path.exists() else pd.DataFrame()
    target = target_nse_table(stage2_summary, threshold=0.4)
    best = best_stage2_table(stage2_summary)
    notable_terrain = stage1["notable_terrain"]
    if isinstance(notable_terrain, pd.DataFrame) and not notable_terrain.empty:
        notable_terrain_report = notable_terrain.groupby(["site", "base_model"], as_index=False, observed=True).head(5)
    else:
        notable_terrain_report = pd.DataFrame()

    random_learning = (
        stage2_summary[
            (stage2_summary["block"] == "spatiotemporal_block")
            & (stage2_summary["selection_strategy"] == "random")
            & (stage2_summary["method"] != "global")
        ][
            [
                "site",
                "base_model",
                "budget_label",
                "calibration_points",
                "method",
                "nse_median",
                "rmse_median",
                "rmse_gain_median",
                "bias_median",
                "n_replicates",
            ]
        ]
        if not stage2_summary.empty
        else pd.DataFrame()
    )
    if not random_learning.empty:
        random_learning = random_learning.sort_values(["site", "base_model", "calibration_points", "method"])

    resp_core = (
        stage2_resp[
            (stage2_resp["block"] == "spatiotemporal_block")
            & (stage2_resp["selection_strategy"] == "random")
        ][
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
            ]
        ]
        if not stage2_resp.empty
        else pd.DataFrame()
    )

    figure_specs = STAGE1_FIGURES + [
        (
            "figures/stage2_local_spiking/baseline_site_model_skill.png",
            "Stage 2 global baseline skill",
            "Uncalibrated baseline for the same held-out design used by local spiking.",
        ),
        (
            "figures/stage2_local_spiking/random_spatiotemporal_learning_curves_rmse_gain.png",
            "Stage 2 random sparse-sensor learning curves",
            "Median RMSE gain under the strict spatial+temporal block.",
        ),
        (
            "figures/stage2_local_spiking/one_sensor_strategy_comparison_rmse_gain.png",
            "Stage 2 one-sensor placement comparison",
            "One-sensor strategy comparison under the strict block.",
        ),
        (
            "figures/stage2_local_spiking/process_vs_statistical_responsiveness_random.png",
            "Process-vs-statistical local calibration responsiveness",
            "Positive values indicate model8 gained more from the same sparse local information budget.",
        ),
    ]

    gallery_warnings = stage1.get("gallery_warnings") or []
    gallery_warning_text = "\n".join(f"- {w}" for w in gallery_warnings) if gallery_warnings else "_None._"

    body = f"""# Unified dense-point validation and local-spiking report

This report resets the earlier ad hoc three-site sparse local-calibration work
into the two-stage protocol described in
`docs/Downscaling moisture validation plan.pdf`.

The two stages are deliberately kept separate:

1. **Stage 1 — independent validation:** all dense point/date observations are
   used only as external validation. No local measurements are supplied to the
   models or calibration layers.
2. **Stage 2 — local-spiking sensitivity:** small controlled subsets of local
   points are used as calibration spikes, and validation is performed on held-out
   points/dates. The strict `spatiotemporal_block` is treated as the primary
   transfer test.

## Data inventory

{markdown_table(stage1["inventory"], max_rows=20)}

Important caveats:

- Tarrawarra is retained because it is uniquely dense, but the existing model6
  run has a known SMIPS-zero caveat. Treat Tarrawarra model6 as partly a
  missing-coarse-anchor stress test.
- Llara has SMIPS-derived point-level predictors in the validation tables, but
  full gridded model6/model8 GeoTIFF prediction maps are not currently cached.
  Llara map outputs therefore focus on point-level validation and interpolated
  point-quality surfaces, not full raster-native model surfaces.
- The PDF says Esdale has 540 points; the current model-agnostic prediction
  table contains 79 unique point IDs and 560 model6 rows across nine dates. This
  likely reflects a point-vs-observation wording mismatch and should be checked
  by a human before publication.

## Stage 1 — independent dense-point validation

### Overall model skill

{markdown_table(stage1["overall"], max_rows=20)}

### Seasonal skill

{markdown_table(stage1["seasonal"], max_rows=40)}

### Dry/wet observed-state bias

{markdown_table(stage1["wetness"], max_rows=40)}

### Most notable terrain/model-input strata

The table below ranks terrain/model-input strata by the range of bias and RMSE
across low/mid/high strata within each site/model. These are diagnostic
validation covariates rather than a claim that every variable is used by every
model internally.

{markdown_table(notable_terrain_report, max_rows=40)}

### Paired model comparison

Negative `mean_delta_abs_error` means model6 had lower absolute error than
model8 on matched observations; positive values favour model8.

{markdown_table(stage1["paired_overall"], max_rows=20)}

## Stage 2 — local training-data spiking

Budgets used: `{args.stage2_budgets}`.

Calibration methods:

- `bias_offset`: constant local residual offset;
- `seasonal_offset`: season-specific residual offset;
- `affine`: local intercept and slope correction;
- `residual_ridge`: regularised residual model using prediction-time model
  inputs such as weather, SMIPS/process state, terrain and soil attributes.

The target requested in the plan is average held-out NSE/R² > 0.4. The table
below reports the smallest strict-block design that reaches that target, or the
best strict-block design if the target is not reached.

{markdown_table(target, max_rows=20)}

### Best strict-block local calibration design per site/model

{markdown_table(best, max_rows=20)}

### Random-placement learning curves

Random placement is the most defensible deployment-oriented strategy because it
does not assume the landowner already knows where the model fails. Landscape and
global-prediction extreme strategies are still useful as practical priors.

{markdown_table(random_learning, max_rows=70)}

### Process-vs-statistical response to local spiking

Positive `process_minus_statistical_rmse_gain_median` means model8 process
benefited more from the same sparse local calibration budget than model6 RF.

{markdown_table(resp_core, max_rows=70)}

## Figures

{render_figures(report_dir, figure_specs)}

## Gallery generation warnings

{gallery_warning_text}

## Output index

- Stage 1 tables: `outputs/unified_dense_validation/stage1_independent_validation/`
- Stage 2 tables: `outputs/unified_dense_validation/stage2_local_spiking/`
- Report figures: `reports/unified_dense_validation/figures/`
- Stage 2 standalone report: `reports/unified_dense_validation/stage2_local_spiking_report.md`

## Interpretation guardrails

- Stage 1 is the independent validation score. Stage 2 is an intervention
  experiment and should not be mixed into the primary model-transfer score.
- Only spatial+temporal blocking should be treated as strong evidence of local
  calibration transfer.
- Field-knowledge-like placement strategies are useful for exploring landowner
  deployment, but anything using observed chronic wet/dry behaviour is an upper
  bound rather than a blind operational rule.
- Interpolated prediction-quality surfaces are diagnostic maps of point metrics.
  They are not substitutes for full gridded model prediction rasters.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    frames = load_site_frames()
    stage1_outdir = args.outdir / "stage1_independent_validation"
    stage2_outdir = args.outdir / "stage2_local_spiking"

    print("running Stage 1 independent dense-point validation ...", flush=True)
    stage1 = run_stage1(
        frames,
        stage1_outdir,
        args.report_dir / "figures",
        terrain_cols=args.terrain_cols,
        terrain_quantiles=args.terrain_quantiles,
        bootstrap=args.bootstrap,
        seed=args.seed,
        skip_galleries=args.skip_galleries,
    )

    if args.skip_stage2:
        print("skipping Stage 2 local spiking by request", flush=True)
    else:
        print("running Stage 2 local-spiking calibration ...", flush=True)
        run_stage2(args, stage2_outdir, args.report_dir)

    report_path = args.report_dir / "unified_dense_validation_report.md"
    write_unified_report(report_path, stage1, stage2_outdir, args)

    summary = {
        "plan_pdf": str(PLAN_PDF),
        "outdir": str(args.outdir),
        "report_dir": str(args.report_dir),
        "stage1_outdir": str(stage1_outdir),
        "stage2_outdir": str(stage2_outdir),
        "stage2_budgets": args.stage2_budgets,
        "stage2_random_reps": args.stage2_random_reps,
    }
    (args.outdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote unified report: {report_path}", flush=True)
    print(f"wrote unified outputs: {args.outdir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
