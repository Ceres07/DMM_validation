#!/usr/bin/env python3
"""Convert Nerrigundah 20 m GM-TDR surveys into DMM validation observations."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path

import pandas as pd
from pyproj import Transformer


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RAW_DATA = Path("/Volumes/Dmitry_work/borevitz_projects/Data/Nerrigundah_data/raw/data")
DEFAULT_OUTDIR = ROOT / "outputs" / "nerrigundah_conversion"
DEFAULT_SOURCE_CRS = "EPSG:20256"  # AGD66 / AMG zone 56.

TRANSFORM = {
    "scale": 1.0,
    "rotation_deg": 8.0 + 44.0 / 60.0,
    "translation_easting": 600801.2134,
    "translation_northing": -6406373.7733,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Nerrigundah GM-TDR grid surveys.")
    parser.add_argument("--raw-data", type=Path, default=DEFAULT_RAW_DATA)
    parser.add_argument("--outdir", type=Path, default=DEFAULT_OUTDIR)
    parser.add_argument("--source-crs", default=DEFAULT_SOURCE_CRS)
    parser.add_argument("--bbox-padding-deg", type=float, default=0.01)
    parser.add_argument("--year", type=int, default=1997)
    parser.add_argument("--min-sm-pct", type=float, default=0.0)
    parser.add_argument("--max-sm-pct", type=float, default=100.0)
    return parser.parse_args()


def read_local_dem_bounds(raw_data: Path) -> dict[str, float]:
    path = raw_data / "DEM" / "ACCURATE" / "nerrig-local.grd"
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    values: dict[str, float] = {}
    for line in text[:10]:
        parts = line.split()
        if len(parts) >= 2 and parts[0] in {"NoCols", "NoRows", "XLLCorner", "YLLCorner", "GridSpacing"}:
            values[parts[0]] = float(parts[1])
    missing = {"NoCols", "NoRows", "XLLCorner", "YLLCorner", "GridSpacing"}.difference(values)
    if missing:
        raise ValueError(f"Could not parse DEM grid header {path}; missing {sorted(missing)}")
    spacing = values["GridSpacing"]
    return {
        "xmin": values["XLLCorner"],
        "xmax": values["XLLCorner"] + (values["NoCols"] - 1) * spacing,
        "ymin": values["YLLCorner"],
        "ymax": values["YLLCorner"] + (values["NoRows"] - 1) * spacing,
        "spacing": spacing,
    }


def local_to_amg(x_local: pd.Series, y_local: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Invert the published AMG-to-local rotation/translation transform."""
    angle = math.radians(TRANSFORM["rotation_deg"])
    vx = (x_local / TRANSFORM["scale"]) - TRANSFORM["translation_easting"]
    vy = (y_local / TRANSFORM["scale"]) - TRANSFORM["translation_northing"]
    east = vx * math.cos(angle) + vy * math.sin(angle)
    north = -vx * math.sin(angle) + vy * math.cos(angle)
    return east, north


def date_from_filename(path: Path, year: int) -> str:
    match = re.search(r"TDR(?P<day>\d{2})(?P<month>\d{2})\.dat$", path.name, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Cannot parse TDR date from {path.name}")
    return date(year, int(match.group("month")), int(match.group("day"))).isoformat()


def coord_label(value: float) -> str:
    ivalue = int(round(float(value)))
    return f"m{abs(ivalue)}" if ivalue < 0 else f"p{ivalue}"


def read_tdr_file(path: Path, day: str, bounds: dict[str, float], args: argparse.Namespace) -> pd.DataFrame:
    raw = pd.read_csv(
        path,
        sep=r"\s+",
        names=["local_easting_m", "local_northing_m", "obs_sm_pct"],
        engine="python",
    )
    raw["source_row"] = raw.index.astype(int)
    for col in ["local_easting_m", "local_northing_m", "obs_sm_pct"]:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    ok = (
        raw["local_easting_m"].between(bounds["xmin"], bounds["xmax"])
        & raw["local_northing_m"].between(bounds["ymin"], bounds["ymax"])
        & raw["obs_sm_pct"].gt(args.min_sm_pct)
        & raw["obs_sm_pct"].le(args.max_sm_pct)
    )
    out = raw.loc[ok].copy()
    out["date"] = day
    out["source_file"] = path.name
    out["point_id"] = [
        f"nerrig_x{coord_label(x)}_y{coord_label(y)}"
        for x, y in zip(out["local_easting_m"], out["local_northing_m"])
    ]
    return out


def build_observations(args: argparse.Namespace) -> tuple[pd.DataFrame, dict]:
    bounds = read_local_dem_bounds(args.raw_data)
    pieces = []
    logs = []
    for path in sorted((args.raw_data / "GM-TDR").glob("TDR*.dat")):
        day = date_from_filename(path, args.year)
        raw_rows = sum(1 for _ in path.open("r", encoding="utf-8", errors="ignore"))
        df = read_tdr_file(path, day, bounds, args)
        pieces.append(df)
        logs.append({"source_file": path.name, "date": day, "raw_rows": raw_rows, "kept_rows": int(len(df))})
    if not pieces:
        raise SystemExit(f"No GM-TDR files found in {args.raw_data / 'GM-TDR'}")
    obs = pd.concat(pieces, ignore_index=True)
    east, north = local_to_amg(obs["local_easting_m"], obs["local_northing_m"])
    obs["amg_easting_m"] = east
    obs["amg_northing_m"] = north
    transformer = Transformer.from_crs(args.source_crs, "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(obs["amg_easting_m"].to_numpy(), obs["amg_northing_m"].to_numpy())
    obs["lon"] = lon
    obs["lat"] = lat
    obs["pred_sm_pct"] = pd.NA
    obs["depth_cm"] = 15
    obs["measurement_id"] = obs["source_file"].astype(str) + ":" + obs["source_row"].astype(str)
    obs["model_name"] = "observation_only"
    obs = obs[
        [
            "model_name",
            "point_id",
            "date",
            "lon",
            "lat",
            "obs_sm_pct",
            "pred_sm_pct",
            "measurement_id",
            "source_file",
            "source_row",
            "local_easting_m",
            "local_northing_m",
            "amg_easting_m",
            "amg_northing_m",
            "depth_cm",
        ]
    ]
    summary = {
        "raw_data": str(args.raw_data),
        "source_crs": args.source_crs,
        "transform": TRANSFORM,
        "dem_local_bounds": bounds,
        "filter": f"DEM-supported local grid and {args.min_sm_pct} < obs_sm_pct <= {args.max_sm_pct}",
        "input_files": logs,
        "rows": int(len(obs)),
        "points": int(obs["point_id"].nunique()),
        "dates": int(obs["date"].nunique()),
        "date_min": str(obs["date"].min()),
        "date_max": str(obs["date"].max()),
    }
    return obs.sort_values(["date", "point_id"]).reset_index(drop=True), summary


def main() -> int:
    args = parse_args()
    args.raw_data = args.raw_data.resolve()
    args.outdir = args.outdir.resolve()
    args.outdir.mkdir(parents=True, exist_ok=True)
    obs, summary = build_observations(args)
    obs_path = args.outdir / "nerrigundah_dmm_observation_template.csv"
    bbox_path = args.outdir / "nerrigundah_points_bbox.json"
    summary_path = args.outdir / "nerrigundah_conversion_summary.json"
    obs.to_csv(obs_path, index=False)
    bbox = {
        "west": float(obs["lon"].min() - args.bbox_padding_deg),
        "south": float(obs["lat"].min() - args.bbox_padding_deg),
        "east": float(obs["lon"].max() + args.bbox_padding_deg),
        "north": float(obs["lat"].max() + args.bbox_padding_deg),
        "order": "west,south,east,north",
    }
    bbox_path.write_text(json.dumps(bbox, indent=2), encoding="utf-8")
    summary["bbox_wsen"] = [bbox["west"], bbox["south"], bbox["east"], bbox["north"]]
    summary["outputs"] = {"observations": str(obs_path), "bbox_json": str(bbox_path)}
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
