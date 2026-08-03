from __future__ import annotations

from itertools import combinations
import os
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd


def _setup():
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "dmm_validation_matplotlib"))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _models(df: pd.DataFrame) -> list[str]:
    return sorted(df["model_name"].dropna().unique())


def scatter_by_season(df: pd.DataFrame, out_path: Path) -> None:
    plt = _setup()
    seasons = [s for s in ["spring", "summer", "autumn", "winter"] if s in set(df["season"].astype(str))]
    models = _models(df)
    if not seasons or not models:
        return
    fig, axes = plt.subplots(len(seasons), len(models), figsize=(4 * len(models), 3.8 * len(seasons)), squeeze=False)
    lo = float(np.nanmin([df["obs_sm_pct"].min(), df["pred_sm_pct"].min()]))
    hi = float(np.nanmax([df["obs_sm_pct"].max(), df["pred_sm_pct"].max()]))
    pad = (hi - lo) * 0.05 if hi > lo else 1.0
    lo -= pad
    hi += pad
    for i, season in enumerate(seasons):
        for j, model in enumerate(models):
            ax = axes[i][j]
            sub = df[(df["season"].astype(str) == season) & (df["model_name"] == model)]
            ax.scatter(sub["obs_sm_pct"], sub["pred_sm_pct"], s=10, alpha=0.55)
            ax.plot([lo, hi], [lo, hi], color="0.25", linewidth=1)
            ax.set_xlim(lo, hi)
            ax.set_ylim(lo, hi)
            ax.set_title(f"{model} — {season}")
            ax.set_xlabel("Observed soil moisture (%)")
            ax.set_ylabel("Predicted soil moisture (%)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def timeseries_mean(df: pd.DataFrame, out_path: Path) -> None:
    plt = _setup()
    tmp = df.copy()
    tmp["date_dt"] = pd.to_datetime(tmp["date"])
    obs = tmp.groupby("date_dt", as_index=False).agg(obs_sm_pct=("obs_sm_pct", "mean"))
    pred = tmp.groupby(["date_dt", "model_name"], as_index=False).agg(pred_sm_pct=("pred_sm_pct", "mean"))
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.plot(obs["date_dt"], obs["obs_sm_pct"], color="black", linewidth=1.6, label="observed mean")
    for model in _models(tmp):
        sub = pred[pred["model_name"] == model]
        ax.plot(sub["date_dt"], sub["pred_sm_pct"], linewidth=1.2, label=model)
    ax.set(ylabel="Mean soil moisture (%)", xlabel="Date")
    ax.legend(ncol=3, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def residual_timeseries(df: pd.DataFrame, out_path: Path) -> None:
    plt = _setup()
    tmp = df.copy()
    tmp["date_dt"] = pd.to_datetime(tmp["date"])
    resid = tmp.groupby(["date_dt", "model_name"], as_index=False).agg(
        residual=("residual", "mean"),
        residual_std=("residual", "std"),
    )
    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.axhline(0, color="0.25", linewidth=0.9)
    for model in _models(tmp):
        sub = resid[resid["model_name"] == model]
        ax.plot(sub["date_dt"], sub["residual"], linewidth=1.2, label=model)
    ax.set(ylabel="Mean residual: prediction - observation (%)", xlabel="Date")
    ax.legend(ncol=3, fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def seasonal_bias_boxplot(df: pd.DataFrame, out_path: Path) -> None:
    plt = _setup()
    models = _models(df)
    seasons = [s for s in ["spring", "summer", "autumn", "winter"] if s in set(df["season"].astype(str))]
    if not models or not seasons:
        return
    fig, ax = plt.subplots(figsize=(max(8, 1.2 * len(models) * len(seasons)), 4.8))
    data = []
    labels = []
    positions = []
    pos = 1
    for season in seasons:
        for model in models:
            sub = df[(df["season"].astype(str) == season) & (df["model_name"] == model)]
            data.append(sub["residual"].dropna().to_numpy())
            labels.append(f"{season}\n{model}")
            positions.append(pos)
            pos += 1
        pos += 0.6
    ax.axhline(0, color="0.25", linewidth=0.9)
    ax.boxplot(data, positions=positions, labels=labels, showfliers=False)
    ax.set_ylabel("Residual: prediction - observation (%)")
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    fig.savefig(out_path, dpi=170)
    plt.close(fig)


def point_metric_maps(point_metrics: pd.DataFrame, figure_dir: Path) -> None:
    plt = _setup()
    if point_metrics.empty:
        return
    metrics = ["rmse", "bias", "nse"]
    for metric in metrics:
        for model in sorted(point_metrics["model_name"].unique()):
            sub = point_metrics[point_metrics["model_name"] == model]
            if sub.empty or metric not in sub.columns:
                continue
            fig, ax = plt.subplots(figsize=(6, 5))
            sc = ax.scatter(sub["lon"], sub["lat"], c=sub[metric], s=55, cmap="coolwarm")
            ax.set_title(f"{model}: point-level {metric}")
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")
            fig.colorbar(sc, ax=ax, label=metric)
            fig.tight_layout()
            safe_model = str(model).replace("/", "_").replace(" ", "_")
            fig.savefig(figure_dir / f"point_map_{safe_model}_{metric}.png", dpi=180)
            plt.close(fig)


def paired_difference_maps(point_diffs: pd.DataFrame, figure_dir: Path) -> None:
    plt = _setup()
    if point_diffs.empty:
        return
    for (model_a, model_b), sub in point_diffs.groupby(["model_a", "model_b"], observed=True):
        fig, ax = plt.subplots(figsize=(6, 5))
        vmax = np.nanmax(np.abs(sub["mean_delta_abs_error"]))
        if not np.isfinite(vmax) or vmax == 0:
            vmax = 1.0
        sc = ax.scatter(
            sub["lon"],
            sub["lat"],
            c=sub["mean_delta_abs_error"],
            s=60,
            cmap="coolwarm",
            vmin=-vmax,
            vmax=vmax,
        )
        ax.set_title(f"Paired abs-error difference\n{model_a} - {model_b}")
        ax.set_xlabel("Longitude")
        ax.set_ylabel("Latitude")
        fig.colorbar(sc, ax=ax, label="Mean Δ absolute error (%)")
        fig.tight_layout()
        safe = f"{model_a}_minus_{model_b}".replace("/", "_").replace(" ", "_")
        fig.savefig(figure_dir / f"paired_error_difference_map_{safe}.png", dpi=180)
        plt.close(fig)


def terrain_residual_boxplots(df: pd.DataFrame, terrain_metadata: list[dict], figure_dir: Path, max_vars: int = 8) -> None:
    plt = _setup()
    models = _models(df)
    for meta in terrain_metadata[:max_vars]:
        var = meta["terrain_var"]
        stratum_col = meta["stratum_col"]
        fig, axes = plt.subplots(len(models), 1, figsize=(9, max(3.0, 2.7 * len(models))), squeeze=False)
        for ax, model in zip(axes[:, 0], models):
            sub = df[df["model_name"] == model]
            groups = []
            labels = []
            for label, g in sub.groupby(stratum_col, dropna=True, observed=True, sort=True):
                groups.append(g["residual"].dropna().to_numpy())
                labels.append(str(label))
            if groups:
                ax.axhline(0, color="0.25", linewidth=0.9)
                ax.boxplot(groups, labels=labels, showfliers=False)
            ax.set_ylabel(model)
        axes[-1, 0].set_xlabel(f"{var} stratum")
        fig.suptitle(f"Residuals by {var} stratum")
        fig.tight_layout()
        safe = var.replace("/", "_").replace(" ", "_")
        fig.savefig(figure_dir / f"terrain_residual_boxplot_{safe}.png", dpi=170)
        plt.close(fig)


def make_all_figures(
    df: pd.DataFrame,
    point_metrics: pd.DataFrame,
    point_diffs: pd.DataFrame,
    terrain_metadata: list[dict],
    figure_dir: Path,
) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    scatter_by_season(df, figure_dir / "scatter_observed_vs_predicted_by_season.png")
    timeseries_mean(df, figure_dir / "timeseries_observed_vs_predicted_mean.png")
    residual_timeseries(df, figure_dir / "timeseries_residuals_mean.png")
    seasonal_bias_boxplot(df, figure_dir / "seasonal_bias_boxplot.png")
    point_metric_maps(point_metrics, figure_dir)
    paired_difference_maps(point_diffs, figure_dir)
    terrain_residual_boxplots(df, terrain_metadata, figure_dir)
