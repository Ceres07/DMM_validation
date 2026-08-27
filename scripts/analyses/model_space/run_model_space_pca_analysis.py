#!/usr/bin/env python3
"""Model-agnostic covariate PCA and terrain residual stratification report.

This is intentionally separate from the main dense-validation manuscript.  It
asks a narrower diagnostic question: do Esdale, Tarrawarra and Llara occupy
different parts of the model-agnostic covariate space, and do model6/model8
errors cluster in consistent terrain/climate covariate locations?

Two PCA scalings are used:

* global-scaled PCA: features are standardised once across the pooled validation
  supports (and, for training-distance diagnostics, against OzNet training
  supports/rows). This preserves absolute site differences.
* site-standardised PCA: features are z-scored within each validation site
  before PCA. This removes site-average offsets and keeps the within-site
  ridge/valley/exposure/soil contrasts.

The script also projects validation rows into the cached OzNet training
covariate table when available, then reports nearest-neighbour and
Mahalanobis-style distance percentiles.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from sklearn.decomposition import PCA
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dmm_validation.metrics import soil_moisture_metrics  # noqa: E402


DEFAULT_PREDICTIONS = ROOT / "outputs/unified_dense_validation/stage1_independent_validation/combined_model_agnostic_predictions.csv"
DEFAULT_TRAINING_TABLE = Path("/Volumes/Dmitry_work/borevitz_projects/Data/oznet_model6_training_2006_2010.csv")
DEFAULT_OUTDIR = ROOT / "outputs/unified_dense_validation/model_space_pca"
DEFAULT_REPORT_DIR = ROOT / "reports" / "analyses" / "unified_dense_validation"
DEFAULT_FIGDIR = DEFAULT_REPORT_DIR / "figures/model_space_pca"
DEFAULT_REPORT = DEFAULT_REPORT_DIR / "model_space_pca_report.md"


STATIC_TERRAIN_SOIL = [
    "elevation",
    "slope",
    "northness",
    "eastness",
    "twi",
    "hli",
    "accumulation",
    "soil_clay",
    "soil_sand",
    "soil_awc",
    "soil_bdw",
]

MODEL_AGNOSTIC_COVARIATES = [
    "smips_totalbucket",
    *STATIC_TERRAIN_SOIL,
    "doy_sin",
    "doy_cos",
    "smips_7d",
    "smips_30d",
    "smips_365d",
    "smips_anom",
    "rain_7",
    "rain_30",
    "rain_365",
    "ppet_30",
    "ppet_365",
    "vpd_30",
    "rain_365_anom",
]

PROCESS_CONTEXT_COVARIATES = [
    "model8_storage_mm",
    "elevation",
    "slope",
    "twi",
    "soil_clay",
    "soil_sand",
    "soil_awc",
    "soil_bdw",
]

FEATURE_SETS = {
    "static_terrain_soil": STATIC_TERRAIN_SOIL,
    "model_agnostic_covariates": MODEL_AGNOSTIC_COVARIATES,
    "process_context_covariates": PROCESS_CONTEXT_COVARIATES,
}

FEATURE_SET_LABELS = {
    "static_terrain_soil": "static terrain-soil covariates",
    "model_agnostic_covariates": "dynamic model-agnostic covariates",
    "process_context_covariates": "process-context covariates",
}

PC_DECOMPOSITION_METRICS = [
    "rmse_model6_rf",
    "rmse_model8_process",
    "bias_model6_rf",
    "bias_model8_process",
    "rmse_model6_minus_model8",
    "abs_bias_model6_minus_model8",
]

MODEL_LABELS = {
    "model6_rf": "model6 statistical RF/HGB",
    "model8_process": "model8 process bucket",
}

SITE_COLORS = {
    "Esdale": "#4477AA",
    "Tarrawarra": "#228833",
    "Llara": "#CC6677",
}


@dataclass
class PcaResult:
    feature_set: str
    scaling: str
    feature_cols: list[str]
    scores: pd.DataFrame
    loadings: pd.DataFrame
    explained: pd.DataFrame
    pca: PCA
    transformed_matrix: np.ndarray


def finite_corr(x: Iterable[float], y: Iterable[float]) -> float:
    a = np.asarray(list(x), dtype=float)
    b = np.asarray(list(y), dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    if ok.sum() < 3:
        return np.nan
    if np.nanstd(a[ok]) <= 0 or np.nanstd(b[ok]) <= 0:
        return np.nan
    return float(np.corrcoef(a[ok], b[ok])[0, 1])


def feature_set_label(name: str) -> str:
    return FEATURE_SET_LABELS.get(name, name.replace("_", " "))


def robust_markdown_table(df: pd.DataFrame, cols: list[str] | None = None, max_rows: int = 20) -> str:
    if df is None or df.empty:
        return "_No rows._"
    sub = df.copy()
    if cols:
        sub = sub[[c for c in cols if c in sub.columns]]
    if len(sub) > max_rows:
        sub = sub.head(max_rows)
    for c in sub.select_dtypes(include=[np.number]).columns:
        sub[c] = sub[c].map(lambda v: "" if pd.isna(v) else f"{v:.3f}")
    sub = sub.fillna("")
    headers = [str(c) for c in sub.columns]
    rows = [[str(v) for v in row] for row in sub.to_numpy()]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]
    header_line = "| " + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers))) + " |"
    sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    body = ["| " + " | ".join(row[i].ljust(widths[i]) for i in range(len(headers))) + " |" for row in rows]
    return "\n".join([header_line, sep_line, *body])


def canonical_base_model(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("model6", "model6_rf", regex=False)
        .str.replace("model8", "model8_process", regex=False)
        .replace({"model6_rf_rf": "model6_rf", "model8_process_process": "model8_process"})
    )


def load_predictions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    if "base_model" not in df.columns:
        if "model_name" in df.columns:
            df["base_model"] = canonical_base_model(df["model_name"])
        else:
            raise ValueError("Predictions table needs either base_model or model_name.")
    else:
        df["base_model"] = canonical_base_model(df["base_model"])
    df["site"] = df["site"].astype(str)
    df["point_id"] = df["point_id"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date.astype(str)
    if "residual" not in df.columns:
        df["residual"] = df["pred_sm_pct"] - df["obs_sm_pct"]
    df["abs_error"] = (df["pred_sm_pct"] - df["obs_sm_pct"]).abs()
    return df


def metric_by_support(pred: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    group_cols = ["site", "point_id", "base_model"]
    for key, g in pred.groupby(group_cols, dropna=False, observed=True):
        site, point_id, base_model = key
        m = soil_moisture_metrics(g["obs_sm_pct"], g["pred_sm_pct"])
        rows.append(
            {
                "site": site,
                "point_id": point_id,
                "base_model": base_model,
                "model_label": MODEL_LABELS.get(base_model, base_model),
                **{k: m[k] for k in ["n", "nse", "pearson_r", "rmse", "ubrmse", "bias"]},
                "mean_abs_error": float(np.nanmean(np.abs(g["pred_sm_pct"] - g["obs_sm_pct"]))),
                "mean_residual": float(np.nanmean(g["pred_sm_pct"] - g["obs_sm_pct"])),
            }
        )
    return pd.DataFrame(rows)


def paired_support_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    idx = ["site", "point_id"]
    wide_parts = []
    for metric in ["n", "nse", "pearson_r", "rmse", "ubrmse", "bias", "mean_abs_error", "mean_residual"]:
        w = metrics.pivot_table(index=idx, columns="base_model", values=metric, aggfunc="first")
        w = w.rename(columns={c: f"{metric}_{c}" for c in w.columns}).reset_index()
        wide_parts.append(w)
    out = wide_parts[0]
    for w in wide_parts[1:]:
        out = out.merge(w, on=idx, how="outer")
    if {"rmse_model6_rf", "rmse_model8_process"}.issubset(out.columns):
        out["rmse_model6_minus_model8"] = out["rmse_model6_rf"] - out["rmse_model8_process"]
        out["rmse_better_model"] = np.where(
            out["rmse_model6_minus_model8"] > 0,
            "model8_process",
            np.where(out["rmse_model6_minus_model8"] < 0, "model6_rf", "tie"),
        )
    if {"bias_model6_rf", "bias_model8_process"}.issubset(out.columns):
        out["bias_model6_minus_model8"] = out["bias_model6_rf"] - out["bias_model8_process"]
        out["abs_bias_model6_minus_model8"] = out["bias_model6_rf"].abs() - out["bias_model8_process"].abs()
    return out


def support_features(pred: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    have = [c for c in feature_cols if c in pred.columns]
    if not have:
        return pd.DataFrame()

    cols = ["site", "point_id", "lon", "lat", *have]
    sub = pred[cols].copy()
    for c in ["lon", "lat", *have]:
        sub[c] = pd.to_numeric(sub[c], errors="coerce")

    agg = {c: "median" for c in ["lon", "lat", *have]}
    out = sub.groupby(["site", "point_id"], as_index=False, observed=True).agg(agg)
    out["support_id"] = out["site"].astype(str) + "::" + out["point_id"].astype(str)
    return out


def observation_feature_rows(pred: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """One validation covariate row per site/point/date.

    Features are identical across model rows except for fields only recorded by
    model8, so taking a median across model rows is safe and avoids duplicated
    point-date rows.
    """

    have = [c for c in feature_cols if c in pred.columns]
    cols = ["site", "point_id", "date", "lon", "lat", "season", *have]
    sub = pred[[c for c in cols if c in pred.columns]].copy()
    for c in ["lon", "lat", *have]:
        if c in sub.columns:
            sub[c] = pd.to_numeric(sub[c], errors="coerce")
    agg = {c: "median" for c in ["lon", "lat", *have] if c in sub.columns}
    if "season" in sub.columns:
        agg["season"] = "first"
    return sub.groupby(["site", "point_id", "date"], as_index=False, observed=True).agg(agg)


def existing_features(df: pd.DataFrame, requested: list[str], min_nonmissing_fraction: float = 0.2) -> list[str]:
    cols = []
    for c in requested:
        if c not in df.columns:
            continue
        vals = pd.to_numeric(df[c], errors="coerce")
        if vals.notna().mean() >= min_nonmissing_fraction:
            cols.append(c)
    return cols


def transform_global(features: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    X = features[feature_cols].apply(pd.to_numeric, errors="coerce")
    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    return scaler.fit_transform(imputer.fit_transform(X))


def transform_site_standardised(features: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    parts = []
    for _, g in features.groupby("site", observed=True, sort=False):
        X = g[feature_cols].apply(pd.to_numeric, errors="coerce")
        mu = X.mean(axis=0)
        sigma = X.std(axis=0, ddof=0).replace(0, np.nan)
        Z = (X - mu) / sigma
        parts.append(Z)
    z = pd.concat(parts).loc[features.index]
    imputer = SimpleImputer(strategy="constant", fill_value=0.0)
    return imputer.fit_transform(z)


def fit_validation_pca(features: pd.DataFrame, feature_cols: list[str], feature_set: str, scaling: str) -> PcaResult:
    if scaling == "global":
        X = transform_global(features, feature_cols)
    elif scaling == "site_standardised":
        X = transform_site_standardised(features, feature_cols)
    else:
        raise ValueError(f"Unknown scaling: {scaling}")

    n_components = int(min(6, len(feature_cols), max(1, X.shape[0] - 1)))
    pca = PCA(n_components=n_components, random_state=0)
    scores_arr = pca.fit_transform(X)

    scores = features[["site", "point_id", "support_id", "lon", "lat"]].copy()
    for i in range(n_components):
        scores[f"PC{i+1}"] = scores_arr[:, i]
    scores["feature_set"] = feature_set
    scores["scaling"] = scaling

    loading_rows = []
    for j, feature in enumerate(feature_cols):
        row = {"feature_set": feature_set, "scaling": scaling, "feature": feature}
        for i in range(n_components):
            row[f"PC{i+1}_loading"] = pca.components_[i, j]
        loading_rows.append(row)
    loadings = pd.DataFrame(loading_rows)
    loadings["PC1_PC2_abs_loading"] = np.sqrt(
        loadings.get("PC1_loading", 0.0) ** 2 + loadings.get("PC2_loading", 0.0) ** 2
    )

    explained = pd.DataFrame(
        {
            "feature_set": feature_set,
            "scaling": scaling,
            "PC": [f"PC{i+1}" for i in range(n_components)],
            "explained_variance_ratio": pca.explained_variance_ratio_,
            "cumulative_explained_variance": np.cumsum(pca.explained_variance_ratio_),
        }
    )
    return PcaResult(feature_set, scaling, feature_cols, scores, loadings, explained, pca, X)


def plot_site_pca(result: PcaResult, figdir: Path) -> Path:
    scores = result.scores
    loadings = result.loadings.sort_values("PC1_PC2_abs_loading", ascending=False).head(9)
    explained = result.explained.set_index("PC")["explained_variance_ratio"]
    out = figdir / f"{result.feature_set}_{result.scaling}_site_pca.png"

    fig, ax = plt.subplots(figsize=(8.2, 6.2))
    for site, g in scores.groupby("site", sort=True):
        ax.scatter(g["PC1"], g["PC2"], s=36, alpha=0.78, edgecolor="white", linewidth=0.4, color=SITE_COLORS.get(site), label=site)
        if len(g) >= 4:
            cx, cy = g["PC1"].mean(), g["PC2"].mean()
            ax.scatter([cx], [cy], s=160, marker="X", color=SITE_COLORS.get(site), edgecolor="black", linewidth=0.8)

    if {"PC1_loading", "PC2_loading"}.issubset(loadings.columns):
        xspan = max(scores["PC1"].max() - scores["PC1"].min(), 1e-6)
        yspan = max(scores["PC2"].max() - scores["PC2"].min(), 1e-6)
        scale = 0.23 * min(xspan, yspan)
        for _, r in loadings.iterrows():
            x = r["PC1_loading"] * scale
            y = r["PC2_loading"] * scale
            ax.arrow(0, 0, x, y, color="0.20", alpha=0.75, width=0.004 * scale, head_width=0.035 * scale, length_includes_head=True)
            ax.text(x * 1.10, y * 1.10, r["feature"], fontsize=8, ha="center", va="center", color="0.12")

    ax.axhline(0, color="0.85", linewidth=0.8)
    ax.axvline(0, color="0.85", linewidth=0.8)
    ax.set_xlabel(f"PC1 ({explained.get('PC1', np.nan) * 100:.1f}% variance)")
    ax.set_ylabel(f"PC2 ({explained.get('PC2', np.nan) * 100:.1f}% variance)")
    title_scaling = "global-scaled" if result.scaling == "global" else "site-standardised"
    ax.set_title(f"{feature_set_label(result.feature_set)}: {title_scaling} PCA of validation supports")
    ax.legend(frameon=False, loc="best")
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_rmse_pca(result: PcaResult, paired: pd.DataFrame, figdir: Path) -> Path:
    df = result.scores.merge(paired, on=["site", "point_id"], how="left")
    out = figdir / f"{result.feature_set}_{result.scaling}_rmse_pca.png"
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.6), sharex=True, sharey=True)
    models = [("rmse_model6_rf", "model6 statistical RF/HGB"), ("rmse_model8_process", "model8 process bucket")]
    vmax = np.nanpercentile(df[[m[0] for m in models]].to_numpy(dtype=float), 95)
    vmin = np.nanpercentile(df[[m[0] for m in models]].to_numpy(dtype=float), 5)
    last = None
    for ax, (col, label) in zip(axes, models):
        for site, g in df.groupby("site", sort=True):
            last = ax.scatter(
                g["PC1"],
                g["PC2"],
                c=g[col],
                cmap="magma_r",
                s=45,
                vmin=vmin,
                vmax=vmax,
                alpha=0.82,
                edgecolor="white",
                linewidth=0.35,
                marker={"Esdale": "o", "Tarrawarra": "s", "Llara": "^"}.get(site, "o"),
            )
        ax.axhline(0, color="0.86", linewidth=0.8)
        ax.axvline(0, color="0.86", linewidth=0.8)
        ax.set_title(label)
        ax.set_xlabel("PC1")
    axes[0].set_ylabel("PC2")
    handles = [
        Line2D([0], [0], marker={"Esdale": "o", "Tarrawarra": "s", "Llara": "^"}.get(site, "o"), color="none", markerfacecolor="0.45", markeredgecolor="white", label=site, markersize=8)
        for site in sorted(df["site"].dropna().unique())
    ]
    axes[1].legend(handles=handles, frameon=False, title="site", loc="best")
    if last is not None:
        cbar = fig.colorbar(last, ax=axes, shrink=0.82, pad=0.02)
        cbar.set_label("support-level RMSE (%)")
    title_scaling = "global-scaled" if result.scaling == "global" else "site-standardised"
    fig.suptitle(f"Where do the high-RMSE supports sit? {feature_set_label(result.feature_set)}, {title_scaling}", y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_bias_pca(result: PcaResult, paired: pd.DataFrame, figdir: Path) -> Path:
    df = result.scores.merge(paired, on=["site", "point_id"], how="left")
    out = figdir / f"{result.feature_set}_{result.scaling}_bias_pca.png"
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.6), sharex=True, sharey=True)
    models = [("bias_model6_rf", "model6 statistical RF/HGB"), ("bias_model8_process", "model8 process bucket")]
    vals = df[[m[0] for m in models]].to_numpy(dtype=float)
    vmax = np.nanpercentile(np.abs(vals), 95)
    if not np.isfinite(vmax) or vmax == 0:
        vmax = 1.0
    last = None
    for ax, (col, label) in zip(axes, models):
        for site, g in df.groupby("site", sort=True):
            last = ax.scatter(
                g["PC1"],
                g["PC2"],
                c=g[col],
                cmap="RdBu",
                s=45,
                vmin=-vmax,
                vmax=vmax,
                alpha=0.82,
                edgecolor="white",
                linewidth=0.35,
                marker={"Esdale": "o", "Tarrawarra": "s", "Llara": "^"}.get(site, "o"),
            )
        ax.axhline(0, color="0.86", linewidth=0.8)
        ax.axvline(0, color="0.86", linewidth=0.8)
        ax.set_title(label)
        ax.set_xlabel("PC1")
    axes[0].set_ylabel("PC2")
    handles = [
        Line2D([0], [0], marker={"Esdale": "o", "Tarrawarra": "s", "Llara": "^"}.get(site, "o"), color="none", markerfacecolor="0.45", markeredgecolor="white", label=site, markersize=8)
        for site in sorted(df["site"].dropna().unique())
    ]
    axes[1].legend(handles=handles, frameon=False, title="site", loc="best")
    if last is not None:
        cbar = fig.colorbar(last, ax=axes, shrink=0.82, pad=0.02)
        cbar.set_label("support-level bias (%; prediction - observation)")
    title_scaling = "global-scaled" if result.scaling == "global" else "site-standardised"
    fig.suptitle(f"Where do signed wet/dry biases sit? {feature_set_label(result.feature_set)}, {title_scaling}", y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_model_difference_pca(result: PcaResult, paired: pd.DataFrame, figdir: Path) -> Path:
    df = result.scores.merge(paired, on=["site", "point_id"], how="left")
    out = figdir / f"{result.feature_set}_{result.scaling}_model_difference_pca.png"
    fig, ax = plt.subplots(figsize=(8.6, 6.2))
    vals = df["rmse_model6_minus_model8"]
    lim = np.nanpercentile(np.abs(vals), 95)
    if not np.isfinite(lim) or lim == 0:
        lim = 1.0
    sc = ax.scatter(
        df["PC1"],
        df["PC2"],
        c=vals,
        cmap="RdBu_r",
        vmin=-lim,
        vmax=lim,
        s=48,
        alpha=0.84,
        edgecolor="white",
        linewidth=0.35,
    )
    for site, g in df.groupby("site", sort=True):
        cx, cy = g["PC1"].mean(), g["PC2"].mean()
        ax.text(cx, cy, site, fontsize=9, weight="bold", ha="center", va="center", bbox=dict(facecolor="white", alpha=0.75, edgecolor="none", pad=2))
    ax.axhline(0, color="0.86", linewidth=0.8)
    ax.axvline(0, color="0.86", linewidth=0.8)
    ax.set_xlabel("PC1")
    ax.set_ylabel("PC2")
    cbar = fig.colorbar(sc, ax=ax, shrink=0.86)
    cbar.set_label("RMSE(model6) - RMSE(model8), %; positive = model8 better")
    title_scaling = "global-scaled" if result.scaling == "global" else "site-standardised"
    ax.set_title(f"Process vs statistical advantage in {feature_set_label(result.feature_set)}, {title_scaling} PCA")
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_training_distance(dist: pd.DataFrame, figdir: Path, feature_set: str) -> Path:
    out = figdir / f"{feature_set}_training_distance_by_site.png"
    metric = "nn_distance_percentile"
    sites = list(dist["site"].dropna().unique())
    fig, ax = plt.subplots(figsize=(8.6, 5.4))
    positions = np.arange(len(sites))
    data = [dist.loc[dist["site"] == s, metric].dropna().values for s in sites]
    box = ax.boxplot(data, positions=positions, patch_artist=True, widths=0.55, showfliers=False)
    for patch, site in zip(box["boxes"], sites):
        patch.set_facecolor(SITE_COLORS.get(site, "0.6"))
        patch.set_alpha(0.70)
    for i, site in enumerate(sites):
        y = dist.loc[dist["site"] == site, metric].dropna().values
        if len(y):
            jitter = np.random.default_rng(0).normal(0, 0.035, size=len(y))
            ax.scatter(np.full(len(y), positions[i]) + jitter, y, s=10, alpha=0.18, color="0.15")
    ax.axhline(95, color="#AA3377", linestyle="--", linewidth=1.0, label="95th percentile of training self-distances")
    ax.set_xticks(positions)
    ax.set_xticklabels(sites)
    ax.set_ylabel("nearest-neighbour distance percentile vs OzNet training")
    ax.set_ylim(-2, 102)
    ax.set_title(f"How far are validation rows from OzNet training covariate space? {feature_set_label(feature_set)}")
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_distance_error(dist: pd.DataFrame, pred: pd.DataFrame, figdir: Path, feature_set: str) -> Path:
    keys = ["site", "point_id", "date"]
    join = pred.merge(dist[keys + ["nn_distance_percentile"]], on=keys, how="inner")
    out = figdir / f"{feature_set}_training_distance_vs_abs_error.png"
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 5.4), sharex=True, sharey=True)
    for ax, (model, g) in zip(axes, join.groupby("base_model", sort=True)):
        for site, s in g.groupby("site", sort=True):
            # Use a light random downsample for the dense Llara time series so the
            # figure stays readable but statistics are still computed from all rows.
            ss = s
            if len(ss) > 4000:
                ss = ss.sample(4000, random_state=7)
            ax.scatter(
                ss["nn_distance_percentile"],
                ss["abs_error"],
                s=9,
                alpha=0.14,
                color=SITE_COLORS.get(site),
                label=site,
                edgecolor="none",
            )
        corr = finite_corr(g["nn_distance_percentile"], g["abs_error"])
        ax.text(0.02, 0.96, f"r(distance, |error|) = {corr:.2f}", transform=ax.transAxes, va="top", ha="left", fontsize=9)
        ax.axvline(95, color="#AA3377", linestyle="--", linewidth=1.0)
        ax.set_title(MODEL_LABELS.get(model, model))
        ax.set_xlabel("training-distance percentile")
    axes[0].set_ylabel("absolute prediction error (%)")
    axes[1].legend(frameon=False, loc="upper left")
    fig.suptitle(f"Does distance from training covariate space predict failure? {feature_set_label(feature_set)}", y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_training_distance_by_season(dist: pd.DataFrame, figdir: Path, feature_set: str) -> Path | None:
    if "season" not in dist.columns or dist["season"].dropna().empty:
        return None
    out = figdir / f"{feature_set}_training_mahalanobis_by_site_season.png"
    season_order = ["summer", "autumn", "winter", "spring"]
    sites = sorted(dist["site"].dropna().unique())
    x = np.arange(len(season_order))

    fig, ax = plt.subplots(figsize=(8.8, 5.4))
    for i, site in enumerate(sites):
        g = dist[dist["site"] == site]
        med = []
        lo = []
        hi = []
        for season in season_order:
            vals = g.loc[g["season"] == season, "mahalanobis_pc_percentile"].dropna()
            if len(vals):
                med.append(float(np.nanmedian(vals)))
                lo.append(float(np.nanpercentile(vals, 25)))
                hi.append(float(np.nanpercentile(vals, 75)))
            else:
                med.append(np.nan)
                lo.append(np.nan)
                hi.append(np.nan)
        med_arr = np.asarray(med, dtype=float)
        lo_arr = np.asarray(lo, dtype=float)
        hi_arr = np.asarray(hi, dtype=float)
        offset = (i - (len(sites) - 1) / 2) * 0.08
        ax.errorbar(
            x + offset,
            med_arr,
            yerr=[med_arr - lo_arr, hi_arr - med_arr],
            marker="o",
            linewidth=1.7,
            capsize=3,
            color=SITE_COLORS.get(site),
            label=site,
        )
    ax.axhline(95, color="#AA3377", linestyle="--", linewidth=1.0, label="95th training percentile")
    ax.set_xticks(x)
    ax.set_xticklabels([s.title() for s in season_order])
    ax.set_ylim(-2, 102)
    ax.set_ylabel("training-PCA Mahalanobis percentile")
    ax.set_title(f"Seasonal distance from OzNet training covariate space: {feature_set_label(feature_set)}")
    ax.legend(frameon=False, ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=220)
    plt.close(fig)
    return out


def plot_seasonal_distance_skill(dist: pd.DataFrame, pred: pd.DataFrame, figdir: Path, feature_set: str) -> Path | None:
    if "season" not in dist.columns or dist["season"].dropna().empty:
        return None
    keys = ["site", "point_id", "date"]
    joined = pred.merge(dist[keys + ["mahalanobis_pc_percentile"]], on=keys, how="inner")
    rows = []
    for (site, season, base_model), g in joined.groupby(["site", "season", "base_model"], observed=True, sort=True):
        m = soil_moisture_metrics(g["obs_sm_pct"], g["pred_sm_pct"])
        rows.append(
            {
                "site": site,
                "season": season,
                "base_model": base_model,
                "median_distance_percentile": float(np.nanmedian(g["mahalanobis_pc_percentile"])),
                "rmse": m["rmse"],
                "bias": m["bias"],
                "n": m["n"],
            }
        )
    agg = pd.DataFrame(rows)
    if agg.empty:
        return None

    out = figdir / f"{feature_set}_seasonal_distance_skill.png"
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 5.4), sharex=True)
    markers = {"model6_rf": "o", "model8_process": "s"}
    for ax, metric, ylabel in [(axes[0], "rmse", "seasonal RMSE (%)"), (axes[1], "bias", "seasonal bias (%; pred - obs)")]:
        for _, r in agg.iterrows():
            ax.scatter(
                r["median_distance_percentile"],
                r[metric],
                s=70,
                marker=markers.get(r["base_model"], "o"),
                color=SITE_COLORS.get(r["site"], "0.5"),
                edgecolor="white",
                linewidth=0.6,
                alpha=0.88,
            )
            ax.text(
                r["median_distance_percentile"] + 0.5,
                r[metric],
                f"{r['site'][0]}-{str(r['season'])[:2]}",
                fontsize=7,
                alpha=0.75,
            )
        ax.axvline(95, color="#AA3377", linestyle="--", linewidth=1.0)
        ax.axhline(0, color="0.82", linewidth=0.8) if metric == "bias" else None
        ax.set_xlabel("median training-distance percentile")
        ax.set_ylabel(ylabel)
    handles = [
        Line2D([0], [0], marker="o", linestyle="none", color="none", markerfacecolor=SITE_COLORS.get(site), markeredgecolor="white", label=site, markersize=9)
        for site in sorted(agg["site"].unique())
    ]
    handles.extend(
        [
            Line2D([0], [0], marker="o", linestyle="none", color="0.25", label="model6", markersize=8),
            Line2D([0], [0], marker="s", linestyle="none", color="0.25", label="model8", markersize=8),
        ]
    )
    axes[1].legend(handles=handles, frameon=False, loc="best", fontsize=8)
    fig.suptitle(f"Seasonal error versus distance from training covariate space: {feature_set_label(feature_set)}", y=1.02)
    fig.tight_layout()
    fig.savefig(out, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return out


def site_centroid_distances(scores: pd.DataFrame) -> pd.DataFrame:
    pcs = [c for c in scores.columns if c.startswith("PC")][:3]
    if len(pcs) < 2:
        return pd.DataFrame()
    cent = scores.groupby("site", observed=True)[pcs].mean()
    rows = []
    sites = list(cent.index)
    for i, a in enumerate(sites):
        for b in sites[i + 1 :]:
            va = cent.loc[a].to_numpy(dtype=float)
            vb = cent.loc[b].to_numpy(dtype=float)
            rows.append(
                {
                    "feature_set": scores["feature_set"].iloc[0],
                    "scaling": scores["scaling"].iloc[0],
                    "site_a": a,
                    "site_b": b,
                    "pc1_pc2_distance": float(np.linalg.norm(va[:2] - vb[:2])),
                    "pc1_pc2_pc3_distance": float(np.linalg.norm(va - vb)) if len(pcs) >= 3 else np.nan,
                }
            )
    return pd.DataFrame(rows)


def pc_residual_correlations(scores: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    df = scores.merge(paired, on=["site", "point_id"], how="left")
    pc_cols = [c for c in scores.columns if c.startswith("PC")][:3]
    rows = []
    metric_cols = PC_DECOMPOSITION_METRICS
    for site, g in df.groupby("site", sort=True, observed=True):
        for metric in metric_cols:
            if metric not in g.columns:
                continue
            for pc in pc_cols:
                rows.append(
                    {
                        "feature_set": scores["feature_set"].iloc[0],
                        "scaling": scores["scaling"].iloc[0],
                        "site": site,
                        "pc_axis": pc,
                        "metric": metric,
                        "pc_metric_correlation": finite_corr(g[pc], g[metric]),
                        "n_supports": int(g[[pc, metric]].dropna().shape[0]),
                    }
                )
    return pd.DataFrame(rows)


def pc_feature_decomposition(loadings: pd.DataFrame, pc_corr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, cr in pc_corr.iterrows():
        pc = cr["pc_axis"]
        loading_col = f"{pc}_loading"
        lsub = loadings[
            loadings["feature_set"].eq(cr["feature_set"])
            & loadings["scaling"].eq(cr["scaling"])
        ]
        if loading_col not in lsub.columns or pd.isna(cr.get("pc_metric_correlation")):
            continue
        for _, lr in lsub.iterrows():
            contribution = float(cr["pc_metric_correlation"] * lr[loading_col])
            rows.append(
                {
                    "feature_set": cr["feature_set"],
                    "scaling": cr["scaling"],
                    "site": cr["site"],
                    "metric": cr["metric"],
                    "pc_axis": pc,
                    "feature": lr["feature"],
                    "pc_metric_correlation": cr["pc_metric_correlation"],
                    "pc_loading": lr[loading_col],
                    "signed_contribution_proxy": contribution,
                    "abs_contribution_proxy": abs(contribution),
                    "n_supports": cr["n_supports"],
                }
            )
    return pd.DataFrame(rows)


def site_standardised_feature_error_correlations(pred: pd.DataFrame, paired: pd.DataFrame) -> pd.DataFrame:
    feature_cols = [c for c in MODEL_AGNOSTIC_COVARIATES if c in pred.columns]
    support = support_features(pred, feature_cols)
    feature_cols = existing_features(support, feature_cols)
    if len(feature_cols) < 3:
        return pd.DataFrame()
    z = support.copy()
    for _, idx in z.groupby("site", observed=True).groups.items():
        X = z.loc[idx, feature_cols].apply(pd.to_numeric, errors="coerce")
        mu = X.mean(axis=0)
        sigma = X.std(axis=0, ddof=0).replace(0, np.nan)
        z.loc[idx, feature_cols] = (X - mu) / sigma
    df = z.merge(paired, on=["site", "point_id"], how="left")
    rows = []
    for site, g in df.groupby("site", sort=True, observed=True):
        for feature in feature_cols:
            for metric in PC_DECOMPOSITION_METRICS:
                if metric not in g.columns:
                    continue
                rows.append(
                    {
                        "site": site,
                        "feature": feature,
                        "metric": metric,
                        "feature_metric_correlation": finite_corr(g[feature], g[metric]),
                        "n_supports": int(g[[feature, metric]].dropna().shape[0]),
                    }
                )
    return pd.DataFrame(rows)


def worst_support_overlap(paired: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for site, g in paired.groupby("site", sort=True, observed=True):
        g = g.dropna(subset=["rmse_model6_rf", "rmse_model8_process"])
        if len(g) < 5:
            continue
        k = int(max(3, math.ceil(0.20 * len(g))))
        w6 = set(g.nlargest(k, "rmse_model6_rf")["point_id"])
        w8 = set(g.nlargest(k, "rmse_model8_process")["point_id"])
        inter = w6 & w8
        union = w6 | w8
        rows.append(
            {
                "site": site,
                "n_supports": int(len(g)),
                "worst_set_size": k,
                "shared_worst_supports": len(inter),
                "jaccard_top20pct_worst_rmse": len(inter) / len(union) if union else np.nan,
                "rmse_correlation_model6_model8": finite_corr(g["rmse_model6_rf"], g["rmse_model8_process"]),
                "bias_correlation_model6_model8": finite_corr(g["bias_model6_rf"], g["bias_model8_process"]),
                "model8_better_fraction": float((g["rmse_model6_minus_model8"] > 0).mean()) if "rmse_model6_minus_model8" in g else np.nan,
            }
        )
    return pd.DataFrame(rows)


def training_space_distance(
    validation_rows: pd.DataFrame,
    training_rows: pd.DataFrame,
    feature_cols: list[str],
    feature_set: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [c for c in feature_cols if c in validation_rows.columns and c in training_rows.columns]
    if len(cols) < 3:
        return pd.DataFrame(), pd.DataFrame(
            [{"feature_set": feature_set, "status": "skipped", "reason": "fewer than three common features", "n_common_features": len(cols)}]
        )

    val = validation_rows.dropna(subset=["site", "point_id", "date"]).copy()
    train = training_rows.copy()
    for c in cols:
        val[c] = pd.to_numeric(val[c], errors="coerce")
        train[c] = pd.to_numeric(train[c], errors="coerce")

    # Require at least half the feature set to be observed before imputation.
    val = val[val[cols].notna().mean(axis=1) >= 0.5].reset_index(drop=True)
    train = train[train[cols].notna().mean(axis=1) >= 0.5].reset_index(drop=True)
    if len(val) == 0 or len(train) < 10:
        return pd.DataFrame(), pd.DataFrame(
            [{"feature_set": feature_set, "status": "skipped", "reason": "insufficient rows after feature completeness filter", "n_common_features": len(cols), "n_training_rows": len(train), "n_validation_rows": len(val)}]
        )

    imputer = SimpleImputer(strategy="median")
    scaler = StandardScaler()
    X_train = scaler.fit_transform(imputer.fit_transform(train[cols]))
    X_val = scaler.transform(imputer.transform(val[cols]))

    # Nearest-neighbour distances in standardised feature space. Training
    # self-distance uses k=2 so a row does not identify itself as its neighbour.
    nn_train = NearestNeighbors(n_neighbors=2, metric="euclidean").fit(X_train)
    train_self = nn_train.kneighbors(X_train, return_distance=True)[0][:, 1]
    nn_val = NearestNeighbors(n_neighbors=1, metric="euclidean").fit(X_train)
    val_nn = nn_val.kneighbors(X_val, return_distance=True)[0][:, 0]

    # Mahalanobis-like distance in training PCA coordinates. Because PCA axes are
    # orthogonal, dividing by their training variances gives a stable diagnostic.
    n_comp = min(len(cols), max(2, min(12, X_train.shape[0] - 1)))
    pca = PCA(n_components=n_comp, random_state=0).fit(X_train)
    train_scores = pca.transform(X_train)
    val_scores = pca.transform(X_val)
    keep = np.cumsum(pca.explained_variance_ratio_) <= 0.95
    if not keep.any():
        keep[0] = True
    # Include the first PC that crosses the 95% threshold.
    first_over = np.argmax(np.cumsum(pca.explained_variance_ratio_) >= 0.95)
    keep[: first_over + 1] = True
    var = np.maximum(pca.explained_variance_[keep], 1e-9)
    train_md = np.sqrt(np.sum((train_scores[:, keep] ** 2) / var, axis=1))
    val_md = np.sqrt(np.sum((val_scores[:, keep] ** 2) / var, axis=1))

    dist = val[["site", "point_id", "date", "lon", "lat"] + (["season"] if "season" in val.columns else [])].copy()
    dist["feature_set"] = feature_set
    dist["n_common_features"] = len(cols)
    dist["nn_distance"] = val_nn
    dist["nn_distance_percentile"] = [float((train_self <= d).mean() * 100.0) for d in val_nn]
    dist["mahalanobis_pc_distance"] = val_md
    dist["mahalanobis_pc_percentile"] = [float((train_md <= d).mean() * 100.0) for d in val_md]
    for i in range(min(3, val_scores.shape[1])):
        dist[f"training_PC{i+1}"] = val_scores[:, i]

    summary_rows = []
    for site, g in dist.groupby("site", sort=True, observed=True):
        summary_rows.append(
            {
                "feature_set": feature_set,
                "status": "ok",
                "site": site,
                "n_validation_rows": int(len(g)),
                "n_training_rows": int(len(train)),
                "n_common_features": len(cols),
                "median_nn_percentile": float(np.nanmedian(g["nn_distance_percentile"])),
                "p90_nn_percentile": float(np.nanpercentile(g["nn_distance_percentile"], 90)),
                "fraction_nn_gt95": float((g["nn_distance_percentile"] > 95).mean()),
                "median_mahalanobis_percentile": float(np.nanmedian(g["mahalanobis_pc_percentile"])),
                "fraction_mahalanobis_gt95": float((g["mahalanobis_pc_percentile"] > 95).mean()),
            }
        )
        if "season" in g.columns:
            for season, s in g.groupby("season", sort=True, observed=True):
                summary_rows.append(
                    {
                        "feature_set": feature_set,
                        "status": "ok",
                        "site": site,
                        "season": season,
                        "n_validation_rows": int(len(s)),
                        "n_training_rows": int(len(train)),
                        "n_common_features": len(cols),
                        "median_nn_percentile": float(np.nanmedian(s["nn_distance_percentile"])),
                        "p90_nn_percentile": float(np.nanpercentile(s["nn_distance_percentile"], 90)),
                        "fraction_nn_gt95": float((s["nn_distance_percentile"] > 95).mean()),
                        "median_mahalanobis_percentile": float(np.nanmedian(s["mahalanobis_pc_percentile"])),
                        "fraction_mahalanobis_gt95": float((s["mahalanobis_pc_percentile"] > 95).mean()),
                    }
                )
    return dist, pd.DataFrame(summary_rows)


def write_report(
    report_path: Path,
    pred_path: Path,
    train_path: Path,
    pca_results: list[PcaResult],
    paired: pd.DataFrame,
    centroid_dist: pd.DataFrame,
    overlap: pd.DataFrame,
    pc_corr: pd.DataFrame,
    pc_decomp: pd.DataFrame,
    direct_feature_corr: pd.DataFrame,
    training_summary: pd.DataFrame,
    training_error_corr: pd.DataFrame,
    figure_paths: list[Path],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    rel = lambda p: p.relative_to(report_path.parent).as_posix() if p.exists() else p.as_posix()

    fig_lookup = {p.name: rel(p) for p in figure_paths}
    explained = pd.concat([r.explained for r in pca_results], ignore_index=True)
    top_loadings = (
        pd.concat([r.loadings for r in pca_results], ignore_index=True)
        .sort_values(["feature_set", "scaling", "PC1_PC2_abs_loading"], ascending=[True, True, False])
        .groupby(["feature_set", "scaling"], as_index=False)
        .head(6)
    )

    pc1pc2 = explained[explained["PC"].isin(["PC1", "PC2"])].copy()
    pc1pc2_wide = pc1pc2.pivot_table(index=["feature_set", "scaling"], columns="PC", values="explained_variance_ratio").reset_index()
    for pc in ["PC1", "PC2"]:
        if pc in pc1pc2_wide.columns:
            pc1pc2_wide[pc] = pc1pc2_wide[pc] * 100.0

    if not training_summary.empty and "season" in training_summary.columns:
        headline_training = training_summary[training_summary["season"].isna()].copy()
        seasonal_training = training_summary[training_summary["season"].notna()].copy()
    else:
        headline_training = training_summary.copy() if not training_summary.empty else pd.DataFrame()
        seasonal_training = pd.DataFrame()
    if not headline_training.empty and "status" in headline_training.columns:
        headline_training = headline_training[headline_training["status"].eq("ok")]
    if not seasonal_training.empty and "status" in seasonal_training.columns:
        seasonal_training = seasonal_training[seasonal_training["status"].eq("ok")]

    pc_corr_ranked = (
        pc_corr.reindex(pc_corr["pc_metric_correlation"].abs().sort_values(ascending=False).index)
        if not pc_corr.empty and "pc_metric_correlation" in pc_corr.columns
        else pd.DataFrame()
    )
    if not pc_decomp.empty:
        d = pc_decomp[pc_decomp["scaling"].eq("site_standardised")].copy()
        d["metric_family"] = np.where(d["metric"].str.contains("bias"), "bias", "RMSE")
        decomp_summary = (
            d.groupby(["feature_set", "metric_family", "feature"], as_index=False)
            .agg(
                mean_abs_contribution=("abs_contribution_proxy", "mean"),
                max_abs_contribution=("abs_contribution_proxy", "max"),
                mean_signed_contribution=("signed_contribution_proxy", "mean"),
                n_tests=("abs_contribution_proxy", "size"),
            )
            .sort_values(["feature_set", "metric_family", "mean_abs_contribution"], ascending=[True, True, False])
            .groupby(["feature_set", "metric_family"], as_index=False)
            .head(8)
        )
    else:
        decomp_summary = pd.DataFrame()

    if not direct_feature_corr.empty:
        f = direct_feature_corr.copy()
        f["metric_family"] = np.where(f["metric"].str.contains("bias"), "bias", "RMSE")
        direct_summary = (
            f.groupby(["metric_family", "feature"], as_index=False)
            .agg(
                mean_abs_correlation=("feature_metric_correlation", lambda x: float(np.nanmean(np.abs(x)))),
                max_abs_correlation=("feature_metric_correlation", lambda x: float(np.nanmax(np.abs(x)))),
                n_tests=("feature_metric_correlation", "size"),
            )
            .sort_values(["metric_family", "mean_abs_correlation"], ascending=[True, False])
            .groupby("metric_family", as_index=False)
            .head(10)
        )
    else:
        direct_summary = pd.DataFrame()

    md = f"""# Model-agnostic covariate PCA and terrain residual stratification scaffold

This is a separate diagnostic report for the dense validation work. It is designed to sit beside the main dense-validation manuscript rather than replace it.

## 1. Purpose

The main question is whether the three dense validation sites occupy comparable or distinct parts of the model-agnostic covariate space, and whether model failures occur in the same parts of that space across sites. This matters because a model can have acceptable pooled skill while still failing systematically in particular terrain, soil, exposure, or seasonal-climate contexts.

The analysis is framed around four working hypotheses.

1. **Absolute covariate-space transfer:** if a site sits far from the OzNet training distribution, both model6 and model8 should be treated as extrapolating or semi-extrapolating there.
2. **Covariate-space failure consistency:** if high-error points cluster in the same PCA region across sites, that suggests a transferable structural weakness.
3. **Scale-dependence of PCA:** global-scaled PCA should reveal between-site environmental differences, while site-standardised PCA should reveal within-site wet/dry terrain contrasts after removing site means.
4. **Model-type contrast:** the process model and statistical model may fail in different parts of the terrain/climate covariate space, which is directly relevant to local calibration design.

## 2. Data used

- Validation predictions: `{pred_path}`
- OzNet training covariate table: `{train_path}`
- Validation sites: Esdale, Tarrawarra, and Llara.
- Models compared: model6 statistical RF/HGB and model8 process bucket.

All PCA inputs are model-agnostic covariates already present in the validation prediction table, not covariates from the raw point-measurement CSVs.

## 3. Feature spaces

Three related spaces are scaffolded.

1. **Static terrain-soil space:** elevation, slope, northness, eastness, TWI, HLI, accumulation, clay, sand, AWC, and bulk density. This is the cleanest terrain stratification space.
2. **Dynamic model-agnostic covariate space:** static terrain-soil plus SMIPS totalbucket, SMIPS lookback/anomaly terms, day-of-year terms, and SILO antecedent rainfall/water-balance/VPD terms.
3. **Process-context covariate space:** bucket storage where available plus the static process-model readout/capacity variables available in the unified table. This is included as exploratory because the complete process forcing/static matrix is not yet fully represented in the unified table for every site.

## 4. PCA methodology

### 4.1 Global-scaled PCA

For each feature space, features are median-imputed and standardised once across pooled validation supports. PCA is then fitted to the pooled support matrix. This preserves absolute between-site differences. Large separation of site centroids means the sites occupy different parts of covariate space.

Interpretation: this is the right view for asking whether Esdale, Tarrawarra, and Llara are genuinely different environments to the model.

### 4.2 Site-standardised PCA

For each site, every feature is z-scored within that site before fitting PCA across all supports. This removes the site-average environmental offset and keeps within-site structure. Local covariate extremes therefore become comparable across sites even when the absolute covariate distributions differ.

Interpretation: this is the right view for asking whether models fail in analogous within-property terrain positions.

## 5. Distance from training covariate space

Where the OzNet training covariate table is available, validation rows are compared with the training distribution in standardised feature space. Two distances are reported.

1. **Nearest-neighbour distance percentile:** distance from each validation row to its nearest OzNet training row, expressed as a percentile of OzNet leave-one-neighbour distances.
2. **Training-PCA Mahalanobis distance percentile:** validation rows are projected into PCA fitted on OzNet training rows. Distance from the OzNet centre is scaled by training PC variance and expressed as a percentile of training-row distances.

Rows above the 95th percentile are flagged as practically out-of-distribution for that feature space. This does not prove the prediction is wrong; it says the prediction is being made in a part of covariate space with weak training support.

## 6. Residual stratification methodology

For each site and support point/grid cell, observed and predicted soil moisture are summarised into support-level metrics. The PCA residual decomposition deliberately focuses on only two response variables:

1. **Bias**: prediction minus observation, used to diagnose signed wet/dry structure.
2. **RMSE**: error magnitude, used to diagnose unreliable regions regardless of sign.

NSE, Pearson r, and ubRMSE remain important validation metrics in the main manuscript, but they are not used here as PC-decomposition targets.

The diagnostic outputs are:

- high-RMSE locations in PCA space for each model;
- signed-bias locations in PCA space for each model;
- model6-minus-model8 RMSE difference in PCA space;
- correlations between PC axes and support-level RMSE and bias;
- a loading-weighted decomposition that identifies which covariates dominate the PC axes most associated with RMSE and bias;
- overlap between the worst 20% of supports for model6 and model8.

If both models fail on the same supports, this suggests a shared missing process, measurement/support mismatch, or terrain state not captured by the available inputs. If only one model fails, that gives clues about process-model versus statistical-model vulnerabilities.

## 7. Headline numeric outputs from this run

### PCA variance explained

{robust_markdown_table(pc1pc2_wide, max_rows=20)}

### Site centroid distances in validation PCA space

{robust_markdown_table(centroid_dist.sort_values(["feature_set", "scaling", "site_a", "site_b"]), max_rows=40)}

### Model failure overlap by site

{robust_markdown_table(overlap, ["site", "n_supports", "worst_set_size", "shared_worst_supports", "jaccard_top20pct_worst_rmse", "rmse_correlation_model6_model8", "bias_correlation_model6_model8", "model8_better_fraction"], max_rows=20)}

### Distance from OzNet training space

{robust_markdown_table(headline_training, ["feature_set", "site", "n_validation_rows", "n_common_features", "median_nn_percentile", "p90_nn_percentile", "fraction_nn_gt95", "median_mahalanobis_percentile", "fraction_mahalanobis_gt95"], max_rows=40)}

### Seasonal distance from OzNet training space

{robust_markdown_table(seasonal_training, ["feature_set", "site", "season", "n_validation_rows", "median_nn_percentile", "fraction_nn_gt95", "median_mahalanobis_percentile", "fraction_mahalanobis_gt95"], max_rows=40)}

### Correlation between training distance and absolute error

{robust_markdown_table(training_error_corr, ["feature_set", "base_model", "n", "distance_abs_error_correlation", "median_abs_error_in_distribution", "median_abs_error_above_95pct"], max_rows=20)}

### Strongest PC associations with bias and RMSE

{robust_markdown_table(pc_corr_ranked, ["feature_set", "scaling", "site", "pc_axis", "metric", "pc_metric_correlation", "n_supports"], max_rows=30)}

### Site-standardised PC feature decomposition

This table back-projects the PC/error correlations through the PCA loadings. It is a diagnostic ranking, not a causal attribution model.

{robust_markdown_table(decomp_summary, ["feature_set", "metric_family", "feature", "mean_abs_contribution", "max_abs_contribution", "mean_signed_contribution", "n_tests"], max_rows=40)}

### Direct site-standardised covariate/error correlations

This is a simpler companion diagnostic: support-level covariates are standardised within each site, then directly correlated with bias and RMSE metrics.

{robust_markdown_table(direct_summary, ["metric_family", "feature", "mean_abs_correlation", "max_abs_correlation", "n_tests"], max_rows=24)}

### Dominant PCA loadings

{robust_markdown_table(top_loadings, ["feature_set", "scaling", "feature", "PC1_loading", "PC2_loading", "PC1_PC2_abs_loading"], max_rows=80)}

## 8. Figures

### Static terrain-soil PCA

![Static global PCA sites]({fig_lookup.get("static_terrain_soil_global_site_pca.png", "")})

![Static site-standardised PCA sites]({fig_lookup.get("static_terrain_soil_site_standardised_site_pca.png", "")})

![Static global PCA RMSE]({fig_lookup.get("static_terrain_soil_global_rmse_pca.png", "")})

![Static global PCA bias]({fig_lookup.get("static_terrain_soil_global_bias_pca.png", "")})

![Static site-standardised PCA RMSE]({fig_lookup.get("static_terrain_soil_site_standardised_rmse_pca.png", "")})

![Static site-standardised PCA bias]({fig_lookup.get("static_terrain_soil_site_standardised_bias_pca.png", "")})

![Static global model difference]({fig_lookup.get("static_terrain_soil_global_model_difference_pca.png", "")})

![Static site-standardised model difference]({fig_lookup.get("static_terrain_soil_site_standardised_model_difference_pca.png", "")})

### Dynamic model-agnostic covariate PCA and training distance

![Dynamic covariate global PCA sites]({fig_lookup.get("model_agnostic_covariates_global_site_pca.png", "")})

![Dynamic covariate site-standardised PCA sites]({fig_lookup.get("model_agnostic_covariates_site_standardised_site_pca.png", "")})

![Dynamic covariate training distance]({fig_lookup.get("model_agnostic_covariates_training_distance_by_site.png", "")})

![Dynamic covariate seasonal Mahalanobis distance]({fig_lookup.get("model_agnostic_covariates_training_mahalanobis_by_site_season.png", "")})

![Dynamic covariate seasonal distance skill]({fig_lookup.get("model_agnostic_covariates_seasonal_distance_skill.png", "")})

![Dynamic covariate distance error]({fig_lookup.get("model_agnostic_covariates_training_distance_vs_abs_error.png", "")})

## 9. Interpretation guardrails

- PCA axes are descriptive rotations of correlated covariates; they are not physical mechanisms by themselves. Loadings should be used to name axes cautiously.
- Global-scaled PCA is best for between-site transfer questions. Site-standardised PCA is best for within-site terrain analogues. These are complementary rather than competing versions.
- Training distance is covariate-space distance, not geographic distance. A point can be geographically close to OzNet-like terrain and still be seasonally outlying in the dynamic covariate space.
- Tarrawarra observations have been aggregated to the 30 m prediction support in the upstream validation table; residual sub-pixel variation should still be treated as support mismatch where within-cell variance is high.
- The model8 process-context PCA is exploratory until the unified table carries the complete process-model forcing/static variables for every site.

## 10. Suggested manuscript use

For the publication-facing report, I would use:

1. one global-scaled static terrain-soil PCA panel to show site separation;
2. one site-standardised static PCA panel coloured by RMSE and bias to show whether bad supports occupy analogous covariate positions;
3. one dynamic covariate-space training-distance figure to quantify how far each validation site/date is from OzNet;
4. a small table of PC-decomposed bias/RMSE associations and worst-support overlap.

That combination keeps the story sharp: first, where are these sites relative to each other and to training; second, are the failures terrain-structured; third, does the process model fail differently from the statistical model?
"""
    report_path.write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--training-table", type=Path, default=DEFAULT_TRAINING_TABLE)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--figdir", type=Path, default=DEFAULT_FIGDIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    args.figdir.mkdir(parents=True, exist_ok=True)

    pred = load_predictions(args.predictions)
    pred.to_csv(args.outdir / "input_predictions_normalised.csv", index=False)

    metrics = metric_by_support(pred)
    paired = paired_support_metrics(metrics)
    metrics.to_csv(args.outdir / "support_level_metrics_long.csv", index=False)
    paired.to_csv(args.outdir / "support_level_metrics_paired.csv", index=False)

    pca_results: list[PcaResult] = []
    figure_paths: list[Path] = []
    scores_all = []
    loadings_all = []
    explained_all = []
    centroid_all = []
    corr_all = []

    for feature_set, requested in FEATURE_SETS.items():
        base_support = support_features(pred, requested)
        feature_cols = existing_features(base_support, requested)
        if len(feature_cols) < 3:
            continue
        # Skip process-context PCA when the only process-only feature is too
        # sparse; keep static/process statics in the static analysis instead.
        if feature_set == "process_context_covariates" and "model8_storage_mm" not in feature_cols:
            continue

        for scaling in ["global", "site_standardised"]:
            result = fit_validation_pca(base_support, feature_cols, feature_set, scaling)
            pca_results.append(result)
            scores_all.append(result.scores)
            loadings_all.append(result.loadings)
            explained_all.append(result.explained)
            centroid_all.append(site_centroid_distances(result.scores))
            corr_all.append(pc_residual_correlations(result.scores, paired))
            figure_paths.extend(
                [
                    plot_site_pca(result, args.figdir),
                    plot_rmse_pca(result, paired, args.figdir),
                    plot_bias_pca(result, paired, args.figdir),
                    plot_model_difference_pca(result, paired, args.figdir),
                ]
            )

    scores_cat = pd.concat(scores_all, ignore_index=True)
    loadings_cat = pd.concat(loadings_all, ignore_index=True)
    explained_cat = pd.concat(explained_all, ignore_index=True)
    scores_cat.to_csv(args.outdir / "pca_scores_supports.csv", index=False)
    loadings_cat.to_csv(args.outdir / "pca_loadings.csv", index=False)
    explained_cat.to_csv(args.outdir / "pca_explained_variance.csv", index=False)
    centroid_dist = pd.concat(centroid_all, ignore_index=True) if centroid_all else pd.DataFrame()
    pc_corr = pd.concat(corr_all, ignore_index=True) if corr_all else pd.DataFrame()
    pc_decomp = pc_feature_decomposition(loadings_cat, pc_corr)
    direct_feature_corr = site_standardised_feature_error_correlations(pred, paired)
    centroid_dist.to_csv(args.outdir / "site_centroid_distances.csv", index=False)
    pc_corr.to_csv(args.outdir / "pc_residual_correlations.csv", index=False)
    pc_decomp.to_csv(args.outdir / "pc_bias_rmse_feature_decomposition.csv", index=False)
    direct_feature_corr.to_csv(args.outdir / "site_standardised_feature_error_correlations.csv", index=False)

    overlap = worst_support_overlap(paired)
    overlap.to_csv(args.outdir / "worst_support_overlap.csv", index=False)

    training_dist_all = []
    training_summary_all = []
    training_error_corr_rows = []
    if args.training_table.exists():
        training = pd.read_csv(args.training_table, low_memory=False)
        for feature_set in ["static_terrain_soil", "model_agnostic_covariates"]:
            requested = FEATURE_SETS[feature_set]
            obs_rows = observation_feature_rows(pred, requested)
            training_for_feature = training
            if feature_set == "static_terrain_soil" and "station" in training.columns:
                numeric_cols = [c for c in requested if c in training.columns]
                training_for_feature = (
                    training[["station", *numeric_cols]]
                    .groupby("station", as_index=False, observed=True)
                    .median(numeric_only=True)
                )
            dist, summary = training_space_distance(obs_rows, training_for_feature, requested, feature_set)
            if not dist.empty:
                training_dist_all.append(dist)
                figure_paths.append(plot_training_distance(dist, args.figdir, feature_set))
                figure_paths.append(plot_distance_error(dist, pred, args.figdir, feature_set))
                seasonal_distance_fig = plot_training_distance_by_season(dist, args.figdir, feature_set)
                if seasonal_distance_fig is not None:
                    figure_paths.append(seasonal_distance_fig)
                seasonal_skill_fig = plot_seasonal_distance_skill(dist, pred, args.figdir, feature_set)
                if seasonal_skill_fig is not None:
                    figure_paths.append(seasonal_skill_fig)
                joined = pred.merge(dist[["site", "point_id", "date", "nn_distance_percentile"]], on=["site", "point_id", "date"], how="inner")
                for model, g in joined.groupby("base_model", sort=True, observed=True):
                    inside = g[g["nn_distance_percentile"] <= 95]
                    outside = g[g["nn_distance_percentile"] > 95]
                    training_error_corr_rows.append(
                        {
                            "feature_set": feature_set,
                            "base_model": model,
                            "n": int(len(g)),
                            "distance_abs_error_correlation": finite_corr(g["nn_distance_percentile"], g["abs_error"]),
                            "median_abs_error_in_distribution": float(np.nanmedian(inside["abs_error"])) if len(inside) else np.nan,
                            "median_abs_error_above_95pct": float(np.nanmedian(outside["abs_error"])) if len(outside) else np.nan,
                        }
                    )
            training_summary_all.append(summary)
    else:
        training_summary_all.append(
            pd.DataFrame(
                [
                    {
                        "feature_set": "static_terrain_soil",
                        "status": "missing_training_table",
                        "reason": str(args.training_table),
                    }
                ]
            )
        )

    training_dist = pd.concat(training_dist_all, ignore_index=True) if training_dist_all else pd.DataFrame()
    training_summary = pd.concat(training_summary_all, ignore_index=True) if training_summary_all else pd.DataFrame()
    training_error_corr = pd.DataFrame(training_error_corr_rows)
    training_dist.to_csv(args.outdir / "training_space_distances_by_validation_row.csv", index=False)
    training_summary.to_csv(args.outdir / "training_space_distance_summary.csv", index=False)
    training_error_corr.to_csv(args.outdir / "training_distance_error_correlations.csv", index=False)

    manifest = {
        "predictions": str(args.predictions),
        "training_table": str(args.training_table),
        "outdir": str(args.outdir),
        "figdir": str(args.figdir),
        "report": str(args.report),
        "feature_sets": {k: v for k, v in FEATURE_SETS.items()},
        "figures": [str(p) for p in figure_paths],
    }
    (args.outdir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    write_report(
        args.report,
        args.predictions,
        args.training_table,
        pca_results,
        paired,
        centroid_dist,
        overlap,
        pc_corr,
        pc_decomp,
        direct_feature_corr,
        training_summary,
        training_error_corr,
        figure_paths,
    )

    print(f"Wrote report: {args.report}")
    print(f"Wrote tables: {args.outdir}")
    print(f"Wrote figures: {args.figdir}")


if __name__ == "__main__":
    main()
