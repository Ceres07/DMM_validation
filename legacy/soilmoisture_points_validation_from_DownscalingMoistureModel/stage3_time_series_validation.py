"""Stage 3: time-series validation and calibration-transfer tests.

This workflow compares the dense point calibration and in-situ time-series
calibration in both transfer directions:

1. train a local residual calibration on dense point observations, then apply it
   to Phenode wireless time-series sensors and score by southern-hemisphere
   season;
2. train the same residual calibration on Phenode wireless sensors, then apply it
   back to the dense point campaign.

The calibration target is the model6 residual ``obs - model6_pred``. The main
calibrator is a ridge residual model using model6's own inputs plus the base
model6 prediction. A bias-only calibrator is also written to output tables as a
low-complexity reference.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_PHENODE_DIR = Path("/Volumes/Dmitry_work/borevitz_projects/Data/Phenode_wireless_data")
DEFAULT_DENSE_FEATURES = Path(
    "/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/"
    "Validation_2stage/stage1_dense_unseen_validation/point_date_model_inputs.csv"
)
DEFAULT_REPORTS_DIR = REPO_ROOT / "reports"
DEFAULT_STAGE3_DIR = DEFAULT_REPORTS_DIR / "stage3_time_series_validation"

SEASON_ORDER = ["spring", "summer", "autumn", "winter"]


def fmt(value: float, digits: int = 3) -> str:
    try:
        value = float(value)
    except Exception:
        return "NA"
    return "NA" if not np.isfinite(value) else f"{value:.{digits}f}"


def safe_json(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    return value


def season_name(month: int) -> str:
    if month in (9, 10, 11):
        return "spring"
    if month in (12, 1, 2):
        return "summer"
    if month in (3, 4, 5):
        return "autumn"
    return "winter"


def add_season_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    dt = pd.to_datetime(out["date"])
    out["month"] = dt.dt.month
    out["season"] = out["month"].map(season_name)
    # Assign December to the following summer year so Dec 2025/Jan-Feb 2026
    # appear as one summer period.
    out["season_year"] = dt.dt.year + ((out["month"] == 12) & (out["season"] == "summer")).astype(int)
    out["season"] = pd.Categorical(out["season"], categories=SEASON_ORDER, ordered=True)
    return out


def markdown_table(df: pd.DataFrame, digits: int = 3) -> str:
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
    ]
    for _, row in df.iterrows():
        vals: list[str] = []
        for col in cols:
            value = row[col]
            if pd.isna(value):
                vals.append("")
            elif isinstance(value, (float, np.floating)):
                vals.append(f"{float(value):.{digits}f}")
            else:
                vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return "\n".join(lines)


def load_phenode_observations(folder: Path) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for path in sorted(folder.glob("*.csv")):
        if path.name.startswith("._"):
            continue
        raw = pd.read_csv(path)
        required = ["Timestamp", "Device Name", "Latitude", "Longitude", "Soil Moisture (VWC%)"]
        missing = [c for c in required if c not in raw.columns]
        if missing:
            print(f"skipping {path.name}: missing columns {missing}", flush=True)
            continue

        ts = pd.to_datetime(raw["Timestamp"], errors="coerce", utc=True)
        obs = pd.to_numeric(raw["Soil Moisture (VWC%)"], errors="coerce")
        lon = pd.to_numeric(raw["Longitude"], errors="coerce")
        lat = pd.to_numeric(raw["Latitude"], errors="coerce")
        ok = ts.notna() & obs.notna() & lon.between(-180, 180) & lat.between(-90, 90)
        if not ok.any():
            continue

        device = raw.loc[ok, "Device Name"].astype(str).str.strip()
        point = path.stem
        df = pd.DataFrame(
            {
                "point": point,
                "device_name": device,
                "date": ts.loc[ok].dt.date.astype(str),
                "measurement_time": ts.loc[ok].dt.strftime("%H:%M:%SZ"),
                "obs_sm_pct": obs.loc[ok].astype(float),
                "lon": lon.loc[ok].astype(float),
                "lat": lat.loc[ok].astype(float),
                "source_file": path.name,
                "source_row": raw.index[ok].astype(int),
                "pred_sm_pct": np.nan,
                "residual_obs_minus_pred": np.nan,
                "residual_pred_minus_obs": np.nan,
            }
        )
        rows.append(df)
    if not rows:
        raise SystemExit(f"No usable Phenode soil-moisture rows found in {folder}")
    out = pd.concat(rows, ignore_index=True)
    return out.sort_values(["point", "date"]).reset_index(drop=True)


def bbox_from_rows(rows: pd.DataFrame, padding_deg: float = 0.002) -> tuple[float, float, float, float]:
    return (
        float(rows["lon"].min() - padding_deg),
        float(rows["lat"].min() - padding_deg),
        float(rows["lon"].max() + padding_deg),
        float(rows["lat"].max() + padding_deg),
    )


def load_dense_features(path: Path) -> pd.DataFrame:
    dense = pd.read_csv(path)
    dense["date"] = pd.to_datetime(dense["date"]).dt.date.astype(str)
    dense["residual_obs_minus_pred"] = dense["obs_sm_pct"] - dense["pred_sm_pct"]
    dense["residual_pred_minus_obs"] = dense["pred_sm_pct"] - dense["obs_sm_pct"]
    return add_season_columns(dense)


def predict_phenode_features(phenode_rows: pd.DataFrame, cache_csv: Path, force: bool) -> pd.DataFrame:
    from emt.model6 import model as model6
    from emt.persist import load_model
    from soilmoisture_points_validation.dense_validation_and_spiking import sample_model6_inputs

    feature_rows = sample_model6_inputs(
        phenode_rows,
        bbox_from_rows(phenode_rows),
        cache_csv=cache_csv,
        force=force,
    )
    if "device_name" not in feature_rows.columns:
        join_cols = ["point", "date", "source_row"]
        metadata = phenode_rows[join_cols + ["device_name", "source_file"]].drop_duplicates(join_cols)
        feature_rows = feature_rows.merge(metadata, on=join_cols, how="left")
    model = load_model("model6")
    if model is None:
        raise SystemExit("No trained model6 found at data/models/model6.joblib")
    feature_rows["pred_sm_pct"] = model.predict(feature_rows[list(model6.FEATURES)])
    feature_rows["residual_obs_minus_pred"] = feature_rows["obs_sm_pct"] - feature_rows["pred_sm_pct"]
    feature_rows["residual_pred_minus_obs"] = feature_rows["pred_sm_pct"] - feature_rows["obs_sm_pct"]
    return add_season_columns(feature_rows)


class ResidualCalibrator:
    def __init__(self, method: str, feature_cols: list[str]):
        self.method = method
        self.feature_cols = feature_cols
        self.bias_: float = 0.0
        self.model = None

    def fit(self, df: pd.DataFrame) -> "ResidualCalibrator":
        train = df.dropna(subset=["residual_obs_minus_pred", "pred_sm_pct"]).copy()
        self.bias_ = float(train["residual_obs_minus_pred"].mean()) if len(train) else 0.0
        if self.method == "bias_only":
            return self
        if self.method != "ridge_residual":
            raise ValueError(f"unsupported calibrator method: {self.method}")

        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import Ridge
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler

        x_cols = self.feature_cols + ["pred_sm_pct"]
        X = train[x_cols].replace([np.inf, -np.inf], np.nan)
        y = train["residual_obs_minus_pred"].to_numpy(dtype=float)
        self.model = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), Ridge(alpha=1.0))
        self.model.fit(X, y)
        return self

    def predict_residual(self, df: pd.DataFrame) -> np.ndarray:
        if self.method == "bias_only" or self.model is None:
            return np.full(len(df), self.bias_, dtype=float)
        x_cols = self.feature_cols + ["pred_sm_pct"]
        X = df[x_cols].replace([np.inf, -np.inf], np.nan)
        return self.model.predict(X)


def apply_calibrators(df: pd.DataFrame, calibrators: dict[str, ResidualCalibrator]) -> pd.DataFrame:
    out = df.copy()
    for name, calibrator in calibrators.items():
        correction = calibrator.predict_residual(out)
        out[f"pred_{name}"] = out["pred_sm_pct"] + correction
        out[f"residual_pred_minus_obs_{name}"] = out[f"pred_{name}"] - out["obs_sm_pct"]
    return out


def metrics(y_true, y_pred) -> dict:
    from emt.evaluation import metrics as _metrics

    return _metrics(y_true, y_pred)


def metric_rows(
    df: pd.DataFrame,
    pred_cols: dict[str, str],
    group_cols: list[str] | None = None,
) -> pd.DataFrame:
    rows = []
    group_cols = group_cols or []
    grouped = [((), df)] if not group_cols else df.groupby(group_cols, observed=True, dropna=False, sort=True)
    for key, group in grouped:
        if group_cols:
            if not isinstance(key, tuple):
                key = (key,)
            base = dict(zip(group_cols, key))
        else:
            base = {}
        for label, pred_col in pred_cols.items():
            row = dict(base)
            row["prediction"] = label
            row.update(metrics(group["obs_sm_pct"], group[pred_col]))
            rows.append(row)
    return pd.DataFrame(rows)


def summarize_phenode_inputs(phenode: pd.DataFrame) -> pd.DataFrame:
    return (
        phenode.groupby(["point", "device_name"], as_index=False, observed=True)
        .agg(
            n=("obs_sm_pct", "size"),
            date_min=("date", "min"),
            date_max=("date", "max"),
            lon=("lon", "mean"),
            lat=("lat", "mean"),
            obs_mean=("obs_sm_pct", "mean"),
            obs_min=("obs_sm_pct", "min"),
            obs_max=("obs_sm_pct", "max"),
        )
        .sort_values("point")
    )


def make_figures(phenode_eval: pd.DataFrame, dense_eval: pd.DataFrame, figure_dir: Path) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:
        print(f"figures skipped: {type(exc).__name__}: {exc}", flush=True)
        return

    figure_dir.mkdir(parents=True, exist_ok=True)
    phenode = phenode_eval.sort_values(["point", "date"]).copy()
    phenode["date_dt"] = pd.to_datetime(phenode["date"])
    points = sorted(phenode["point"].unique())
    n = len(points)

    fig, axes = plt.subplots(n, 1, figsize=(11, max(2.0 * n, 4)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, point in zip(axes, points):
        sub = phenode[phenode["point"] == point]
        label = str(sub.get("device_name", pd.Series([point])).iloc[0])
        ax.plot(sub["date_dt"], sub["obs_sm_pct"], color="black", linewidth=1.3, label="observed")
        ax.plot(sub["date_dt"], sub["pred_sm_pct"], color="0.55", linewidth=1.0, label="model6")
        ax.plot(sub["date_dt"], sub["pred_dense_ridge"], color="#2563eb", linewidth=1.1, label="dense-calibrated")
        ax.set_ylabel(label)
    axes[0].legend(ncol=3, fontsize=8, loc="upper left")
    axes[-1].set_xlabel("Date")
    fig.suptitle("Phenode time-series: observed vs model6 vs dense-point calibrated", y=0.995)
    fig.tight_layout()
    fig.savefig(figure_dir / "phenode_timeseries_observed_vs_predicted.png", dpi=160)
    plt.close(fig)

    fig, axes = plt.subplots(n, 1, figsize=(11, max(2.0 * n, 4)), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, point in zip(axes, points):
        sub = phenode[phenode["point"] == point]
        label = str(sub.get("device_name", pd.Series([point])).iloc[0])
        ax.axhline(0, color="0.25", linewidth=0.8)
        ax.plot(sub["date_dt"], sub["pred_sm_pct"] - sub["obs_sm_pct"], color="0.55", linewidth=1.0, label="model6")
        ax.plot(sub["date_dt"], sub["pred_dense_ridge"] - sub["obs_sm_pct"], color="#2563eb", linewidth=1.0, label="dense-calibrated")
        ax.set_ylabel(label)
    axes[0].legend(ncol=2, fontsize=8, loc="upper left")
    axes[-1].set_xlabel("Date")
    fig.suptitle("Phenode residuals through time (prediction - observation)", y=0.995)
    fig.tight_layout()
    fig.savefig(figure_dir / "phenode_residuals_through_time.png", dpi=160)
    plt.close(fig)

    dense = dense_eval.copy()
    dense["date_dt"] = pd.to_datetime(dense["date"])
    date_resid = (
        dense.assign(
            base_resid=dense["pred_sm_pct"] - dense["obs_sm_pct"],
            phenode_resid=dense["pred_phenode_ridge"] - dense["obs_sm_pct"],
        )
        .groupby("date_dt", as_index=False)
        .agg(base_resid=("base_resid", "mean"), phenode_resid=("phenode_resid", "mean"))
    )
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.axhline(0, color="0.25", linewidth=0.8)
    ax.plot(date_resid["date_dt"], date_resid["base_resid"], marker="o", label="model6")
    ax.plot(date_resid["date_dt"], date_resid["phenode_resid"], marker="o", label="Phenode-calibrated")
    ax.set(ylabel="Mean residual (prediction - observation, %)", xlabel="Dense campaign date")
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(figure_dir / "dense_mean_residuals_with_phenode_calibration.png", dpi=160)
    plt.close(fig)


def write_report(
    report_path: Path,
    output_dir: Path,
    phenode_summary: pd.DataFrame,
    phenode_overall: pd.DataFrame,
    phenode_by_season: pd.DataFrame,
    phenode_by_season_year: pd.DataFrame,
    dense_overall: pd.DataFrame,
    dense_by_season: pd.DataFrame,
    calibration_summary: dict,
) -> None:
    def slim(df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in ["season", "season_year", "prediction", "n", "nse", "r2", "r", "rmse", "ubrmse", "bias"] if c in df.columns]
        out = df[cols].copy()
        if "season" in out.columns:
            out["season"] = out["season"].astype(str)
        return out

    body = f"""# Stage 3 — Time series validation

Objective: quantify how well dense point calibration transfers to unseen time
windows in the Phenode wireless in-situ time series, and compare that with the
reverse transfer from time-series sensors back to dense point observations.

## Inputs

- Dense calibration source:
  `{DEFAULT_DENSE_FEATURES}`
- Phenode wireless data:
  `{DEFAULT_PHENODE_DIR}`
- Stage 3 output folder:
  `{output_dir}`

Phenode usable observations:

{markdown_table(phenode_summary[["point", "device_name", "n", "date_min", "date_max", "obs_mean", "obs_min", "obs_max"]])}

## Calibration method

The primary local calibration is a ridge residual model trained on:

`model6 residual = observed soil moisture - uncalibrated model6 prediction`

using model6's own input features plus the uncalibrated model6 prediction. A
bias-only correction is also written to CSV as a conservative reference, but the
main tables below focus on:

- `model6`: uncalibrated shipped model6;
- `dense_ridge`: residual calibration trained on dense points and applied to
  Phenode time-series sensors;
- `phenode_ridge`: residual calibration trained on Phenode sensors and applied
  back to dense points.

The repo's shared evaluation helper reports `r2` as the same coefficient as NSE;
Pearson correlation is reported separately as `r`.

Training rows:

- Dense residual calibration rows: {calibration_summary["dense_training_rows"]}
- Phenode residual calibration rows: {calibration_summary["phenode_training_rows"]}
- Dense dates: {calibration_summary["dense_date_min"]} to {calibration_summary["dense_date_max"]}
- Phenode dates: {calibration_summary["phenode_date_min"]} to {calibration_summary["phenode_date_max"]}

## Dense point calibration → Phenode time-series sensors

Overall:

{markdown_table(slim(phenode_overall))}

By season:

{markdown_table(slim(phenode_by_season))}

By season-year:

{markdown_table(slim(phenode_by_season_year))}

## Phenode time-series calibration → dense points

Overall:

{markdown_table(slim(dense_overall))}

By season:

{markdown_table(slim(dense_by_season))}

Dense points only cover autumn/winter campaign dates, so spring and summer are
not available for this reverse-transfer test.

## Figures

- `stage3_time_series_validation/figures/phenode_timeseries_observed_vs_predicted.png`
- `stage3_time_series_validation/figures/phenode_residuals_through_time.png`
- `stage3_time_series_validation/figures/dense_mean_residuals_with_phenode_calibration.png`

## Short interpretation

The Stage 3 comparison is intentionally a transfer test, not an in-sample
calibration score. Dense point calibration is trained on a short autumn/winter
field campaign and then asked to transfer into a longer Phenode time series that
includes unseen spring and summer conditions. The reverse test asks whether
continuous in-situ sensors can provide a useful local residual correction for
the dense spatial campaign.

If dense-calibrated Phenode metrics degrade in spring/summer, that indicates the
dense campaign calibration is too seasonally narrow. If Phenode-calibrated dense
metrics improve, that suggests continuous local sensors are valuable anchors for
spatial dense-point campaigns. If they degrade, the Phenode sensors and dense
handheld points are likely measuring different soil depths, micro-sites, or
calibration scales.

Important caveat: Phenode VWC%, dense handheld points and model6's OzNet-style
root-zone target are not guaranteed to represent exactly the same sensing depth
or support volume. Treat these as calibration-transfer diagnostics unless sensor
depths/calibration equations are reconciled.
"""
    report_path.write_text(body)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stage 3 time-series validation.")
    parser.add_argument("--phenode-dir", type=Path, default=DEFAULT_PHENODE_DIR)
    parser.add_argument("--dense-features", type=Path, default=DEFAULT_DENSE_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_STAGE3_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORTS_DIR / "stage3_time_series_validation_2026-07-29.md")
    parser.add_argument("--force-phenode-features", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "figures").mkdir(parents=True, exist_ok=True)

    from emt.model6 import model as model6

    dense = load_dense_features(args.dense_features)
    phenode_raw = load_phenode_observations(args.phenode_dir)
    phenode = predict_phenode_features(
        phenode_raw,
        cache_csv=args.output_dir / "phenode_point_date_model_inputs.csv",
        force=args.force_phenode_features,
    )

    feature_cols = list(model6.FEATURES)
    dense_calibrators = {
        "dense_bias": ResidualCalibrator("bias_only", feature_cols).fit(dense),
        "dense_ridge": ResidualCalibrator("ridge_residual", feature_cols).fit(dense),
    }
    phenode_calibrators = {
        "phenode_bias": ResidualCalibrator("bias_only", feature_cols).fit(phenode),
        "phenode_ridge": ResidualCalibrator("ridge_residual", feature_cols).fit(phenode),
    }

    phenode_eval = apply_calibrators(phenode, dense_calibrators)
    dense_eval = apply_calibrators(dense, phenode_calibrators)

    phenode_pred_cols = {
        "model6": "pred_sm_pct",
        "dense_bias": "pred_dense_bias",
        "dense_ridge": "pred_dense_ridge",
    }
    dense_pred_cols = {
        "model6": "pred_sm_pct",
        "phenode_bias": "pred_phenode_bias",
        "phenode_ridge": "pred_phenode_ridge",
    }

    phenode_overall = metric_rows(phenode_eval, phenode_pred_cols)
    phenode_by_season = metric_rows(phenode_eval, phenode_pred_cols, ["season"])
    phenode_by_season_year = metric_rows(phenode_eval, phenode_pred_cols, ["season", "season_year"])
    phenode_by_sensor_season = metric_rows(phenode_eval, phenode_pred_cols, ["point", "device_name", "season"])

    dense_overall = metric_rows(dense_eval, dense_pred_cols)
    dense_by_season = metric_rows(dense_eval, dense_pred_cols, ["season"])
    dense_by_date = metric_rows(dense_eval, dense_pred_cols, ["date"])

    phenode_summary = summarize_phenode_inputs(phenode_eval)

    phenode_eval.to_csv(args.output_dir / "phenode_predictions_with_dense_calibration.csv", index=False)
    dense_eval.to_csv(args.output_dir / "dense_predictions_with_phenode_calibration.csv", index=False)
    phenode_summary.to_csv(args.output_dir / "phenode_sensor_summary.csv", index=False)
    phenode_overall.to_csv(args.output_dir / "phenode_metrics_overall.csv", index=False)
    phenode_by_season.to_csv(args.output_dir / "phenode_metrics_by_season.csv", index=False)
    phenode_by_season_year.to_csv(args.output_dir / "phenode_metrics_by_season_year.csv", index=False)
    phenode_by_sensor_season.to_csv(args.output_dir / "phenode_metrics_by_sensor_season.csv", index=False)
    dense_overall.to_csv(args.output_dir / "dense_metrics_overall.csv", index=False)
    dense_by_season.to_csv(args.output_dir / "dense_metrics_by_season.csv", index=False)
    dense_by_date.to_csv(args.output_dir / "dense_metrics_by_date.csv", index=False)
    with (args.output_dir / "calibration_summary.json").open("w") as f:
        json.dump(
            {
                "dense_training_rows": int(len(dense)),
                "phenode_training_rows": int(len(phenode)),
                "dense_date_min": str(dense["date"].min()),
                "dense_date_max": str(dense["date"].max()),
                "phenode_date_min": str(phenode["date"].min()),
                "phenode_date_max": str(phenode["date"].max()),
                "feature_cols": feature_cols,
            },
            f,
            indent=2,
            default=safe_json,
        )

    make_figures(phenode_eval, dense_eval, args.output_dir / "figures")
    write_report(
        args.report,
        args.output_dir,
        phenode_summary,
        phenode_overall,
        phenode_by_season,
        phenode_by_season_year,
        dense_overall,
        dense_by_season,
        {
            "dense_training_rows": int(len(dense)),
            "phenode_training_rows": int(len(phenode)),
            "dense_date_min": str(dense["date"].min()),
            "dense_date_max": str(dense["date"].max()),
            "phenode_date_min": str(phenode["date"].min()),
            "phenode_date_max": str(phenode["date"].max()),
        },
    )

    print("\nStage 3 complete")
    print("----------------")
    print(f"Phenode rows: {len(phenode)} across {phenode['point'].nunique()} sensors")
    print(f"Dense rows: {len(dense)} across {dense['point'].nunique()} points")
    print(f"Report: {args.report}")
    print(f"Output folder: {args.output_dir}")
    print("\nDense → Phenode overall:")
    print(phenode_overall.to_string(index=False))
    print("\nPhenode → Dense overall:")
    print(dense_overall.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
