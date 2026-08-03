from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd


def _bootstrap_mean_ci(
    group: pd.DataFrame,
    value_col: str,
    cluster_col: str = "point_id",
    n_boot: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    if n_boot <= 0 or group.empty or cluster_col not in group.columns:
        return np.nan, np.nan
    clusters = np.asarray(sorted(group[cluster_col].dropna().unique()))
    if clusters.size < 2:
        return np.nan, np.nan
    by_cluster = group.groupby(cluster_col, observed=True)[value_col].agg(["sum", "count"]).reindex(clusters)
    sums = by_cluster["sum"].to_numpy(dtype=float)
    counts = by_cluster["count"].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    values = np.empty(n_boot, dtype=float)
    for _ in range(n_boot):
        idx = rng.integers(0, clusters.size, size=clusters.size)
        values[_] = float(sums[idx].sum() / counts[idx].sum())
    lo, hi = np.percentile(values, [2.5, 97.5])
    return float(lo), float(hi)


def paired_model_comparison(
    df: pd.DataFrame,
    key_cols: list[str],
    group_cols: list[str] | None = None,
    n_boot: int = 1000,
    seed: int = 42,
) -> pd.DataFrame:
    """Paired model comparison on matched point-date observations.

    Negative `mean_delta_abs_error` means `model_a` has lower absolute error than
    `model_b` on the same observations.
    """
    group_cols = group_cols or []
    rows: list[dict] = []
    models = sorted(df["model_name"].unique())
    if len(models) < 2:
        return pd.DataFrame()

    base_cols = list(dict.fromkeys(key_cols + ["point_id", "date", "obs_sm_pct"] + group_cols))
    keep_cols = base_cols + ["model_name", "abs_error", "sq_error", "residual"]
    sub = df[keep_cols].dropna(subset=["abs_error", "sq_error"]).copy()

    if group_cols:
        grouped = sub.groupby(group_cols, dropna=False, observed=True, sort=True)
    else:
        grouped = [((), sub)]

    for group_key, group in grouped:
        group_base = {}
        if group_cols:
            if not isinstance(group_key, tuple):
                group_key = (group_key,)
            group_base = dict(zip(group_cols, group_key))

        for model_a, model_b in combinations(models, 2):
            a = group[group["model_name"] == model_a]
            b = group[group["model_name"] == model_b]
            merged = a.merge(
                b,
                on=base_cols,
                suffixes=("_a", "_b"),
                how="inner",
            )
            if merged.empty:
                continue
            merged["delta_abs_error"] = merged["abs_error_a"] - merged["abs_error_b"]
            merged["delta_sq_error"] = merged["sq_error_a"] - merged["sq_error_b"]
            merged["delta_residual"] = merged["residual_a"] - merged["residual_b"]
            lo, hi = _bootstrap_mean_ci(
                merged,
                "delta_abs_error",
                cluster_col="point_id",
                n_boot=n_boot,
                seed=seed,
            )
            row = dict(group_base)
            row.update(
                {
                    "model_a": model_a,
                    "model_b": model_b,
                    "n_matched": int(len(merged)),
                    "mean_delta_abs_error": float(merged["delta_abs_error"].mean()),
                    "mean_delta_abs_error_ci95_low": lo,
                    "mean_delta_abs_error_ci95_high": hi,
                    "median_delta_abs_error": float(merged["delta_abs_error"].median()),
                    "mean_delta_sq_error": float(merged["delta_sq_error"].mean()),
                    "rmse_a": float(np.sqrt(merged["sq_error_a"].mean())),
                    "rmse_b": float(np.sqrt(merged["sq_error_b"].mean())),
                    "rmse_delta_a_minus_b": float(np.sqrt(merged["sq_error_a"].mean()) - np.sqrt(merged["sq_error_b"].mean())),
                    "bias_a": float(merged["residual_a"].mean()),
                    "bias_b": float(merged["residual_b"].mean()),
                    "bias_delta_a_minus_b": float(merged["delta_residual"].mean()),
                    "fraction_model_a_better_abs_error": float((merged["delta_abs_error"] < 0).mean()),
                }
            )
            rows.append(row)

    return pd.DataFrame(rows)


def paired_point_differences(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    models = sorted(df["model_name"].unique())
    if len(models) < 2:
        return pd.DataFrame()

    rows: list[pd.DataFrame] = []
    base_cols = list(dict.fromkeys(key_cols + ["point_id", "date", "lon", "lat"]))
    sub = df[base_cols + ["model_name", "abs_error", "sq_error", "residual"]].dropna()
    for model_a, model_b in combinations(models, 2):
        a = sub[sub["model_name"] == model_a]
        b = sub[sub["model_name"] == model_b]
        merged = a.merge(b, on=base_cols, suffixes=("_a", "_b"), how="inner")
        if merged.empty:
            continue
        merged["model_a"] = model_a
        merged["model_b"] = model_b
        merged["delta_abs_error"] = merged["abs_error_a"] - merged["abs_error_b"]
        merged["delta_sq_error"] = merged["sq_error_a"] - merged["sq_error_b"]
        point = (
            merged.groupby(["model_a", "model_b", "point_id"], as_index=False)
            .agg(
                lon=("lon", "mean"),
                lat=("lat", "mean"),
                n_matched=("delta_abs_error", "size"),
                mean_delta_abs_error=("delta_abs_error", "mean"),
                mean_delta_sq_error=("delta_sq_error", "mean"),
            )
        )
        rows.append(point)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
