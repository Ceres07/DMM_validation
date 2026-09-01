#!/usr/bin/env python3
"""Stage 2 local-spiking calibration experiment across dense validation sites.

Purpose
-------
This is the local-calibration half of the unified dense-validation plan. The
practical question is deliberately property-management flavoured:

    If a landowner can afford only a few local soil-moisture sensors, where
    should they go, and does that small local information budget improve
    model6 RF and model8 process predictions differently?

The experiment uses the retained model-ready validation datasets:

- Esdale (formerly "dense validation");
- Tarrawarra;
- Nerrigundah;
- Llara;
- MRI.

For each site, local calibration points are selected under strategies that use
either no soil-moisture information (random), model/terrain priors, or an
explicitly labelled field-knowledge proxy for chronic wet/dry positions. Small
calibration layers are fitted on selected point/date observations and evaluated
with spatial, temporal and strict spatio-temporal blocking.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")


DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[3]
SRC = DMM_VALIDATION_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dmm_validation.metrics import soil_moisture_metrics  # noqa: E402
from dmm_validation.reporting import markdown_table  # noqa: E402
from dmm_validation.schema import prepare_prediction_table  # noqa: E402
from dmm_validation.seasons import add_season_columns  # noqa: E402


DEFAULT_OUTDIR = DMM_VALIDATION_ROOT / "outputs" / "unified_dense_validation" / "stage2_local_spiking"
DEFAULT_REPORT = (
    DMM_VALIDATION_ROOT
    / "reports"
    / "analyses"
    / "unified_dense_validation"
    / "stage2_local_spiking_report.md"
)
DEFAULT_REPORT_FIGDIR = (
    DMM_VALIDATION_ROOT
    / "reports"
    / "analyses"
    / "unified_dense_validation"
    / "figures"
    / "stage2_local_spiking"
)

REPORT_FIGURES = (
    (
        "baseline_site_model_skill.png",
        "Uncalibrated global model skill by validation site",
        "Baseline RMSE and NSE for model6 RF and model8 process before any local calibration.",
    ),
    (
        "prior_guided_spatiotemporal_learning_curves_rmse_gain.png",
        "Strict spatio-temporal prior-guided learning curves: RMSE gain",
        "Best RMSE gain from deployable non-random placement priors under the strict spatial+temporal block.",
    ),
    (
        "prior_guided_spatiotemporal_learning_curves_nse.png",
        "Strict spatio-temporal prior-guided learning curves: NSE",
        "Best held-out NSE from deployable non-random placement priors under the strict spatial+temporal block.",
    ),
    (
        "prior_guided_process_vs_statistical_responsiveness.png",
        "Process-vs-statistical responsiveness under prior-guided placement",
        "Positive values indicate model8 process gains more from the same deployable non-random placement strategy than model6 RF.",
    ),
    (
        "random_spatiotemporal_learning_curves_rmse_gain.png",
        "Appendix: random strict spatio-temporal learning curves, RMSE gain",
        "Median RMSE gain from random sparse local sensors when calibration and validation are separated in space and time.",
    ),
    (
        "random_spatiotemporal_learning_curves_nse.png",
        "Appendix: random strict spatio-temporal learning curves, NSE",
        "Median held-out NSE from random sparse local sensors when calibration and validation are separated in space and time.",
    ),
    (
        "process_vs_statistical_responsiveness_random.png",
        "Appendix: process-vs-statistical responsiveness under random placement",
        "Positive values indicate model8 process gains more from the same random sparse calibration budget than model6 RF.",
    ),
)

SITE_PATHS = {
    "Esdale": DMM_VALIDATION_ROOT / "outputs" / "model6_vs_model8_dense" / "model6_model8_combined_predictions.csv",
    # Tarrawarra campaign points are much denser than the model raster support.
    # Treat the model grid cell, not the raw probe point, as the validation unit.
    "Tarrawarra": DMM_VALIDATION_ROOT
    / "outputs"
    / "tarrawarra_model6_vs_model8"
    / "model6_model8_combined_predictions_valid_30m_gridcell.csv",
    "Nerrigundah": DMM_VALIDATION_ROOT
    / "outputs"
    / "nerrigundah_model6_vs_model8"
    / "model6_model8_combined_predictions_valid_30m_gridcell.csv",
    "Llara": DMM_VALIDATION_ROOT / "outputs" / "llara_unseen_model6_vs_model8" / "llara_model6_model8_predictions.csv",
    "MRI": DMM_VALIDATION_ROOT / "outputs" / "mri_dense_validation" / "mri_model6_model8_predictions.csv",
}

SITE_QC_START_DATES = {
    "Llara": "2022-01-01",
    "MRI": "2021-07-01",
}

MODEL_NAME_MAP = {
    "model6": "model6_rf",
    "model6_rf": "model6_rf",
    "model8": "model8_process",
    "model8_process": "model8_process",
}

MODEL_TRACK = {
    "model6_rf": "statistical_rf",
    "model8_process": "process_bucket",
}

BLOCKS = ["spatial_block", "temporal_block", "spatiotemporal_block"]
METHODS = ["global", "bias_offset", "seasonal_offset", "affine", "residual_ridge"]
CALIBRATION_METHODS = [m for m in METHODS if m != "global"]
SELECTION_STRATEGIES = [
    "random",
    "landscape_wetdry_prior",
    "global_prediction_extremes",
    "field_knowledge_wetdry_proxy",
]
DEPLOYABLE_PRIOR_STRATEGIES = ["landscape_wetdry_prior", "global_prediction_extremes"]

RESIDUAL_FEATURES = [
    "pred_sm_pct",
    "doy_sin",
    "doy_cos",
    "smips_totalbucket",
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
    "model8_storage_mm",
]

WETNESS_FEATURE_WEIGHTS = {
    "twi": 1.0,
    "soil_awc": 0.7,
    "smips_totalbucket": 0.4,
    "northness": -0.25,  # north-facing slopes tend to be hotter/drier here
    "hli": -0.7,
    "slope": -0.35,
    "elevation": -0.2,
}


def ordered_sites(values: pd.Series | list[str] | set[str]) -> list[str]:
    order = ["Esdale", "Tarrawarra", "Nerrigundah", "Llara", "MRI"]
    seen = {str(v) for v in values if pd.notna(v)}
    out = [site for site in order if site in seen]
    out.extend(sorted(seen.difference(out)))
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--report-figdir", type=Path, default=DEFAULT_REPORT_FIGDIR)
    parser.add_argument(
        "--budgets",
        default="3,5,10,25%,50%,all",
        help="Comma-separated point budgets. Supports integers, percentages such as 25%%, and all.",
    )
    parser.add_argument("--random-reps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--train-date-fraction", type=float, default=0.33)
    parser.add_argument("--min-train-dates", type=int, default=3)
    return parser.parse_args(argv)


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path).replace([np.inf, -np.inf], np.nan)


def zscore(values: pd.Series) -> pd.Series:
    vals = pd.to_numeric(values, errors="coerce")
    std = vals.std(skipna=True)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=values.index)
    return (vals - vals.mean(skipna=True)) / std


def parse_budget_specs(text: str) -> list[str]:
    specs: list[str] = []
    seen: set[str] = set()
    for raw in text.split(","):
        spec = raw.strip().lower()
        if not spec:
            continue
        if spec == "100%":
            spec = "all"
        if spec not in seen:
            specs.append(spec)
            seen.add(spec)
    return specs


def resolve_budget(spec: str, n_eligible: int) -> tuple[str, int]:
    """Resolve an integer/percentage/all budget for a specific site."""
    if n_eligible <= 0:
        return spec, 0
    if spec == "all":
        return "all", int(n_eligible)
    if spec.endswith("%"):
        pct = float(spec[:-1]) / 100.0
        n = int(math.ceil(n_eligible * pct))
        return spec, max(1, min(n, int(n_eligible)))
    n = int(spec)
    return str(n), max(1, min(n, int(n_eligible)))


def load_site(site: str, path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SystemExit(f"Missing {site} prediction table: {path}")
    raw = read_csv(path)
    raw["model_name"] = raw["model_name"].astype(str).map(MODEL_NAME_MAP).fillna(raw["model_name"].astype(str))
    raw = raw[raw["model_name"].isin(["model6_rf", "model8_process"])].copy()
    df = prepare_prediction_table(raw)
    qc_start = SITE_QC_START_DATES.get(site)
    if qc_start is not None:
        df = df[df["date"] >= qc_start].copy()
    df["site"] = site
    df["base_model"] = df["model_name"]
    df["model_track"] = df["base_model"].map(MODEL_TRACK)
    return df


def split_dates(dates: list[str], train_fraction: float, min_train_dates: int) -> tuple[set[str], set[str]]:
    dates = sorted(pd.to_datetime(pd.Series(dates)).dt.date.astype(str).unique())
    if len(dates) < 2:
        return set(dates), set()
    n_train = int(math.ceil(len(dates) * train_fraction))
    n_train = max(1, n_train)
    if len(dates) > min_train_dates:
        n_train = max(n_train, min_train_dates)
    n_train = min(n_train, len(dates) - 1)
    return set(dates[:n_train]), set(dates[n_train:])


def site_point_summary(df: pd.DataFrame, train_dates: set[str], future_dates: set[str]) -> pd.DataFrame:
    # Use model6 rows if present to avoid duplicated point summaries; otherwise
    # fall back to the first available model.
    base_model = "model6_rf" if "model6_rf" in set(df["base_model"]) else sorted(df["base_model"].unique())[0]
    one = df[df["base_model"] == base_model].copy()
    numeric_cols = [
        c
        for c in WETNESS_FEATURE_WEIGHTS
        if c in one.columns and pd.api.types.is_numeric_dtype(one[c])
    ]
    agg_spec = {
        "lon": ("lon", "mean"),
        "lat": ("lat", "mean"),
        "obs_mean": ("obs_sm_pct", "mean"),
        "obs_sd": ("obs_sm_pct", "std"),
        "global_pred_mean": ("pred_sm_pct", "mean"),
        "global_pred_sd": ("pred_sm_pct", "std"),
        "n_rows": ("date", "size"),
        "n_dates": ("date", lambda x: pd.Series(x).nunique()),
    }
    for col in numeric_cols:
        agg_spec[col] = (col, "mean")
    out = one.groupby("point_id", as_index=False).agg(**agg_spec)
    date_sets = one.groupby("point_id")["date"].agg(lambda x: set(x))
    out["has_train_dates"] = out["point_id"].map(lambda p: bool(date_sets.loc[p] & train_dates))
    out["has_future_dates"] = out["point_id"].map(lambda p: bool(date_sets.loc[p] & future_dates))
    out["eligible"] = out["has_train_dates"] & out["has_future_dates"]

    wetness = pd.Series(0.0, index=out.index)
    used = []
    for col, weight in WETNESS_FEATURE_WEIGHTS.items():
        if col in out.columns:
            wetness = wetness + weight * zscore(out[col])
            used.append(col)
    out["landscape_wetness_score"] = wetness
    out["landscape_wetness_features"] = ",".join(used)
    out["global_prediction_score"] = out["global_pred_mean"]
    out["field_knowledge_proxy_score"] = out["obs_mean"]
    return out


def alternating_extreme_points(summary: pd.DataFrame, score_col: str, budget: int, rng: np.random.Generator) -> list[str]:
    eligible = summary[summary["eligible"]].dropna(subset=[score_col]).copy()
    if eligible.empty:
        eligible = summary[summary["eligible"]].copy()
    if eligible.empty:
        return []
    if score_col not in eligible or eligible[score_col].nunique(dropna=True) < 2:
        n = min(budget, len(eligible))
        return eligible["point_id"].iloc[rng.choice(len(eligible), size=n, replace=False)].astype(str).tolist()

    # For one point, pick the most extreme chronic dry/wet position. For more
    # points, alternate dry and wet extremes to represent landowner knowledge of
    # "that ridge dries first" and "that swale stays wet".
    centre = eligible[score_col].median()
    eligible["abs_extreme"] = (eligible[score_col] - centre).abs()
    if budget == 1:
        return [str(eligible.sort_values("abs_extreme", ascending=False).iloc[0]["point_id"])]

    low = eligible.sort_values(score_col, ascending=True)["point_id"].astype(str).tolist()
    high = eligible.sort_values(score_col, ascending=False)["point_id"].astype(str).tolist()
    selected: list[str] = []
    i = j = 0
    while len(selected) < min(budget, len(eligible)):
        if i < len(low) and low[i] not in selected:
            selected.append(low[i])
        i += 1
        if len(selected) >= min(budget, len(eligible)):
            break
        if j < len(high) and high[j] not in selected:
            selected.append(high[j])
        j += 1
    return selected


def select_points(
    summary: pd.DataFrame,
    strategy: str,
    budget: int,
    rng: np.random.Generator,
) -> list[str]:
    eligible = summary[summary["eligible"]].copy()
    if eligible.empty:
        return []
    budget = min(budget, len(eligible))
    if strategy == "random":
        idx = rng.choice(len(eligible), size=budget, replace=False)
        return eligible.iloc[idx]["point_id"].astype(str).tolist()
    if strategy == "landscape_wetdry_prior":
        return alternating_extreme_points(eligible, "landscape_wetness_score", budget, rng)
    if strategy == "global_prediction_extremes":
        return alternating_extreme_points(eligible, "global_prediction_score", budget, rng)
    if strategy == "field_knowledge_wetdry_proxy":
        return alternating_extreme_points(eligible, "field_knowledge_proxy_score", budget, rng)
    raise ValueError(f"unknown selection strategy: {strategy}")


def masks_for_block(
    df: pd.DataFrame,
    selected_points: list[str],
    train_dates: set[str],
    future_dates: set[str],
    block: str,
) -> tuple[pd.Series, pd.Series]:
    selected = df["point_id"].isin(selected_points)
    train_time = df["date"].isin(train_dates)
    future_time = df["date"].isin(future_dates)
    if block == "spatial_block":
        return selected, ~selected
    if block == "temporal_block":
        return selected & train_time, selected & future_time
    if block == "spatiotemporal_block":
        return selected & train_time, (~selected) & future_time
    raise ValueError(f"unknown block: {block}")


def fit_clip_bounds(df: pd.DataFrame, cols: list[str], lo_q: float = 0.01, hi_q: float = 0.99) -> dict[str, tuple[float, float]]:
    bounds: dict[str, tuple[float, float]] = {}
    for col in cols:
        vals = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if vals.empty:
            continue
        lo, hi = np.quantile(vals, [lo_q, hi_q])
        if np.isfinite(lo) and np.isfinite(hi) and lo < hi:
            bounds[col] = (float(lo), float(hi))
    return bounds


def apply_clip_bounds(df: pd.DataFrame, bounds: dict[str, tuple[float, float]]) -> pd.DataFrame:
    out = df.copy()
    for col, (lo, hi) in bounds.items():
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").clip(lower=lo, upper=hi)
    return out


@dataclass
class Calibrator:
    method: str
    predict: Callable[[pd.DataFrame], np.ndarray]
    metadata: dict


def clip_prediction(values: np.ndarray) -> np.ndarray:
    return np.clip(np.asarray(values, dtype=float), 0.0, 100.0)


def fit_bias_offset(train: pd.DataFrame) -> Calibrator:
    residual = train["obs_sm_pct"].to_numpy(dtype=float) - train["pred_sm_pct"].to_numpy(dtype=float)
    bias = float(np.nanmean(residual)) if np.isfinite(residual).any() else 0.0

    def predict(df: pd.DataFrame) -> np.ndarray:
        return clip_prediction(df["pred_sm_pct"].to_numpy(dtype=float) + bias)

    return Calibrator("bias_offset", predict, {"bias_obs_minus_pred": bias, "n_train": int(len(train))})


def fit_seasonal_offset(train: pd.DataFrame) -> Calibrator:
    residual = train["obs_sm_pct"].to_numpy(dtype=float) - train["pred_sm_pct"].to_numpy(dtype=float)
    global_bias = float(np.nanmean(residual)) if np.isfinite(residual).any() else 0.0
    if "season" not in train.columns or train["season"].nunique(dropna=True) < 1:
        bias_fit = fit_bias_offset(train)
        meta = {"fallback": "bias_offset", "reason": "no_season_column", **bias_fit.metadata}
        return Calibrator("seasonal_offset", bias_fit.predict, meta)

    tmp = train.copy()
    tmp["_residual_obs_minus_pred"] = tmp["obs_sm_pct"] - tmp["pred_sm_pct"]
    season_bias = (
        tmp.groupby("season", observed=True)["_residual_obs_minus_pred"]
        .mean()
        .dropna()
        .astype(float)
        .to_dict()
    )

    def predict(df: pd.DataFrame) -> np.ndarray:
        offsets = df["season"].astype(str).map({str(k): v for k, v in season_bias.items()}).fillna(global_bias)
        return clip_prediction(df["pred_sm_pct"].to_numpy(dtype=float) + offsets.to_numpy(dtype=float))

    return Calibrator(
        "seasonal_offset",
        predict,
        {
            "global_bias_obs_minus_pred": global_bias,
            "season_bias_obs_minus_pred": {str(k): float(v) for k, v in season_bias.items()},
            "n_train": int(len(train)),
        },
    )


def fit_affine(train: pd.DataFrame) -> Calibrator:
    sub = train[["pred_sm_pct", "obs_sm_pct"]].dropna()
    if len(sub) < 4 or sub["pred_sm_pct"].std() <= 1e-6:
        bias_fit = fit_bias_offset(train)
        meta = {"fallback": "bias_offset", **bias_fit.metadata}
        return Calibrator("affine", bias_fit.predict, meta)

    slope, intercept = np.polyfit(sub["pred_sm_pct"], sub["obs_sm_pct"], deg=1)
    slope = float(np.clip(slope, 0.0, 2.5))
    intercept = float(sub["obs_sm_pct"].mean() - slope * sub["pred_sm_pct"].mean())

    def predict(df: pd.DataFrame) -> np.ndarray:
        return clip_prediction(intercept + slope * df["pred_sm_pct"].to_numpy(dtype=float))

    return Calibrator("affine", predict, {"intercept": intercept, "slope": slope, "n_train": int(len(sub))})


def fit_residual_ridge(train: pd.DataFrame) -> Calibrator:
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import RidgeCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    cols = [
        c
        for c in RESIDUAL_FEATURES
        if c in train.columns and pd.api.types.is_numeric_dtype(train[c])
        and pd.to_numeric(train[c], errors="coerce").notna().any()
    ]
    if len(train) < 5 or not cols:
        bias_fit = fit_bias_offset(train)
        meta = {"fallback": "bias_offset", "reason": "too_few_rows_or_no_features", **bias_fit.metadata}
        return Calibrator("residual_ridge", bias_fit.predict, meta)

    bounds = fit_clip_bounds(train, cols)
    train_x = apply_clip_bounds(train, bounds)
    y = train_x["obs_sm_pct"].to_numpy(dtype=float) - train_x["pred_sm_pct"].to_numpy(dtype=float)
    x = train_x[cols]
    ok = np.isfinite(y)
    if ok.sum() < 5:
        bias_fit = fit_bias_offset(train)
        meta = {"fallback": "bias_offset", "reason": "too_few_finite_residuals", **bias_fit.metadata}
        return Calibrator("residual_ridge", bias_fit.predict, meta)

    pipe = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
            ("ridge", RidgeCV(alphas=np.logspace(1, 5, 18))),
        ]
    )
    pipe.fit(x.loc[ok], y[ok])

    def predict(df: pd.DataFrame) -> np.ndarray:
        x_new = apply_clip_bounds(df, bounds)
        residual = pipe.predict(x_new[cols])
        return clip_prediction(df["pred_sm_pct"].to_numpy(dtype=float) + residual)

    return Calibrator(
        "residual_ridge",
        predict,
        {
            "features": cols,
            "feature_clip_bounds": {k: [v[0], v[1]] for k, v in bounds.items()},
            "alpha": float(pipe.named_steps["ridge"].alpha_),
            "n_train": int(ok.sum()),
        },
    )


def fit_calibrator(train: pd.DataFrame, method: str) -> Calibrator:
    if method == "bias_offset":
        return fit_bias_offset(train)
    if method == "seasonal_offset":
        return fit_seasonal_offset(train)
    if method == "affine":
        return fit_affine(train)
    if method == "residual_ridge":
        return fit_residual_ridge(train)
    raise ValueError(method)


def metric_row(obs: pd.Series, pred: np.ndarray) -> dict:
    return soil_moisture_metrics(obs, pred)


def evaluate_design(
    site_df: pd.DataFrame,
    site: str,
    selected_points: list[str],
    train_dates: set[str],
    future_dates: set[str],
    block: str,
    strategy: str,
    budget_label: str,
    budget: int,
    replicate: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    metrics_rows: list[dict] = []
    season_rows: list[dict] = []
    fit_rows: list[dict] = []

    for base_model, model_df in site_df.groupby("base_model", observed=True):
        train_mask, test_mask = masks_for_block(model_df, selected_points, train_dates, future_dates, block)
        train = model_df.loc[train_mask].copy()
        test = model_df.loc[test_mask].copy()
        if len(test) < 2 or len(train) < 1:
            continue

        baseline = metric_row(test["obs_sm_pct"], test["pred_sm_pct"].to_numpy(dtype=float))
        base_prefix = {
            "site": site,
            "base_model": base_model,
            "model_track": MODEL_TRACK.get(base_model, base_model),
            "block": block,
            "selection_strategy": strategy,
            "budget_label": budget_label,
            "calibration_points": budget,
            "replicate": replicate,
            "method": "global",
            "n_train": int(len(train)),
            "n_test": int(len(test)),
            "n_selected_points": int(len(selected_points)),
            "n_train_dates": int(len(train_dates)),
            "n_future_dates": int(len(future_dates)),
        }
        row = {**base_prefix, **baseline}
        row.update(
            {
                "baseline_rmse": baseline["rmse"],
                "baseline_nse": baseline["nse"],
                "baseline_bias": baseline["bias"],
                "delta_rmse": 0.0,
                "rmse_gain": 0.0,
                "delta_nse": 0.0,
                "delta_abs_bias": 0.0,
            }
        )
        metrics_rows.append(row)

        for season, group in test.groupby("season", observed=True):
            s_metrics = metric_row(group["obs_sm_pct"], group["pred_sm_pct"].to_numpy(dtype=float))
            season_rows.append({**base_prefix, "season": str(season), **s_metrics})

        for method in CALIBRATION_METHODS:
            calibrator = fit_calibrator(train, method)
            pred = calibrator.predict(test)
            metrics = metric_row(test["obs_sm_pct"], pred)
            metric_prefix = {**base_prefix, "method": method}
            out_row = {**metric_prefix, **metrics}
            out_row.update(
                {
                    "baseline_rmse": baseline["rmse"],
                    "baseline_nse": baseline["nse"],
                    "baseline_bias": baseline["bias"],
                    "delta_rmse": metrics["rmse"] - baseline["rmse"],
                    "rmse_gain": baseline["rmse"] - metrics["rmse"],
                    "delta_nse": metrics["nse"] - baseline["nse"],
                    "delta_abs_bias": abs(metrics["bias"]) - abs(baseline["bias"]),
                }
            )
            metrics_rows.append(out_row)
            fit_rows.append(
                {
                    **metric_prefix,
                    "selected_points": ";".join(map(str, selected_points)),
                    "fit_metadata": json.dumps(calibrator.metadata, sort_keys=True),
                }
            )

            for season, group in test.assign(pred_calibrated=pred).groupby("season", observed=True):
                s_metrics = metric_row(group["obs_sm_pct"], group["pred_calibrated"].to_numpy(dtype=float))
                season_rows.append({**metric_prefix, "season": str(season), **s_metrics})

    return metrics_rows, season_rows, fit_rows


def summarize_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    group_cols = [
        "site",
        "block",
        "selection_strategy",
        "budget_label",
        "calibration_points",
        "base_model",
        "model_track",
        "method",
    ]
    value_cols = ["n", "nse", "pearson_r", "rmse", "ubrmse", "bias", "mae", "delta_rmse", "rmse_gain", "delta_nse", "delta_abs_bias"]

    def qfun(pct: float):
        def _inner(x):
            vals = pd.to_numeric(x, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            return np.nan if vals.empty else float(np.nanpercentile(vals, pct))

        return _inner

    agg = {}
    for col in value_cols:
        if col in metrics.columns:
            agg[f"{col}_median"] = (col, "median")
            agg[f"{col}_q25"] = (col, qfun(25))
            agg[f"{col}_q75"] = (col, qfun(75))
    out = metrics.groupby(group_cols, as_index=False, observed=True).agg(**agg)
    out["n_replicates"] = metrics.groupby(group_cols, observed=True)["replicate"].nunique().to_numpy()
    return out


def process_vs_statistical(metrics: pd.DataFrame) -> pd.DataFrame:
    sub = metrics[metrics["method"] != "global"].copy()
    keys = ["site", "block", "selection_strategy", "budget_label", "calibration_points", "replicate", "method"]
    stat = sub[sub["base_model"] == "model6_rf"]
    proc = sub[sub["base_model"] == "model8_process"]
    merged = stat.merge(proc, on=keys, suffixes=("_statistical", "_process"), how="inner")
    if merged.empty:
        return pd.DataFrame()
    rows = pd.DataFrame(
        {
            **{k: merged[k] for k in keys},
            "statistical_rmse_gain": merged["rmse_gain_statistical"],
            "process_rmse_gain": merged["rmse_gain_process"],
            "process_minus_statistical_rmse_gain": merged["rmse_gain_process"] - merged["rmse_gain_statistical"],
            "statistical_delta_nse": merged["delta_nse_statistical"],
            "process_delta_nse": merged["delta_nse_process"],
            "process_minus_statistical_delta_nse": merged["delta_nse_process"] - merged["delta_nse_statistical"],
            "statistical_calibrated_rmse": merged["rmse_statistical"],
            "process_calibrated_rmse": merged["rmse_process"],
            "post_calibration_winner": np.where(
                merged["rmse_process"] < merged["rmse_statistical"], "process_model8", "statistical_model6"
            ),
        }
    )
    group_cols = ["site", "block", "selection_strategy", "budget_label", "calibration_points", "method"]
    return (
        rows.groupby(group_cols, as_index=False, observed=True)
        .agg(
            statistical_rmse_gain_median=("statistical_rmse_gain", "median"),
            process_rmse_gain_median=("process_rmse_gain", "median"),
            process_minus_statistical_rmse_gain_median=("process_minus_statistical_rmse_gain", "median"),
            statistical_delta_nse_median=("statistical_delta_nse", "median"),
            process_delta_nse_median=("process_delta_nse", "median"),
            process_minus_statistical_delta_nse_median=("process_minus_statistical_delta_nse", "median"),
            statistical_calibrated_rmse_median=("statistical_calibrated_rmse", "median"),
            process_calibrated_rmse_median=("process_calibrated_rmse", "median"),
            fraction_process_wins=("post_calibration_winner", lambda x: float((x == "process_model8").mean())),
            n_replicates=("process_rmse_gain", "size"),
        )
    )


def baseline_metrics(site_frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for site, df in site_frames.items():
        for base_model, group in df.groupby("base_model", observed=True):
            row = {
                "site": site,
                "base_model": base_model,
                "model_track": MODEL_TRACK.get(base_model, base_model),
                **soil_moisture_metrics(group["obs_sm_pct"], group["pred_sm_pct"]),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def best_prior_guided_designs(summary: pd.DataFrame) -> pd.DataFrame:
    """Best deployable non-random/non-proxy design by site/model/budget.

    This mirrors the Table 5 logic in the manuscript: use the strict
    spatio-temporal block, exclude random placement and the observed wet/dry
    proxy, then select the strategy/method combination with the highest median
    held-out NSE for each site/model/local information budget.
    """

    core = summary[
        (summary["block"] == "spatiotemporal_block")
        & (summary["selection_strategy"].isin(DEPLOYABLE_PRIOR_STRATEGIES))
        & (summary["method"] != "global")
    ].copy()
    if core.empty:
        return core
    site_order = {site: i for i, site in enumerate(ordered_sites(core["site"]))}
    core["site_order"] = core["site"].map(site_order).fillna(len(site_order)).astype(int)
    return (
        core.sort_values(
            ["site_order", "base_model", "calibration_points", "nse_median", "rmse_gain_median"],
            ascending=[True, True, True, False, False],
        )
        .groupby(["site", "base_model", "budget_label", "calibration_points"], as_index=False, observed=True)
        .first()
        .sort_values(["site_order", "base_model", "calibration_points"])
        .drop(columns=["site_order"], errors="ignore")
    )


def best_prior_guided_responsiveness(responsiveness: pd.DataFrame) -> pd.DataFrame:
    """Best paired prior-guided response by site/strategy/budget.

    The paired process-vs-statistical table already compares model6 and model8
    for the same strategy, budget, replicate and calibration method.  For a
    compact figure we keep, within each non-random prior and budget, the
    calibration method with the strongest average RMSE gain across both models.
    """

    resp = responsiveness[
        (responsiveness["block"] == "spatiotemporal_block")
        & (responsiveness["selection_strategy"].isin(DEPLOYABLE_PRIOR_STRATEGIES))
    ].copy()
    if resp.empty:
        return resp
    resp["mean_model_rmse_gain"] = (
        resp["statistical_rmse_gain_median"] + resp["process_rmse_gain_median"]
    ) / 2.0
    site_order = {site: i for i, site in enumerate(ordered_sites(resp["site"]))}
    resp["site_order"] = resp["site"].map(site_order).fillna(len(site_order)).astype(int)
    return (
        resp.sort_values(
            ["site_order", "selection_strategy", "calibration_points", "mean_model_rmse_gain"],
            ascending=[True, True, True, False],
        )
        .groupby(["site", "selection_strategy", "budget_label", "calibration_points"], as_index=False, observed=True)
        .first()
        .sort_values(["site_order", "selection_strategy", "calibration_points"])
        .drop(columns=["site_order"], errors="ignore")
    )


def make_figures(outdir: Path, baseline: pd.DataFrame, summary: pd.DataFrame, responsiveness: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figdir = outdir / "figures"
    figdir.mkdir(parents=True, exist_ok=True)

    # Baseline skill by site/model.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
    sites = ordered_sites(baseline["site"])
    x = np.arange(len(sites))
    width = 0.36
    for offset, model in [(-width / 2, "model6_rf"), (width / 2, "model8_process")]:
        sub = baseline[baseline["base_model"] == model].set_index("site").reindex(sites)
        axes[0].bar(x + offset, sub["rmse"], width=width, label=model)
        axes[1].bar(x + offset, sub["nse"], width=width, label=model)
    for ax, ylab in zip(axes, ["RMSE (%)", "NSE"]):
        ax.set_xticks(x)
        ax.set_xticklabels(sites, rotation=20, ha="right")
        ax.set_ylabel(ylab)
        ax.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    fig.suptitle("Uncalibrated global model skill by validation site")
    fig.tight_layout()
    fig.savefig(figdir / "baseline_site_model_skill.png", dpi=180)
    plt.close(fig)

    # Main manuscript learning curves: deployable prior-guided placement.
    prior_best = best_prior_guided_designs(summary)
    if not prior_best.empty:
        model_colours = {"model6_rf": "#4C78A8", "model8_process": "#F58518"}
        for metric, ylabel, filename, title in [
            (
                "rmse_gain_median",
                "RMSE gain vs global (%)",
                "prior_guided_spatiotemporal_learning_curves_rmse_gain.png",
                "Strict spatial+temporal block: best non-random, non-proxy local calibration",
            ),
            (
                "nse_median",
                "Held-out NSE",
                "prior_guided_spatiotemporal_learning_curves_nse.png",
                "Strict spatial+temporal block: best non-random, non-proxy local calibration",
            ),
        ]:
            fig, axes = plt.subplots(len(sites), 1, figsize=(9.5, max(3.2 * len(sites), 5)), sharex=False)
            axes = np.atleast_1d(axes)
            for ax, site in zip(axes, sites):
                sub = prior_best[prior_best["site"] == site]
                for model, g in sub.groupby("base_model", observed=True):
                    g = g.sort_values("calibration_points")
                    ax.plot(
                        g["calibration_points"],
                        g[metric],
                        marker="o",
                        linewidth=1.8,
                        color=model_colours.get(model),
                        label=model,
                    )
                ax.axhline(0, color="0.3", linewidth=0.8)
                if metric == "nse_median":
                    ax.axhline(0.2, color="0.45", linewidth=0.8, linestyle="--")
                    ax.axhline(0.3, color="0.45", linewidth=0.8, linestyle=":")
                ax.set_title(site)
                ax.set_ylabel(ylabel)
                ax.grid(alpha=0.25)
            axes[-1].set_xlabel("Calibration points")
            axes[0].legend(fontsize=8)
            fig.suptitle(title)
            fig.tight_layout()
            fig.savefig(figdir / filename, dpi=180)
            plt.close(fig)

    # Main manuscript process-vs-statistical response under deployable priors.
    prior_resp = best_prior_guided_responsiveness(responsiveness)
    if not prior_resp.empty:
        strategy_colours = {
            "landscape_wetdry_prior": "#54A24B",
            "global_prediction_extremes": "#B279A2",
        }
        fig, axes = plt.subplots(len(sites), 1, figsize=(9.5, max(3.0 * len(sites), 5)), sharex=False)
        axes = np.atleast_1d(axes)
        for ax, site in zip(axes, sites):
            sub = prior_resp[prior_resp["site"] == site]
            for strategy, g in sub.groupby("selection_strategy", observed=True):
                g = g.sort_values("calibration_points")
                ax.plot(
                    g["calibration_points"],
                    g["process_minus_statistical_rmse_gain_median"],
                    marker="o",
                    linewidth=1.8,
                    color=strategy_colours.get(strategy),
                    label=strategy.replace("_", " "),
                )
            ax.axhline(0, color="0.3", linewidth=0.8)
            ax.set_title(site)
            ax.set_ylabel("model8 gain -\nmodel6 gain (%)")
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Calibration points")
        axes[0].legend(fontsize=8)
        fig.suptitle("Does the process model respond more under prior-guided placement?")
        fig.tight_layout()
        fig.savefig(figdir / "prior_guided_process_vs_statistical_responsiveness.png", dpi=180)
        plt.close(fig)

    # Random strict-block learning curves.
    core = summary[
        (summary["selection_strategy"] == "random")
        & (summary["block"] == "spatiotemporal_block")
        & (summary["method"] != "global")
    ].copy()
    if not core.empty:
        fig, axes = plt.subplots(len(sites), 1, figsize=(9.5, max(3.2 * len(sites), 5)), sharex=False)
        axes = np.atleast_1d(axes)
        for ax, site in zip(axes, sites):
            sub = core[core["site"] == site]
            for (model, method), g in sub.groupby(["base_model", "method"], observed=True):
                g = g.sort_values("calibration_points")
                ax.plot(g["calibration_points"], g["rmse_gain_median"], marker="o", label=f"{model} {method}")
            ax.axhline(0, color="0.3", linewidth=0.8)
            ax.set_title(site)
            ax.set_ylabel("RMSE gain vs global (%)")
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Calibration points")
        axes[0].legend(ncol=2, fontsize=7)
        fig.suptitle("Strict spatio-temporal transfer: random sparse sensors")
        fig.tight_layout()
        fig.savefig(figdir / "random_spatiotemporal_learning_curves_rmse_gain.png", dpi=180)
        plt.close(fig)

        fig, axes = plt.subplots(len(sites), 1, figsize=(9.5, max(3.2 * len(sites), 5)), sharex=False)
        axes = np.atleast_1d(axes)
        for ax, site in zip(axes, sites):
            sub = core[core["site"] == site]
            for (model, method), g in sub.groupby(["base_model", "method"], observed=True):
                g = g.sort_values("calibration_points")
                ax.plot(g["calibration_points"], g["nse_median"], marker="o", label=f"{model} {method}")
            ax.axhline(0, color="0.3", linewidth=0.8)
            ax.axhline(0.2, color="0.45", linewidth=0.8, linestyle="--")
            ax.axhline(0.3, color="0.45", linewidth=0.8, linestyle=":")
            ax.set_title(site)
            ax.set_ylabel("Held-out NSE")
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Calibration points")
        axes[0].legend(ncol=2, fontsize=7)
        fig.suptitle("Strict spatio-temporal transfer: random sparse sensors, NSE")
        fig.tight_layout()
        fig.savefig(figdir / "random_spatiotemporal_learning_curves_nse.png", dpi=180)
        plt.close(fig)

    # Process-vs-statistical responsiveness.
    resp = responsiveness[
        (responsiveness["selection_strategy"] == "random")
        & (responsiveness["block"] == "spatiotemporal_block")
    ].copy()
    if not resp.empty:
        fig, axes = plt.subplots(len(sites), 1, figsize=(9.5, max(3.0 * len(sites), 5)), sharex=False)
        axes = np.atleast_1d(axes)
        for ax, site in zip(axes, sites):
            sub = resp[resp["site"] == site]
            for method, g in sub.groupby("method", observed=True):
                g = g.sort_values("calibration_points")
                ax.plot(
                    g["calibration_points"],
                    g["process_minus_statistical_rmse_gain_median"],
                    marker="o",
                    label=method,
                )
            ax.axhline(0, color="0.3", linewidth=0.8)
            ax.set_title(site)
            ax.set_ylabel("model8 gain -\nmodel6 gain (%)")
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Calibration points")
        axes[0].legend(fontsize=8)
        fig.suptitle("Does the process model respond more to sparse local calibration?")
        fig.tight_layout()
        fig.savefig(figdir / "process_vs_statistical_responsiveness_random.png", dpi=180)
        plt.close(fig)


def copy_report_figures(outdir: Path, report_figdir: Path) -> None:
    """Copy generated figures from ignored outputs/ into the tracked reports tree."""
    report_figdir.mkdir(parents=True, exist_ok=True)
    source_figdir = outdir / "figures"
    for filename, _, _ in REPORT_FIGURES:
        src = source_figdir / filename
        if src.exists():
            shutil.copy2(src, report_figdir / filename)


def render_report_figures(report_path: Path, report_figdir: Path) -> str:
    blocks = []
    for index, (filename, title, caption) in enumerate(REPORT_FIGURES, start=1):
        rel_path = os.path.relpath(report_figdir / filename, start=report_path.parent)
        rel_path = Path(rel_path).as_posix()
        blocks.append(
            "\n".join(
                [
                    f"### Figure {index}. {title}",
                    "",
                    f"![{title}]({rel_path})",
                    "",
                    caption,
                ]
            )
        )
    return "\n\n".join(blocks)


def report_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Return a report-facing table with only explicitly approved columns."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    return df[[c for c in cols if c in df.columns]].copy()


def write_report(
    out_path: Path,
    outdir: Path,
    report_figdir: Path,
    site_summaries: pd.DataFrame,
    baseline: pd.DataFrame,
    summary: pd.DataFrame,
    responsiveness: pd.DataFrame,
) -> None:
    random_learning = summary[
        (summary["block"] == "spatiotemporal_block")
        & (summary["selection_strategy"] == "random")
        & (summary["method"] != "global")
    ][
        [
            "site",
            "budget_label",
            "calibration_points",
            "base_model",
            "method",
            "nse_median",
            "pearson_r_median",
            "rmse_median",
            "ubrmse_median",
            "bias_median",
            "n_replicates",
        ]
    ]
    prior_guided_learning = best_prior_guided_designs(summary)[
        [
            "site",
            "budget_label",
            "calibration_points",
            "base_model",
            "selection_strategy",
            "method",
            "nse_median",
            "pearson_r_median",
            "rmse_median",
            "ubrmse_median",
            "bias_median",
            "rmse_gain_median",
            "delta_nse_median",
            "n_replicates",
        ]
    ]
    resp_core = responsiveness[
        (responsiveness["block"] == "spatiotemporal_block")
        & (responsiveness["selection_strategy"] == "random")
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

    baseline_report = report_columns(
        baseline,
        ["site", "base_model", "model_track", "n", "nse", "pearson_r", "rmse", "ubrmse", "bias"],
    )

    tarrawarra_note = (
        "Tarrawarra observations are aggregated to the model prediction grid cell "
        "by date before validation, because the raw campaign points are much closer "
        "than the raster support. Tarrawarra model6 should also be read with a "
        "special caveat: the historical SMIPS inputs in the existing Tarrawarra run "
        "are zero, so model6 there is closer to a missing-coarse-anchor ablation "
        "than a normal model6 run."
    )
    figures_md = render_report_figures(out_path, report_figdir)
    site_names = ordered_sites(site_summaries["site"]) if "site" in site_summaries.columns else []
    site_list = ", ".join(site_names) if site_names else "the retained validation sites"
    site_count_phrase = f"{len(site_names)}-site" if site_names else "multi-site"

    body = f"""# Stage 2 local-spiking calibration: {site_count_phrase} validation set

Sites included in this run: {site_list}.

The practical question is: if a landowner can afford a small cluster of
soil-moisture sensors, can that local information budget improve property-scale
downscaling enough to matter? The experiment deliberately assumes that a new
site starts with **no measured soil moisture map**. Sensor locations are
therefore chosen using:

- random point selection;
- a terrain/model-input wet-dry landscape prior;
- global prediction extremes;
- an explicitly labelled `field_knowledge_wetdry_proxy`, which uses observed
  chronic wet/dry points as a proxy for landowner knowledge and should not be
  treated as a fully deployable selection rule.

## Blocking design

Each site is tested under three blocks:

1. `spatial_block`: fit selected calibration points across all available dense
   dates, validate unselected points.
2. `temporal_block`: fit selected calibration points in the early dense dates,
   validate those same points in later dates.
3. `spatiotemporal_block`: fit selected calibration points in early dates,
   validate different points in later dates. This is the strictest and most
   relevant property-map transfer test.

Calibration methods:

- `bias_offset`: one local residual offset;
- `seasonal_offset`: separate residual offsets by southern-hemisphere season,
  falling back to the global offset where a season is unseen in calibration;
- `affine`: local intercept and slope correction;
- `residual_ridge`: strongly regularised residual layer using only
  prediction-time model inputs and terrain/soil/weather state.

## Site inputs

{markdown_table(site_summaries)}

{tarrawarra_note}

Nerrigundah uses the same grid-cell support logic as Tarrawarra. MRI is a
sparser continuous probe network, so its Stage 2 curves test local temporal
transfer at fewer fixed supports rather than dense campaign spatial structure.

## Uncalibrated global model skill

{markdown_table(baseline_report)}

## Headline inference

- Under the strict prior-guided, non-proxy placement test, the report now
  compares all retained validation sites with model-ready support/date tables.
  The cleanest manuscript reading should focus on whether calibration improves
  held-out RMSE and NSE within each site, then compare process-vs-statistical
  responsiveness as a secondary diagnostic.
- Tarrawarra is different: both models improve strongly with sparse local
  calibration, but model6 often shows larger RMSE gains because its uncalibrated
  bias is very large. However, model8 generally remains the lower-RMSE model
  after calibration. Interpret this alongside the Tarrawarra SMIPS-zero caveat.
- Nerrigundah and MRI should be treated as support-type sensitivity checks:
  Nerrigundah is a Tarrawarra-like campaign grid, while MRI is a sparse
  continuously monitored probe network.
- Random placement is retained as an appendix comparator. It is not consistently
  enough under the strict block, which supports the practical idea of using
  defensible landscape knowledge rather than arbitrary sensor placement.
- The `field_knowledge_wetdry_proxy` can outperform deployable priors in some
  cases, but it is an upper-bound proxy, not a blind deployment rule.
- The residual-ridge layer is useful in selected cases, but simple
  `bias_offset` is often the most robust sparse-sensor calibration layer. This
  matters for deployability: a landowner-facing calibration should probably
  start with a small, interpretable correction before adding flexible residual
  models.

## Prior-guided sparse-sensor learning curves

This table mirrors the main manuscript learning-curve figures and
Table 5-style minimum-budget summary. It keeps only deployable non-random,
non-proxy placement strategies: `landscape_wetdry_prior` and
`global_prediction_extremes`.

{markdown_table(prior_guided_learning, max_rows=60)}

## Appendix comparator: random sparse-sensor learning curves

Random placement is retained as a conservative comparator because it does not
assume any landscape knowledge. The report table shows calibrated held-out NSE,
Pearson r, RMSE, ubRMSE and bias; improvement bookkeeping is retained in the
CSV outputs.

{markdown_table(random_learning, max_rows=60)}

## Process-vs-statistical calibration responsiveness

Positive `process_minus_statistical_rmse_gain_median` means model8 process
benefited more from the same sparse local calibration than model6 RF. Negative
values mean model6 RF benefited more.

{markdown_table(resp_core, max_rows=60)}

## Figures

{figures_md}

## Interpretation guardrails

- Local calibration is not independent validation. It is a separate
  intervention/sensor-placement experiment layered after unseen-site
  validation.
- The `spatiotemporal_block` results are the most defensible for property-scale
  transfer because calibration and validation are separated in both space and
  time.
- The field-knowledge proxy is useful for thinking with landowners, but it is
  not a strict blind selection rule because the proxy is generated from observed
  chronic wet/dry behaviour.
- A calibration layer that improves RMSE by destroying seasonal behaviour should
  not be treated as a win. Seasonal metrics are written to
  `metrics_by_design_season.csv` for that reason.
- The process-vs-statistical question should be read as **responsiveness to a
  sparse local information budget**, not as a universal ranking of model types.
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    budget_specs = parse_budget_specs(args.budgets)
    rng = np.random.default_rng(args.seed)

    site_frames: dict[str, pd.DataFrame] = {}
    site_summary_rows = []
    point_summary_frames = []
    selected_rows = []
    metrics_rows: list[dict] = []
    season_rows: list[dict] = []
    fit_rows: list[dict] = []

    for site, path in SITE_PATHS.items():
        print(f"loading {site}: {path}", flush=True)
        df = load_site(site, path)
        site_frames[site] = df
        dates = sorted(df["date"].unique())
        train_dates, future_dates = split_dates(dates, args.train_date_fraction, args.min_train_dates)
        point_summary = site_point_summary(df, train_dates, future_dates)
        point_summary["site"] = site
        point_summary_frames.append(point_summary)
        site_summary_rows.append(
            {
                "site": site,
                "path": str(path),
                "rows": int(len(df)),
                "models": ",".join(sorted(df["base_model"].unique())),
                "points": int(df["point_id"].nunique()),
                "eligible_points_train_and_future": int(point_summary["eligible"].sum()),
                "dates": int(len(dates)),
                "date_min": min(dates),
                "date_max": max(dates),
                "train_dates": int(len(train_dates)),
                "future_dates": int(len(future_dates)),
                "seasons": ",".join(sorted(map(str, df["season"].dropna().unique()))),
            }
        )

        n_eligible = int(point_summary["eligible"].sum())
        resolved_budgets: list[tuple[str, int]] = []
        seen_budgets: set[int] = set()
        for spec in budget_specs:
            budget_label, budget = resolve_budget(spec, n_eligible)
            if budget <= 0:
                continue
            if budget not in seen_budgets:
                resolved_budgets.append((budget_label, budget))
                seen_budgets.add(budget)

        for budget_label, budget in resolved_budgets:
            for strategy in SELECTION_STRATEGIES:
                reps = args.random_reps if strategy == "random" and budget < n_eligible else 1
                for rep in range(reps):
                    selected = select_points(point_summary, strategy, budget, rng)
                    if not selected:
                        continue
                    selected_rows.append(
                        {
                            "site": site,
                            "selection_strategy": strategy,
                            "budget_label": budget_label,
                            "calibration_points": budget,
                            "replicate": rep,
                            "selected_points": ";".join(selected),
                        }
                    )
                    for block in BLOCKS:
                        m_rows, s_rows, f_rows = evaluate_design(
                            df,
                            site,
                            selected,
                            train_dates,
                            future_dates,
                            block,
                            strategy,
                            budget_label,
                            budget,
                            rep,
                        )
                        metrics_rows.extend(m_rows)
                        season_rows.extend(s_rows)
                        fit_rows.extend(f_rows)

    site_summaries = pd.DataFrame(site_summary_rows)
    point_summaries = pd.concat(point_summary_frames, ignore_index=True)
    selected_points = pd.DataFrame(selected_rows)
    metrics = pd.DataFrame(metrics_rows)
    season_metrics = pd.DataFrame(season_rows)
    fit_metadata = pd.DataFrame(fit_rows)
    baseline = baseline_metrics(site_frames)
    summary = summarize_metrics(metrics)
    responsiveness = process_vs_statistical(metrics)

    site_summaries.to_csv(outdir / "site_summaries.csv", index=False)
    point_summaries.to_csv(outdir / "point_selection_summaries.csv", index=False)
    selected_points.to_csv(outdir / "selected_calibration_points.csv", index=False)
    metrics.to_csv(outdir / "metrics_by_design.csv", index=False)
    season_metrics.to_csv(outdir / "metrics_by_design_season.csv", index=False)
    fit_metadata.to_csv(outdir / "calibration_fit_metadata.csv", index=False)
    baseline.to_csv(outdir / "global_baseline_metrics_by_site.csv", index=False)
    summary.to_csv(outdir / "local_calibration_summary.csv", index=False)
    responsiveness.to_csv(outdir / "process_vs_statistical_responsiveness.csv", index=False)

    make_figures(outdir, baseline, summary, responsiveness)
    copy_report_figures(outdir, args.report_figdir)
    write_report(args.report, outdir, args.report_figdir, site_summaries, baseline, summary, responsiveness)
    run_summary = {
        "outdir": str(outdir),
        "report": str(args.report),
        "report_figdir": str(args.report_figdir),
        "budget_specs": budget_specs,
        "random_reps": args.random_reps,
        "seed": args.seed,
        "blocks": BLOCKS,
        "methods": METHODS,
        "selection_strategies": SELECTION_STRATEGIES,
    }
    (outdir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print(f"wrote outputs: {outdir}", flush=True)
    print(f"wrote report: {args.report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
