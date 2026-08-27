#!/usr/bin/env python3
"""Temporal-blocked local calibration CV for dense validation sites.

This experiment answers a narrower deployment question than the strict
spatial+temporal local-spiking experiment:

    If local soil-moisture points/sensors are installed at a few locations,
    and a calibration layer is fitted from measurements at those locations
    during some dates, does that calibration improve predictions for unseen
    dates at the same locations?

The validation geometry is therefore temporal-only:

- unique sampling dates are sorted chronologically;
- contiguous temporal blocks are used as folds;
- calibration is fitted on selected local points in the other folds;
- validation is performed on the same selected points in the held-out fold.

This is deliberately not an independent dense-site validation score.  It is a
local adaptation/sensor-budget diagnostic.
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

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/dmm_validation_matplotlib")


DMM_VALIDATION_ROOT = Path(__file__).resolve().parents[3]
SRC = DMM_VALIDATION_ROOT / "src"
LOCAL_CALIBRATION_DIR = DMM_VALIDATION_ROOT / "scripts" / "analyses" / "local_calibration"
for path in (SRC, LOCAL_CALIBRATION_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dmm_validation.reporting import markdown_table  # noqa: E402

import run_local_spiking_experiment as spiking  # noqa: E402


DEFAULT_OUTDIR = (
    DMM_VALIDATION_ROOT
    / "outputs"
    / "unified_dense_validation"
    / "stage2_temporal_blocked_cv"
)
DEFAULT_REPORT = (
    DMM_VALIDATION_ROOT
    / "reports"
    / "analyses"
    / "unified_dense_validation"
    / "stage2_temporal_blocked_cv_report.md"
)
DEFAULT_REPORT_FIGDIR = (
    DMM_VALIDATION_ROOT
    / "reports"
    / "analyses"
    / "unified_dense_validation"
    / "figures"
    / "stage2_temporal_blocked_cv"
)

CALIBRATION_METHODS = ["bias_offset", "seasonal_offset", "affine", "residual_ridge"]
METHODS = ["global", *CALIBRATION_METHODS]
SELECTION_STRATEGIES = [
    "random",
    "landscape_wetdry_prior",
    "global_prediction_extremes",
    "field_knowledge_wetdry_proxy",
]
FIGURES = [
    (
        "temporal_cv_random_same_points_rmse_gain.png",
        "Random point-budget temporal CV: RMSE gain",
        "Median pooled 10-fold temporal-CV RMSE gain as local point budgets increase. Positive values mean the local calibration improved RMSE relative to the uncalibrated model on the same held-out dates/supports.",
    ),
    (
        "temporal_cv_random_same_points_delta_nse.png",
        "Random point-budget temporal CV: NSE gain",
        "Median pooled 10-fold temporal-CV change in NSE as local point budgets increase. Positive values mean the local calibration improved temporal skill relative to the uncalibrated model on the same held-out dates/supports.",
    ),
    (
        "temporal_cv_best_strategy_delta_nse.png",
        "Best temporal-CV NSE gain by selection strategy",
        "Best median NSE gain across calibration methods for each point-selection strategy and budget.",
    ),
    (
        "temporal_cv_best_strategy_rmse_gain.png",
        "Best temporal-CV RMSE gain by selection strategy",
        "Best median RMSE gain across calibration methods for each point-selection strategy and budget.",
    ),
]


@dataclass
class MetricAccumulator:
    n: int = 0
    sum_obs: float = 0.0
    sum_pred: float = 0.0
    sum_obs2: float = 0.0
    sum_pred2: float = 0.0
    sum_obspred: float = 0.0
    sum_err: float = 0.0
    sum_err2: float = 0.0

    def update(self, obs_values, pred_values) -> None:
        obs = np.asarray(obs_values, dtype=float)
        pred = np.asarray(pred_values, dtype=float)
        ok = np.isfinite(obs) & np.isfinite(pred)
        if not ok.any():
            return
        obs = obs[ok]
        pred = pred[ok]
        err = pred - obs
        self.n += int(obs.size)
        self.sum_obs += float(obs.sum())
        self.sum_pred += float(pred.sum())
        self.sum_obs2 += float(np.square(obs).sum())
        self.sum_pred2 += float(np.square(pred).sum())
        self.sum_obspred += float((obs * pred).sum())
        self.sum_err += float(err.sum())
        self.sum_err2 += float(np.square(err).sum())

    def finalise(self) -> dict[str, float]:
        if self.n < 2:
            return {
                "n": self.n,
                "nse": np.nan,
                "pearson_r": np.nan,
                "rmse": np.nan,
                "ubrmse": np.nan,
                "bias": np.nan,
            }

        n = float(self.n)
        bias = self.sum_err / n
        rmse = math.sqrt(self.sum_err2 / n)
        ubrmse = math.sqrt(max(rmse**2 - bias**2, 0.0))

        ss_tot = self.sum_obs2 - (self.sum_obs**2 / n)
        nse = 1.0 - self.sum_err2 / ss_tot if ss_tot > 0 else np.nan

        var_obs = self.sum_obs2 - (self.sum_obs**2 / n)
        var_pred = self.sum_pred2 - (self.sum_pred**2 / n)
        cov = self.sum_obspred - (self.sum_obs * self.sum_pred / n)
        pearson = cov / math.sqrt(var_obs * var_pred) if var_obs > 0 and var_pred > 0 else np.nan

        return {
            "n": self.n,
            "nse": float(nse),
            "pearson_r": float(pearson),
            "rmse": float(rmse),
            "ubrmse": float(ubrmse),
            "bias": float(bias),
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--report-figdir", type=Path, default=DEFAULT_REPORT_FIGDIR)
    parser.add_argument("--folds", type=int, default=10)
    parser.add_argument(
        "--budgets",
        default="3,5,10,25%,50%,all",
        help="Comma-separated local point budgets. Supports integers, percentages and all.",
    )
    parser.add_argument("--random-reps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def make_temporal_folds(dates: list[str], requested_folds: int) -> list[dict]:
    sorted_dates = sorted(pd.to_datetime(pd.Series(dates)).dt.date.astype(str).unique())
    if len(sorted_dates) < 2:
        return []
    n_folds = max(2, min(int(requested_folds), len(sorted_dates)))
    date_arrays = np.array_split(np.asarray(sorted_dates, dtype=object), n_folds)
    folds: list[dict] = []
    all_dates = set(sorted_dates)
    for fold_id, heldout in enumerate(date_arrays, start=1):
        test_dates = set(map(str, heldout.tolist()))
        train_dates = all_dates - test_dates
        folds.append(
            {
                "fold": fold_id,
                "n_folds": n_folds,
                "train_dates": train_dates,
                "test_dates": test_dates,
                "test_date_min": min(test_dates),
                "test_date_max": max(test_dates),
                "n_train_dates": len(train_dates),
                "n_test_dates": len(test_dates),
            }
        )
    return folds


def point_summary_for_fold(df: pd.DataFrame, train_dates: set[str], test_dates: set[str]) -> pd.DataFrame:
    """Fold-aware point summary.

    Observed chronic wet/dry scores are computed from calibration dates only,
    so the `field_knowledge_wetdry_proxy` does not look into the held-out
    temporal fold.
    """

    base_model = "model6_rf" if "model6_rf" in set(df["base_model"]) else sorted(df["base_model"].unique())[0]
    one = df[df["base_model"] == base_model].copy()
    train = one[one["date"].isin(train_dates)].copy()
    test = one[one["date"].isin(test_dates)].copy()

    numeric_cols = [
        c
        for c in spiking.WETNESS_FEATURE_WEIGHTS
        if c in train.columns and pd.api.types.is_numeric_dtype(train[c])
    ]
    if train.empty:
        return pd.DataFrame(columns=["point_id", "eligible"])

    agg_spec = {
        "lon": ("lon", "mean"),
        "lat": ("lat", "mean"),
        "obs_mean": ("obs_sm_pct", "mean"),
        "obs_sd": ("obs_sm_pct", "std"),
        "global_pred_mean": ("pred_sm_pct", "mean"),
        "global_pred_sd": ("pred_sm_pct", "std"),
        "n_train_rows": ("date", "size"),
        "n_train_dates": ("date", lambda x: pd.Series(x).nunique()),
    }
    for col in numeric_cols:
        agg_spec[col] = (col, "mean")
    out = train.groupby("point_id", as_index=False).agg(**agg_spec)
    test_dates_by_point = test.groupby("point_id")["date"].agg(lambda x: set(x))
    train_dates_by_point = train.groupby("point_id")["date"].agg(lambda x: set(x))
    out["has_train_dates"] = out["point_id"].map(lambda p: p in train_dates_by_point.index and bool(train_dates_by_point.loc[p]))
    out["has_test_dates"] = out["point_id"].map(lambda p: p in test_dates_by_point.index and bool(test_dates_by_point.loc[p]))
    out["n_test_dates"] = out["point_id"].map(
        lambda p: len(test_dates_by_point.loc[p]) if p in test_dates_by_point.index else 0
    )
    out["eligible"] = out["has_train_dates"] & out["has_test_dates"]

    wetness = pd.Series(0.0, index=out.index)
    used = []
    for col, weight in spiking.WETNESS_FEATURE_WEIGHTS.items():
        if col in out.columns:
            wetness = wetness + weight * spiking.zscore(out[col])
            used.append(col)
    out["landscape_wetness_score"] = wetness
    out["landscape_wetness_features"] = ",".join(used)
    out["global_prediction_score"] = out["global_pred_mean"]
    out["field_knowledge_proxy_score"] = out["obs_mean"]
    return out


def key_without_method(row: dict) -> tuple:
    return (
        row["site"],
        row["base_model"],
        row["selection_strategy"],
        row["budget_label"],
        row["calibration_points"],
        row["replicate"],
    )


def evaluate_cv_design(
    site: str,
    df: pd.DataFrame,
    folds: list[dict],
    strategy: str,
    budget_label: str,
    budget: int,
    replicate: int,
    rng: np.random.Generator,
    accumulator: dict[tuple, MetricAccumulator],
    selected_rows: list[dict],
    fold_rows: list[dict],
    fit_rows: list[dict],
) -> None:
    for fold in folds:
        train_dates = fold["train_dates"]
        test_dates = fold["test_dates"]
        point_summary = point_summary_for_fold(df, train_dates, test_dates)
        n_eligible = int(point_summary["eligible"].sum()) if not point_summary.empty else 0
        if n_eligible <= 0:
            continue
        actual_budget = min(budget, n_eligible)
        selected_points = spiking.select_points(point_summary, strategy, actual_budget, rng)
        if not selected_points:
            continue

        selected_rows.append(
            {
                "site": site,
                "fold": fold["fold"],
                "n_folds": fold["n_folds"],
                "selection_strategy": strategy,
                "budget_label": budget_label,
                "requested_calibration_points": budget,
                "actual_calibration_points": actual_budget,
                "replicate": replicate,
                "n_eligible_points": n_eligible,
                "selected_points": ";".join(map(str, selected_points)),
            }
        )

        for base_model, model_df in df.groupby("base_model", observed=True):
            selected = model_df["point_id"].isin(selected_points)
            train_mask = selected & model_df["date"].isin(train_dates)
            test_mask = selected & model_df["date"].isin(test_dates)
            train = model_df.loc[train_mask].copy()
            test = model_df.loc[test_mask].copy()
            # Fold-level test sets can legitimately contain one row when the
            # local point budget is tiny and the held-out temporal block has a
            # single date.  NSE/RMSE are calculated after pooling predictions
            # across all temporal folds, so keep these one-row fold
            # contributions.
            if len(train) < 1 or len(test) < 1:
                continue

            common = {
                "site": site,
                "base_model": base_model,
                "model_track": spiking.MODEL_TRACK.get(base_model, base_model),
                "selection_strategy": strategy,
                "budget_label": budget_label,
                # Keep the requested/nominal budget in the design key so
                # temporally pooled metrics are not fragmented when a fold has
                # fewer eligible supports than another fold.  The realised
                # fold-level count is still recorded as n_selected_points.
                "calibration_points": budget,
                "replicate": replicate,
            }

            fold_base = {
                **common,
                "fold": fold["fold"],
                "n_folds": fold["n_folds"],
                "n_train_dates": fold["n_train_dates"],
                "n_test_dates": fold["n_test_dates"],
                "test_date_min": fold["test_date_min"],
                "test_date_max": fold["test_date_max"],
                "n_train_rows": int(len(train)),
                "n_test_rows": int(len(test)),
                "n_selected_points": int(len(selected_points)),
            }

            global_key = (*key_without_method(common), "global")
            accumulator.setdefault(global_key, MetricAccumulator()).update(
                test["obs_sm_pct"], test["pred_sm_pct"]
            )
            fold_rows.append({**fold_base, "method": "global"})

            for method in CALIBRATION_METHODS:
                calibrator = spiking.fit_calibrator(train, method)
                pred = calibrator.predict(test)
                method_key = (*key_without_method(common), method)
                accumulator.setdefault(method_key, MetricAccumulator()).update(test["obs_sm_pct"], pred)
                fold_rows.append({**fold_base, "method": method})
                fit_rows.append(
                    {
                        **fold_base,
                        "method": method,
                        "fit_metadata": json.dumps(calibrator.metadata, sort_keys=True),
                    }
                )


def build_metrics(accumulator: dict[tuple, MetricAccumulator]) -> pd.DataFrame:
    rows = []
    for key, acc in accumulator.items():
        (
            site,
            base_model,
            selection_strategy,
            budget_label,
            calibration_points,
            replicate,
            method,
        ) = key
        rows.append(
            {
                "site": site,
                "base_model": base_model,
                "model_track": spiking.MODEL_TRACK.get(base_model, base_model),
                "selection_strategy": selection_strategy,
                "budget_label": budget_label,
                "calibration_points": calibration_points,
                "replicate": replicate,
                "method": method,
                **acc.finalise(),
            }
        )
    metrics = pd.DataFrame(rows)
    if metrics.empty:
        return metrics

    base_keys = [
        "site",
        "base_model",
        "selection_strategy",
        "budget_label",
        "calibration_points",
        "replicate",
    ]
    baseline = metrics[metrics["method"] == "global"][base_keys + ["rmse", "nse", "bias"]].rename(
        columns={"rmse": "baseline_rmse", "nse": "baseline_nse", "bias": "baseline_bias"}
    )
    metrics = metrics.merge(baseline, on=base_keys, how="left")
    metrics["rmse_gain"] = metrics["baseline_rmse"] - metrics["rmse"]
    metrics["delta_rmse"] = metrics["rmse"] - metrics["baseline_rmse"]
    metrics["delta_nse"] = metrics["nse"] - metrics["baseline_nse"]
    metrics["delta_abs_bias"] = metrics["bias"].abs() - metrics["baseline_bias"].abs()
    metrics.loc[metrics["method"] == "global", ["rmse_gain", "delta_rmse", "delta_nse", "delta_abs_bias"]] = 0.0
    return metrics


def summarise_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    if metrics.empty:
        return metrics

    group_cols = [
        "site",
        "selection_strategy",
        "budget_label",
        "calibration_points",
        "base_model",
        "model_track",
        "method",
    ]
    value_cols = [
        "n",
        "nse",
        "pearson_r",
        "rmse",
        "ubrmse",
        "bias",
        "rmse_gain",
        "delta_nse",
        "delta_abs_bias",
    ]

    def qfun(pct: float):
        def _inner(x):
            vals = pd.to_numeric(x, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
            return np.nan if vals.empty else float(np.nanpercentile(vals, pct))

        return _inner

    agg = {}
    for col in value_cols:
        agg[f"{col}_median"] = (col, "median")
        agg[f"{col}_q25"] = (col, qfun(25))
        agg[f"{col}_q75"] = (col, qfun(75))
    out = metrics.groupby(group_cols, as_index=False, observed=True).agg(**agg)
    reps = metrics.groupby(group_cols, observed=True)["replicate"].nunique().reset_index(name="n_replicates")
    out = out.merge(reps, on=group_cols, how="left")
    return out.sort_values(["site", "base_model", "selection_strategy", "calibration_points", "method"])


def best_calibration_by_budget(summary: pd.DataFrame) -> pd.DataFrame:
    sub = summary[summary["method"] != "global"].copy()
    if sub.empty:
        return sub
    sort_cols = ["site", "base_model", "selection_strategy", "calibration_points", "rmse_gain_median", "delta_nse_median"]
    return (
        sub.sort_values(sort_cols, ascending=[True, True, True, True, False, False])
        .groupby(["site", "base_model", "selection_strategy", "budget_label", "calibration_points"], as_index=False, observed=True)
        .first()
        .sort_values(["site", "base_model", "selection_strategy", "calibration_points"])
    )


def make_figures(outdir: Path, summary: pd.DataFrame) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figdir = outdir / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    if summary.empty:
        return

    sites = list(summary["site"].drop_duplicates())
    random_core = summary[(summary["selection_strategy"] == "random") & (summary["method"] != "global")].copy()
    for metric, ylabel, filename, title in [
        (
            "rmse_gain_median",
            "RMSE gain vs global (%)",
            "temporal_cv_random_same_points_rmse_gain.png",
            "10-fold temporal CV, same selected points: random local point budgets",
        ),
        (
            "delta_nse_median",
            "NSE gain vs global",
            "temporal_cv_random_same_points_delta_nse.png",
            "10-fold temporal CV, same selected points: random local point budgets",
        ),
    ]:
        if random_core.empty:
            continue
        fig, axes = plt.subplots(len(sites), 1, figsize=(10, max(3.2 * len(sites), 5)), sharex=False)
        axes = np.atleast_1d(axes)
        for ax, site in zip(axes, sites):
            site_sub = random_core[random_core["site"] == site]
            for (model, method), g in site_sub.groupby(["base_model", "method"], observed=True):
                g = g.sort_values("calibration_points")
                ax.plot(g["calibration_points"], g[metric], marker="o", linewidth=1.6, label=f"{model} {method}")
            ax.axhline(0, color="0.25", linewidth=0.8)
            ax.set_title(site)
            ax.set_ylabel(ylabel)
            ax.grid(alpha=0.25)
        axes[-1].set_xlabel("Local calibration points")
        axes[0].legend(ncol=2, fontsize=7)
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(figdir / filename, dpi=180)
        plt.close(fig)

    best = best_calibration_by_budget(summary)
    for metric, ylabel, filename, title in [
        (
            "delta_nse_median",
            "Best NSE gain vs global",
            "temporal_cv_best_strategy_delta_nse.png",
            "Best temporal-CV NSE gain by selection strategy",
        ),
        (
            "rmse_gain_median",
            "Best RMSE gain vs global (%)",
            "temporal_cv_best_strategy_rmse_gain.png",
            "Best temporal-CV RMSE gain by selection strategy",
        ),
    ]:
        if best.empty:
            continue
        fig, axes = plt.subplots(len(sites), 2, figsize=(12, max(3.0 * len(sites), 5)), sharex=False, sharey=False)
        axes = np.asarray(axes).reshape(len(sites), 2)
        for i, site in enumerate(sites):
            for j, model in enumerate(["model6_rf", "model8_process"]):
                ax = axes[i, j]
                sub = best[(best["site"] == site) & (best["base_model"] == model)]
                for strategy, g in sub.groupby("selection_strategy", observed=True):
                    g = g.sort_values("calibration_points")
                    ax.plot(g["calibration_points"], g[metric], marker="o", linewidth=1.4, label=strategy)
                ax.axhline(0, color="0.25", linewidth=0.8)
                ax.set_title(f"{site} — {model}")
                ax.grid(alpha=0.25)
                if j == 0:
                    ax.set_ylabel(ylabel)
        axes[-1, 0].set_xlabel("Local calibration points")
        axes[-1, 1].set_xlabel("Local calibration points")
        axes[0, 0].legend(fontsize=7)
        fig.suptitle(title)
        fig.tight_layout()
        fig.savefig(figdir / filename, dpi=180)
        plt.close(fig)


def copy_figures(outdir: Path, report_figdir: Path) -> None:
    report_figdir.mkdir(parents=True, exist_ok=True)
    for filename, _, _ in FIGURES:
        src = outdir / "figures" / filename
        if src.exists():
            shutil.copy2(src, report_figdir / filename)


def render_figures(report_path: Path, report_figdir: Path) -> str:
    blocks = []
    for i, (filename, title, caption) in enumerate(FIGURES, start=1):
        rel = os.path.relpath(report_figdir / filename, start=report_path.parent)
        blocks.append(
            "\n".join(
                [
                    f"### Figure {i}. {title}",
                    "",
                    f"![{title}]({Path(rel).as_posix()})",
                    "",
                    caption,
                ]
            )
        )
    return "\n\n".join(blocks)


def report_table(df: pd.DataFrame, cols: list[str], max_rows: int = 30) -> str:
    if df.empty:
        return "_No rows._"
    return markdown_table(df[[c for c in cols if c in df.columns]], max_rows=max_rows)


def write_report(
    report_path: Path,
    outdir: Path,
    report_figdir: Path,
    site_summary: pd.DataFrame,
    fold_summary: pd.DataFrame,
    summary: pd.DataFrame,
    best: pd.DataFrame,
) -> None:
    random_learning = best[best["selection_strategy"] == "random"].copy()
    headline = best[
        best["selection_strategy"].isin(["random", "landscape_wetdry_prior", "global_prediction_extremes"])
    ].copy()
    headline = headline.sort_values(["site", "base_model", "selection_strategy", "calibration_points"])

    best_final = (
        best.sort_values(["site", "base_model", "rmse_gain_median", "delta_nse_median"], ascending=[True, True, False, False])
        .groupby(["site", "base_model"], as_index=False, observed=True)
        .first()
    )

    body = f"""# Stage 2 temporal-blocked local calibration CV

This report adds a less spatially punitive local-calibration diagnostic to the
strict spatio-temporal experiment. The question here is:

> If a landowner measures a few known locations during some dates, does that
> local information improve predictions for **unseen dates at those same
> locations**?

## Validation design

- Dates are sorted chronologically and split into contiguous temporal folds.
- Requested folds: 10. Sites with fewer than 10 dates use the maximum possible
  number of date folds.
- For each fold, selected local points are calibrated using all other dates.
- Validation is performed on the held-out dates at the same selected points.
- Metrics are pooled across held-out folds before NSE/RMSE are calculated. This
  avoids unstable fold-level NSE when a fold contains only one or two dates.
- Selection strategies that use observed soil moisture, especially
  `field_knowledge_wetdry_proxy`, are calculated from calibration dates only.

This is not an independent validation score. It is a temporal transfer /
sensor-budget diagnostic layered on top of the independent dense validation.

## Site and fold inventory

{markdown_table(site_summary)}

{markdown_table(fold_summary, max_rows=40)}

## Headline result: best temporal-CV calibration by site/model

This table reports the best local calibration result found for each site and
model, ranked by RMSE gain and then NSE gain. Positive RMSE gain and positive
NSE gain mean the local layer improved over the uncalibrated model.

{report_table(best_final, ["site", "base_model", "selection_strategy", "budget_label", "calibration_points", "method", "nse_median", "delta_nse_median", "rmse_median", "rmse_gain_median", "bias_median", "n_replicates"], max_rows=12)}

## Random point-budget learning curves

Random placement is the most conservative deployment analogue because it does
not assume the landowner already knows where the model fails. The table below
keeps the best calibration method per random point budget and reports median
pooled 10-fold temporal-CV metrics across random replicates. The full
method-by-method table is retained in `temporal_cv_summary.csv`.

{report_table(random_learning, ["site", "base_model", "budget_label", "calibration_points", "method", "nse_median", "delta_nse_median", "rmse_median", "rmse_gain_median", "ubrmse_median", "bias_median", "pearson_r_median", "n_replicates"], max_rows=80)}

## Strategy comparison

This compact table keeps only the best calibration method per
site/model/selection-strategy/budget. It is useful for comparing random
selection against terrain/model-prior placement and the observed wet/dry
upper-bound proxy.

{report_table(headline, ["site", "base_model", "selection_strategy", "budget_label", "calibration_points", "method", "nse_median", "delta_nse_median", "rmse_median", "rmse_gain_median", "bias_median", "n_replicates"], max_rows=120)}

## Figures

{render_figures(report_path, report_figdir)}

## Interpretation guardrails

- This is a **same-location temporal transfer** test, not a spatial transfer
  test. It should be read alongside, not instead of, the strict
  spatial+temporal block.
- A 10-fold temporal CV uses roughly 90% of dates for calibration in each fold.
  It isolates the effect of adding more local point locations, but it is
  optimistic relative to a landowner collecting only one or two campaign dates.
- Esdale has only nine dense-campaign dates, so it uses nine temporal folds
  rather than ten.
- Tarrawarra still uses grid-cell-aggregated supports, not raw TDR points.
- Tarrawarra model6 remains affected by the historical missing/zero coarse
  SMIPS-anchor caveat.

CSV outputs are written under:

`{outdir}`
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    args.report_figdir.mkdir(parents=True, exist_ok=True)
    budget_specs = spiking.parse_budget_specs(args.budgets)
    rng = np.random.default_rng(args.seed)

    site_rows: list[dict] = []
    fold_rows: list[dict] = []
    selected_rows: list[dict] = []
    fit_rows: list[dict] = []
    fold_eval_rows: list[dict] = []
    accumulator: dict[tuple, MetricAccumulator] = {}

    for site, path in spiking.SITE_PATHS.items():
        print(f"loading {site}: {path}", flush=True)
        df = spiking.load_site(site, path)
        dates = sorted(df["date"].unique())
        folds = make_temporal_folds(dates, args.folds)
        if not folds:
            print(f"skipping {site}: too few dates for temporal CV", flush=True)
            continue

        site_rows.append(
            {
                "site": site,
                "rows": int(len(df)),
                "models": ",".join(sorted(df["base_model"].unique())),
                "points": int(df["point_id"].nunique()),
                "dates": int(len(dates)),
                "date_min": min(dates),
                "date_max": max(dates),
                "actual_temporal_folds": int(folds[0]["n_folds"]),
                "seasons": ",".join(sorted(map(str, df["season"].dropna().unique()))),
            }
        )
        for fold in folds:
            fold_rows.append(
                {
                    "site": site,
                    "fold": fold["fold"],
                    "n_folds": fold["n_folds"],
                    "n_train_dates": fold["n_train_dates"],
                    "n_test_dates": fold["n_test_dates"],
                    "test_date_min": fold["test_date_min"],
                    "test_date_max": fold["test_date_max"],
                }
            )

        # Budgets are resolved against the maximum eligible points across folds.
        max_eligible = 0
        for fold in folds:
            ps = point_summary_for_fold(df, fold["train_dates"], fold["test_dates"])
            max_eligible = max(max_eligible, int(ps["eligible"].sum()) if not ps.empty else 0)
        resolved: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()
        for spec in budget_specs:
            label, budget = spiking.resolve_budget(spec, max_eligible)
            if budget <= 0:
                continue
            key = (label, budget)
            if key not in seen:
                resolved.append(key)
                seen.add(key)

        for budget_label, budget in resolved:
            for strategy in SELECTION_STRATEGIES:
                reps = args.random_reps if strategy == "random" and budget < max_eligible else 1
                for rep in range(reps):
                    evaluate_cv_design(
                        site=site,
                        df=df,
                        folds=folds,
                        strategy=strategy,
                        budget_label=budget_label,
                        budget=budget,
                        replicate=rep,
                        rng=rng,
                        accumulator=accumulator,
                        selected_rows=selected_rows,
                        fold_rows=fold_eval_rows,
                        fit_rows=fit_rows,
                    )

    site_summary = pd.DataFrame(site_rows)
    fold_summary = pd.DataFrame(fold_rows)
    selected = pd.DataFrame(selected_rows)
    fold_eval = pd.DataFrame(fold_eval_rows)
    fit_metadata = pd.DataFrame(fit_rows)
    metrics = build_metrics(accumulator)
    summary = summarise_metrics(metrics)
    best = best_calibration_by_budget(summary)

    site_summary.to_csv(args.outdir / "site_summary.csv", index=False)
    fold_summary.to_csv(args.outdir / "temporal_fold_summary.csv", index=False)
    selected.to_csv(args.outdir / "selected_points_by_fold.csv", index=False)
    fold_eval.to_csv(args.outdir / "fold_evaluation_rows.csv", index=False)
    fit_metadata.to_csv(args.outdir / "calibration_fit_metadata.csv", index=False)
    metrics.to_csv(args.outdir / "temporal_cv_metrics_by_design.csv", index=False)
    summary.to_csv(args.outdir / "temporal_cv_summary.csv", index=False)
    best.to_csv(args.outdir / "temporal_cv_best_by_budget.csv", index=False)

    make_figures(args.outdir, summary)
    copy_figures(args.outdir, args.report_figdir)
    write_report(args.report, args.outdir, args.report_figdir, site_summary, fold_summary, summary, best)
    run_summary = {
        "outdir": str(args.outdir),
        "report": str(args.report),
        "report_figdir": str(args.report_figdir),
        "folds_requested": args.folds,
        "budgets": budget_specs,
        "random_reps": args.random_reps,
        "seed": args.seed,
        "validation_geometry": "same selected points, held-out contiguous temporal folds",
        "selection_strategies": SELECTION_STRATEGIES,
        "methods": METHODS,
    }
    (args.outdir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    print(f"wrote outputs: {args.outdir}", flush=True)
    print(f"wrote report: {args.report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
