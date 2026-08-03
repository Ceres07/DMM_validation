#!/usr/bin/env python3
"""Run model8 over the dense point campaign and build model-agnostic tables.

This script is intentionally a bridge between the process-model branch of
DownscalingMoistureModel and the independent DMM_validation schema.

It uses the existing model6 dense validation table as the paired comparison
backbone: same point/date/observation rows, same terrain diagnostics, with
`pred_sm_pct` replaced by model8 predictions sampled from model8 30 m maps.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_MODEL6_TABLE = Path(
    "/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/current_model6_dense/"
    "model_agnostic_predictions.csv"
)
DEFAULT_OUTPUT_DIR = Path(
    "/Volumes/Dmitry_work/borevitz_projects/DMM_validation/outputs/model6_vs_model8_dense"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model6-table", type=Path, default=DEFAULT_MODEL6_TABLE)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--model-name", default="model8_process")
    parser.add_argument("--padding-deg", type=float, default=0.002)
    parser.add_argument("--step-deg", type=float, default=0.1)
    parser.add_argument("--force", action="store_true", help="Ignore cached output tables and rerun model8 maps.")
    return parser.parse_args()


def bbox_from_points(df: pd.DataFrame, padding: float) -> tuple[float, float, float, float]:
    return (
        float(df["lon"].min() - padding),
        float(df["lat"].min() - padding),
        float(df["lon"].max() + padding),
        float(df["lat"].max() + padding),
    )


def sample_model8_predictions(
    model6: pd.DataFrame,
    bbox: tuple[float, float, float, float],
    step_deg: float,
) -> pd.DataFrame:
    from emt.covariates import sample_points
    from emt.model8.predict import predict_map

    rows = []
    for i, date in enumerate(sorted(model6["date"].unique()), start=1):
        print(f"model8 map {i}/{model6['date'].nunique()}: {date}", flush=True)
        ds = predict_map(
            bbox,
            date,
            step_deg=step_deg,
            save=False,
            plot=False,
            verbose=True,
        )
        sub = model6.loc[model6["date"] == date].copy()
        preds = []
        for row in sub.itertuples(index=False):
            pred = sample_points(ds["sm_pred"], float(row.lon), float(row.lat))
            preds.append(float(pred.values))
        sub["pred_sm_pct"] = np.asarray(preds, dtype=float)
        sub["model8_sample_status"] = np.where(np.isfinite(sub["pred_sm_pct"]), "ok", "nan")
        rows.append(sub)
    return pd.concat(rows, ignore_index=True)


def main() -> int:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    model8_path = args.outdir / "model8_model_agnostic_predictions.csv"
    combined_path = args.outdir / "model6_model8_combined_predictions.csv"

    model6 = pd.read_csv(args.model6_table)
    model6["date"] = pd.to_datetime(model6["date"]).dt.date.astype(str)
    model6 = model6.dropna(subset=["point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]).copy()
    model6["model_name"] = "model6_rf"

    if model8_path.exists() and not args.force:
        print(f"using cached {model8_path}", flush=True)
        model8 = pd.read_csv(model8_path)
    else:
        bbox = bbox_from_points(model6, args.padding_deg)
        print(f"dense AOI bbox W/S/E/N: {bbox}", flush=True)
        model8 = sample_model8_predictions(model6, bbox, args.step_deg)
        model8["model_name"] = args.model_name
        model8["residual_obs_minus_pred"] = model8["obs_sm_pct"] - model8["pred_sm_pct"]
        model8["residual_pred_minus_obs"] = model8["pred_sm_pct"] - model8["obs_sm_pct"]
        model8.to_csv(model8_path, index=False)
        print(f"wrote {model8_path}", flush=True)

    combined = pd.concat([model6, model8], ignore_index=True, sort=False)
    combined.to_csv(combined_path, index=False)
    print(f"wrote {combined_path}", flush=True)
    print(f"rows by model:\n{combined['model_name'].value_counts().to_string()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

