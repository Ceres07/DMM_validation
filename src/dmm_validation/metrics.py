from __future__ import annotations

import numpy as np
import pandas as pd


def _finite_pairs(y_true, y_pred) -> tuple[np.ndarray, np.ndarray]:
    obs = np.asarray(y_true, dtype=float)
    pred = np.asarray(y_pred, dtype=float)
    ok = np.isfinite(obs) & np.isfinite(pred)
    return obs[ok], pred[ok]


def soil_moisture_metrics(y_true, y_pred) -> dict[str, float]:
    """Return common soil-moisture validation metrics.

    Bias is prediction minus observation. `nse` and `r2` are the same
    coefficient-of-determination style score: 1 - SS_res / SS_tot. Pearson
    correlation is reported separately as `pearson_r` and `pearson_r2`.
    """
    obs, pred = _finite_pairs(y_true, y_pred)
    n = int(obs.size)
    if n < 2:
        return {
            "n": n,
            "nse": np.nan,
            "r2": np.nan,
            "pearson_r": np.nan,
            "pearson_r2": np.nan,
            "rmse": np.nan,
            "ubrmse": np.nan,
            "bias": np.nan,
            "mae": np.nan,
            "median_ae": np.nan,
            "pred_vs_obs_slope": np.nan,
            "pred_vs_obs_intercept": np.nan,
        }

    err = pred - obs
    bias = float(np.mean(err))
    rmse = float(np.sqrt(np.mean(err**2)))
    ubrmse = float(np.sqrt(max(rmse**2 - bias**2, 0.0)))
    mae = float(np.mean(np.abs(err)))
    median_ae = float(np.median(np.abs(err)))

    ss_res = float(np.sum((obs - pred) ** 2))
    ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
    nse = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else np.nan

    if np.std(obs) > 0 and np.std(pred) > 0:
        pearson_r = float(np.corrcoef(obs, pred)[0, 1])
        pearson_r2 = float(pearson_r**2)
    else:
        pearson_r = np.nan
        pearson_r2 = np.nan

    if np.std(obs) > 0:
        slope, intercept = np.polyfit(obs, pred, deg=1)
        slope = float(slope)
        intercept = float(intercept)
    else:
        slope = np.nan
        intercept = np.nan

    return {
        "n": n,
        "nse": nse,
        "r2": nse,
        "pearson_r": pearson_r,
        "pearson_r2": pearson_r2,
        "rmse": rmse,
        "ubrmse": ubrmse,
        "bias": bias,
        "mae": mae,
        "median_ae": median_ae,
        "pred_vs_obs_slope": slope,
        "pred_vs_obs_intercept": intercept,
    }


def metric_table(
    df: pd.DataFrame,
    group_cols: list[str] | None = None,
    obs_col: str = "obs_sm_pct",
    pred_col: str = "pred_sm_pct",
) -> pd.DataFrame:
    """Compute metrics overall or by group."""
    group_cols = group_cols or []
    rows: list[dict] = []

    if group_cols:
        grouped = df.groupby(group_cols, dropna=False, observed=True, sort=True)
    else:
        grouped = [((), df)]

    for key, group in grouped:
        if group_cols:
            if not isinstance(key, tuple):
                key = (key,)
            row = dict(zip(group_cols, key))
        else:
            row = {}
        row.update(soil_moisture_metrics(group[obs_col], group[pred_col]))
        rows.append(row)

    return pd.DataFrame(rows)


def add_error_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["residual"] = out["pred_sm_pct"] - out["obs_sm_pct"]
    out["abs_error"] = out["residual"].abs()
    out["sq_error"] = out["residual"] ** 2
    return out

