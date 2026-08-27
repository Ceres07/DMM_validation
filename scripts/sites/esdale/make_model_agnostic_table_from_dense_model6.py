#!/usr/bin/env python3
"""Convert the existing dense model6 point table into the model-agnostic schema.

This is a bridge script for the current DownscalingMoistureModel outputs. Future
RF/process models should preferably write the schema directly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_INPUT = Path(
    "/Volumes/Dmitry_work/borevitz_projects/model6_dense_validation_spiking/"
    "Validation_2stage/stage1_dense_unseen_validation/point_date_model_inputs.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-name", default="model6_rf")
    parser.add_argument("--prediction-col", default="pred_sm_pct")
    parser.add_argument("--observed-col", default="obs_sm_pct")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    df = pd.read_csv(args.input)
    if args.prediction_col not in df.columns:
        raise SystemExit(f"missing prediction column: {args.prediction_col}")
    if args.observed_col not in df.columns:
        raise SystemExit(f"missing observed column: {args.observed_col}")

    point_col = "point_id" if "point_id" in df.columns else "point"
    out = df.copy()
    out["model_name"] = args.model_name
    out["point_id"] = out[point_col].astype(str)
    out["obs_sm_pct"] = out[args.observed_col]
    out["pred_sm_pct"] = out[args.prediction_col]

    leading = ["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]
    cols = leading + [c for c in out.columns if c not in leading]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out[cols].to_csv(args.output, index=False)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

