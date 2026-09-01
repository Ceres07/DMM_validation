#!/usr/bin/env python3
"""Plot predicted-vs-observed spatial-mean time series for validation sites.

Inputs are the model-agnostic prediction tables produced by the independent
validation workflow. The output figure uses one row per site and overlays the
mean observed soil moisture against the mean model6/model8 predictions for each
sampling date.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/matplotlib")
DEFAULT_INPUTS = {
    "Esdale": ROOT / "outputs/model6_vs_model8_dense/model6_model8_combined_predictions.csv",
    "Tarrawarra": ROOT
    / "outputs/tarrawarra_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv",
    "Nerrigundah": ROOT
    / "outputs/nerrigundah_model6_vs_model8/model6_model8_combined_predictions_valid_30m_gridcell.csv",
    "Llara": ROOT / "outputs/llara_unseen_model6_vs_model8/llara_model6_model8_predictions.csv",
    "MRI": ROOT / "outputs/mri_dense_validation/mri_model6_model8_predictions.csv",
}
DEFAULT_FIGURE = (
    ROOT
    / "reports/analyses/unified_dense_validation/figures/stage1/"
    / "predicted_vs_observed_timeseries_validation_sites.png"
)
DEFAULT_TABLE = (
    ROOT
    / "reports/analyses/unified_dense_validation/tables/"
    / "predicted_vs_observed_timeseries_validation_sites.csv"
)

MODEL_LABELS = {
    "model6": "model6 RF",
    "model6_rf": "model6 RF",
    "model8_process": "model8 process",
}
MODEL_COLORS = {
    "model6 RF": "#D55E00",
    "model8 process": "#0072B2",
}
SITE_ORDER = ["Esdale", "Tarrawarra", "Nerrigundah", "Llara", "MRI"]
QC_START_DATES = {
    "Llara": "2022-01-01",
    "MRI": "2021-07-01",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure", type=Path, default=DEFAULT_FIGURE)
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    return parser.parse_args()


def load_site(site: str, path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    cols = ["model_name", "point_id", "date", "obs_sm_pct", "pred_sm_pct"]
    df = pd.read_csv(path, usecols=lambda c: c in cols)
    missing = set(cols).difference(df.columns)
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    df = df.dropna(subset=["model_name", "point_id", "date", "obs_sm_pct", "pred_sm_pct"]).copy()
    df["site"] = site
    df["date"] = pd.to_datetime(df["date"])
    df["obs_sm_pct"] = pd.to_numeric(df["obs_sm_pct"], errors="coerce")
    df["pred_sm_pct"] = pd.to_numeric(df["pred_sm_pct"], errors="coerce")
    df["model_label"] = df["model_name"].astype(str).map(MODEL_LABELS).fillna(df["model_name"].astype(str))
    qc_start = QC_START_DATES.get(site)
    if qc_start is not None:
        df = df[df["date"] >= pd.Timestamp(qc_start)].copy()
    return df.dropna(subset=["obs_sm_pct", "pred_sm_pct"])


def build_timeseries_table() -> pd.DataFrame:
    frames = [load_site(site, DEFAULT_INPUTS[site]) for site in SITE_ORDER]
    df = pd.concat(frames, ignore_index=True)
    grouped = (
        df.groupby(["site", "date", "model_label"], as_index=False)
        .agg(
            obs_mean_pct=("obs_sm_pct", "mean"),
            obs_sd_pct=("obs_sm_pct", "std"),
            pred_mean_pct=("pred_sm_pct", "mean"),
            pred_sd_pct=("pred_sm_pct", "std"),
            n_points=("point_id", "nunique"),
            n_rows=("pred_sm_pct", "size"),
        )
    )
    grouped["mean_residual_pred_minus_obs_pct"] = grouped["pred_mean_pct"] - grouped["obs_mean_pct"]
    return grouped.sort_values(["site", "date", "model_label"]).reset_index(drop=True)


def pooled_metrics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (site, model), sub in df.groupby(["site", "model_label"]):
        obs = sub["obs_sm_pct"].to_numpy(dtype=float)
        pred = sub["pred_sm_pct"].to_numpy(dtype=float)
        resid = pred - obs
        ss_res = float(np.sum((obs - pred) ** 2))
        ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
        nse = np.nan if ss_tot == 0 else 1 - ss_res / ss_tot
        rmse = float(np.sqrt(np.mean(resid**2)))
        bias = float(np.mean(resid))
        rows.append({"site": site, "model_label": model, "nse": nse, "rmse": rmse, "bias": bias})
    return pd.DataFrame(rows)


def plot(timeseries: pd.DataFrame, metrics: pd.DataFrame, out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    out.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(SITE_ORDER), 1, figsize=(12.0, max(3.0 * len(SITE_ORDER), 9.2)), sharex=False)
    if len(SITE_ORDER) == 1:
        axes = [axes]

    for ax, site in zip(axes, SITE_ORDER):
        sub = timeseries[timeseries["site"] == site].copy()
        obs = (
            sub.groupby("date", as_index=False)
            .agg(obs_mean_pct=("obs_mean_pct", "mean"), n_points=("n_points", "max"))
            .sort_values("date")
        )
        ax.plot(
            obs["date"],
            obs["obs_mean_pct"],
            color="black",
            linewidth=2.3,
            marker="o",
            markersize=3.4,
            label="observed mean",
            zorder=4,
        )
        for model in ["model6 RF", "model8 process"]:
            m = sub[sub["model_label"] == model].sort_values("date")
            if m.empty:
                continue
            ax.plot(
                m["date"],
                m["pred_mean_pct"],
                color=MODEL_COLORS[model],
                linewidth=1.8,
                marker=None if site in {"Llara", "MRI"} else "o",
                markersize=3.0,
                alpha=0.95,
                label=f"{model} predicted mean",
            )

        met = metrics[metrics["site"] == site].copy()
        metric_lines = []
        for model in ["model6 RF", "model8 process"]:
            row = met[met["model_label"] == model]
            if row.empty:
                continue
            r = row.iloc[0]
            metric_lines.append(f"{model}: NSE {r.nse:.2f}, RMSE {r.rmse:.1f}%, bias {r.bias:+.1f}%")
        title = f"{site}: spatial mean predicted vs observed soil moisture"
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
        text_x = 0.99 if site == "MRI" else 0.01
        text_ha = "right" if site == "MRI" else "left"
        ax.text(
            text_x,
            0.96,
            "\n".join(metric_lines),
            transform=ax.transAxes,
            va="top",
            ha=text_ha,
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.78, edgecolor="0.85"),
        )
        ax.set_ylabel("soil moisture (%)")
        ax.grid(True, color="0.88", linewidth=0.8)
        ax.spines[["top", "right"]].set_visible(False)
        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        if site == "MRI":
            ax.set_ylim(15, 60)
        else:
            ymin = np.nanmin([sub["obs_mean_pct"].min(), sub["pred_mean_pct"].min()])
            ymax = np.nanmax([sub["obs_mean_pct"].max(), sub["pred_mean_pct"].max()])
            pad = max(2.0, 0.08 * (ymax - ymin))
            ax.set_ylim(max(0, ymin - pad), min(100, ymax + pad))

    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
    fig.suptitle(
        "Predicted vs observed soil-moisture time series across validation sites",
        fontsize=14,
        fontweight="bold",
        y=0.995,
    )
    fig.text(
        0.5,
        0.035,
        "Lines are spatial means across available validation points for each site/date; metrics are pooled point-date scores.",
        ha="center",
        fontsize=9,
        color="0.25",
    )
    fig.tight_layout(rect=[0, 0.065, 1, 0.975])
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    table = build_timeseries_table()
    args.table.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(args.table, index=False)

    raw = pd.concat([load_site(site, DEFAULT_INPUTS[site]) for site in SITE_ORDER], ignore_index=True)
    metrics = pooled_metrics(raw)
    plot(table, metrics, args.figure)
    print(f"wrote {args.figure}")
    print(f"wrote {args.table}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
