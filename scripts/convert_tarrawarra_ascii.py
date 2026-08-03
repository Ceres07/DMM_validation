#!/usr/bin/env python3
"""Convert Tarrawarra ASCII DEM/TDR files into DMM_validation-ready outputs."""

from __future__ import annotations

import argparse
from pathlib import Path

from tarrawarra import (
    bbox_from_points,
    read_tdr_patterns,
    write_json,
    write_tarrawarra_dem_geotiff,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dem-local", type=Path, help="Tarrawarra local-coordinate DEM, e.g. tarrawar.dem")
    parser.add_argument("--tdr-dir", type=Path, help="Directory containing sm*.tdr files")
    parser.add_argument("--tdr-files", type=Path, nargs="*", default=[], help="Individual sm*.tdr files")
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--bbox-padding-deg", type=float, default=0.002)
    parser.add_argument("--point-prefix", default="tarrawarra")
    parser.add_argument("--keep-local-z", action="store_true", help="Do not convert DEM elevations to AHD = z - 2.6 m")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)

    outputs = {}

    if args.dem_local:
        dem_out = args.outdir / "tarrawarra_5m_dem_agd66_amg55.tif"
        write_tarrawarra_dem_geotiff(
            args.dem_local,
            dem_out,
            convert_z_to_ahd=not args.keep_local_z,
        )
        outputs["dem_geotiff"] = str(dem_out)
        print(f"wrote {dem_out}")

    tdr_files = list(args.tdr_files)
    if args.tdr_dir:
        tdr_files.extend(sorted(args.tdr_dir.glob("sm*.tdr")))

    if tdr_files:
        obs = read_tdr_patterns(tdr_files, point_prefix=args.point_prefix)
        obs_path = args.outdir / "tarrawarra_tdr_observations.csv"
        obs.to_csv(obs_path, index=False)
        outputs["tdr_observations"] = str(obs_path)
        print(f"wrote {obs_path} ({len(obs)} rows)")

        leading = ["model_name", "point_id", "date", "lon", "lat", "obs_sm_pct", "pred_sm_pct"]
        template_cols = leading + [c for c in obs.columns if c not in leading]
        template_path = args.outdir / "tarrawarra_dmm_observation_template.csv"
        obs[template_cols].to_csv(template_path, index=False)
        outputs["dmm_observation_template"] = str(template_path)
        print(f"wrote {template_path}")

        bbox = bbox_from_points(obs, padding_deg=args.bbox_padding_deg)
        bbox_path = args.outdir / "tarrawarra_points_bbox.json"
        write_json(bbox_path, bbox)
        outputs["points_bbox"] = str(bbox_path)
        print(f"wrote {bbox_path}: {bbox}")

    metadata = {
        "source_crs": "Tarrawarra local coordinates / AGD66 AMG zone 55",
        "target_crs": "EPSG:4326",
        "dem_crs": "EPSG:20255",
        "local_to_amg55": {
            "easting0": 361474,
            "northing0": 5829892,
            "rotation_degrees": 14.0,
            "formula": "E=e0+x*cos(theta)-y*sin(theta); N=n0+x*sin(theta)+y*cos(theta)",
        },
        "dem_vertical_adjustment": "AHD = local_z - 2.6 m unless --keep-local-z is used",
        "feature_extraction_bbox_policy": "Use tarrawarra_points_bbox.json from transformed observation points, not the local DEM extent.",
        "outputs": outputs,
    }
    metadata_path = args.outdir / "tarrawarra_conversion_metadata.json"
    write_json(metadata_path, metadata)
    print(f"wrote {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
