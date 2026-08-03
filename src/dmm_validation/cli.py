from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .metrics import metric_table
from .paired import paired_model_comparison, paired_point_differences
from .plots import make_all_figures
from .reporting import write_geojson_points, write_report
from .schema import default_pair_keys, load_prediction_table
from .terrain import add_terrain_strata, detect_terrain_columns


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run independent model-agnostic dense-point soil-moisture validation."
    )
    parser.add_argument("--predictions", required=True, type=Path, help="Long-format model-agnostic prediction CSV/parquet.")
    parser.add_argument("--outdir", required=True, type=Path, help="Output folder for metrics, maps, figures and report.")
    parser.add_argument(
        "--terrain-cols",
        default="auto",
        help="Comma-separated terrain/diagnostic columns, 'auto' to detect, or 'none'.",
    )
    parser.add_argument(
        "--pair-keys",
        default=None,
        help="Comma-separated keys used to pair models. Default: point_id,date plus optional depth/measurement fields.",
    )
    parser.add_argument("--terrain-quantiles", type=int, default=3, help="Number of quantile strata for numeric terrain columns.")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Cluster bootstrap iterations for paired error CIs.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for bootstrap CIs.")
    return parser.parse_args(argv)


def _sort_cols(df: pd.DataFrame, leading: list[str]) -> pd.DataFrame:
    cols = [c for c in leading if c in df.columns] + [c for c in df.columns if c not in leading]
    return df[cols]


def seasonal_bias_summary(df: pd.DataFrame) -> pd.DataFrame:
    by_season = (
        df.groupby(["model_name", "season"], as_index=False, observed=True)
        .agg(n=("residual", "size"), bias=("residual", "mean"), rmse=("sq_error", lambda x: float(np.sqrt(np.mean(x)))))
    )
    amp = (
        by_season.groupby("model_name", as_index=False)
        .agg(
            seasonal_bias_min=("bias", "min"),
            seasonal_bias_max=("bias", "max"),
        )
    )
    amp["seasonal_bias_amplitude"] = amp["seasonal_bias_max"] - amp["seasonal_bias_min"]
    return by_season.merge(amp, on="model_name", how="left")


def moisture_quantile_bias(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    try:
        out["obs_moisture_quantile"] = pd.qcut(
            out["obs_sm_pct"],
            q=4,
            labels=["dry_q1", "q2", "q3", "wet_q4"],
            duplicates="drop",
        )
    except ValueError:
        return pd.DataFrame()
    return (
        out.groupby(["model_name", "obs_moisture_quantile"], as_index=False, observed=True)
        .agg(
            n=("residual", "size"),
            obs_mean=("obs_sm_pct", "mean"),
            pred_mean=("pred_sm_pct", "mean"),
            bias=("residual", "mean"),
            rmse=("sq_error", lambda x: float(np.sqrt(np.mean(x)))),
            mae=("abs_error", "mean"),
        )
    )


def terrain_metric_table(df: pd.DataFrame, terrain_metadata: list[dict]) -> pd.DataFrame:
    rows = []
    for meta in terrain_metadata:
        stratum_col = meta["stratum_col"]
        if stratum_col not in df.columns:
            continue
        table = metric_table(df.dropna(subset=[stratum_col]), ["model_name", stratum_col])
        if table.empty:
            continue
        table.insert(1, "terrain_var", meta["terrain_var"])
        table = table.rename(columns={stratum_col: "terrain_stratum"})
        rows.append(table)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def paired_by_terrain(df: pd.DataFrame, terrain_metadata: list[dict], key_cols: list[str], n_boot: int, seed: int) -> pd.DataFrame:
    rows = []
    for meta in terrain_metadata:
        stratum_col = meta["stratum_col"]
        if stratum_col not in df.columns:
            continue
        table = paired_model_comparison(df.dropna(subset=[stratum_col]), key_cols, [stratum_col], n_boot=n_boot, seed=seed)
        if table.empty:
            continue
        table.insert(0, "terrain_var", meta["terrain_var"])
        table = table.rename(columns={stratum_col: "terrain_stratum"})
        rows.append(table)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def point_metrics_with_location(df: pd.DataFrame) -> pd.DataFrame:
    metrics = metric_table(df, ["model_name", "point_id"])
    loc = df.groupby(["model_name", "point_id"], as_index=False).agg(lon=("lon", "mean"), lat=("lat", "mean"))
    return loc.merge(metrics, on=["model_name", "point_id"], how="left")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.outdir.mkdir(parents=True, exist_ok=True)
    figure_dir = args.outdir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    df = load_prediction_table(args.predictions)
    terrain_cols = detect_terrain_columns(df, args.terrain_cols)
    df, terrain_metadata = add_terrain_strata(df, terrain_cols, q=args.terrain_quantiles)

    if args.pair_keys:
        key_cols = [c.strip() for c in args.pair_keys.split(",") if c.strip()]
    else:
        key_cols = default_pair_keys(df)

    df.to_csv(args.outdir / "standardized_predictions.csv", index=False)
    (args.outdir / "terrain_strata.json").write_text(json.dumps(terrain_metadata, indent=2), encoding="utf-8")

    overall = metric_table(df, ["model_name"])
    by_season = metric_table(df, ["model_name", "season"])
    by_season_year = metric_table(df, ["model_name", "season", "season_year"])
    by_point = point_metrics_with_location(df)
    by_point_season = metric_table(df, ["model_name", "point_id", "season"])
    seasonal_bias = seasonal_bias_summary(df)
    moisture_bias = moisture_quantile_bias(df)
    terrain_metrics = terrain_metric_table(df, terrain_metadata)

    paired_overall = paired_model_comparison(df, key_cols, n_boot=args.bootstrap, seed=args.seed)
    paired_season = paired_model_comparison(df, key_cols, ["season"], n_boot=args.bootstrap, seed=args.seed)
    paired_terrain = paired_by_terrain(df, terrain_metadata, key_cols, n_boot=args.bootstrap, seed=args.seed)
    point_diffs = paired_point_differences(df, key_cols)

    outputs = {
        "metrics_overall.csv": _sort_cols(overall, ["model_name", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "metrics_by_season.csv": _sort_cols(by_season, ["model_name", "season", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "metrics_by_season_year.csv": _sort_cols(by_season_year, ["model_name", "season", "season_year", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "metrics_by_point.csv": _sort_cols(by_point, ["model_name", "point_id", "lon", "lat", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "metrics_by_point_season.csv": _sort_cols(by_point_season, ["model_name", "point_id", "season", "n", "nse", "r2", "pearson_r", "rmse", "ubrmse", "bias", "mae"]),
        "seasonal_bias_summary.csv": seasonal_bias,
        "bias_by_moisture_quantile.csv": moisture_bias,
        "metrics_by_terrain_strata.csv": terrain_metrics,
        "paired_model_comparison_overall.csv": paired_overall,
        "paired_model_comparison_by_season.csv": paired_season,
        "paired_model_comparison_by_terrain.csv": paired_terrain,
        "paired_point_error_differences.csv": point_diffs,
    }
    for filename, table in outputs.items():
        table.to_csv(args.outdir / filename, index=False)

    write_geojson_points(by_point, args.outdir / "point_metrics.geojson")
    if not point_diffs.empty:
        write_geojson_points(point_diffs, args.outdir / "paired_point_error_differences.geojson")

    make_all_figures(df, by_point, point_diffs, terrain_metadata, figure_dir)

    summary = {
        "n_rows": int(len(df)),
        "models": sorted(df["model_name"].unique()),
        "n_points": int(df["point_id"].nunique()),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        "pair_keys": key_cols,
        "terrain_columns": terrain_cols,
    }
    (args.outdir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(
        args.outdir / "report.md",
        args.predictions,
        summary,
        outputs["metrics_overall.csv"],
        outputs["metrics_by_season.csv"],
        seasonal_bias,
        moisture_bias,
        paired_overall,
        paired_season,
        terrain_metrics,
    )

    print("DMM independent dense-point validation complete")
    print(f"Rows: {len(df)}")
    print(f"Models: {', '.join(summary['models'])}")
    print(f"Output folder: {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

