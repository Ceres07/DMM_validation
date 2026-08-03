from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from pyproj import Transformer


LOCAL_TO_AMG55_EASTING0 = 361474.0
LOCAL_TO_AMG55_NORTHING0 = 5829892.0
LOCAL_TO_AMG55_ROTATION_DEG = 14.0
SOURCE_CRS = "EPSG:20255"  # AGD66 / AMG zone 55
TARGET_CRS = "EPSG:4326"   # WGS84 lon/lat
DEM_CELL_SIZE_M = 5.0
DEM_LOCAL_Z_TO_AHD_M = -2.6

TDR_DATE_RE = re.compile(r"^\s*\d{1,2}-[A-Z]{3}-\d{2}\s+", flags=re.I)


def tarrawarra_to_amg55(x, y):
    """Transform Tarrawarra local x/y metres to AGD66 AMG zone 55 easting/northing.

    This is the official affine equivalent of the Readme.1st polar formula:

    E = 361474 + x*cos(14°) - y*sin(14°)
    N = 5829892 + x*sin(14°) + y*cos(14°)
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    theta = math.radians(LOCAL_TO_AMG55_ROTATION_DEG)
    easting = LOCAL_TO_AMG55_EASTING0 + x * math.cos(theta) - y * math.sin(theta)
    northing = LOCAL_TO_AMG55_NORTHING0 + x * math.sin(theta) + y * math.cos(theta)
    return easting, northing


def amg55_to_wgs84(easting, northing):
    transformer = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
    lon, lat = transformer.transform(easting, northing)
    return lon, lat


def tarrawarra_to_wgs84(x, y):
    easting, northing = tarrawarra_to_amg55(x, y)
    lon, lat = amg55_to_wgs84(easting, northing)
    return lon, lat


def _parse_key_value_header(lines: Iterable[str], required_keys: int = 6) -> tuple[dict, list[str]]:
    header: dict[str, float] = {}
    remaining: list[str] = []
    for line in lines:
        if len(header) < required_keys and ":" in line:
            key, value = line.replace(":", " ").split()[:2]
            key = key.lower()
            if key in {"north", "south", "east", "west", "rows", "cols"}:
                header[key] = float(value)
                continue
        if len(header) >= required_keys:
            remaining.append(line)
    if len(header) != required_keys:
        raise ValueError(f"DEM header is incomplete; found keys: {sorted(header)}")
    header["rows"] = int(header["rows"])
    header["cols"] = int(header["cols"])
    return header, remaining


def read_tarrawarra_dem(path: str | Path) -> tuple[dict, np.ndarray]:
    """Read the Tarrawarra ASCII DEM format into (header, elevation array)."""
    path = Path(path)
    with path.open(encoding="latin-1") as f:
        header, value_lines = _parse_key_value_header(f)
    values: list[float] = []
    for line in value_lines:
        if line.strip():
            values.extend(float(v) for v in line.split())
    expected = header["rows"] * header["cols"]
    if len(values) != expected:
        raise ValueError(f"{path} has {len(values)} DEM values; expected {expected}")
    data = np.asarray(values, dtype="float32").reshape(header["rows"], header["cols"])
    return header, data


def tarrawarra_dem_transform(header: dict):
    """Rasterio affine transform for the rotated local DEM in AGD66 AMG zone 55."""
    from rasterio.transform import Affine

    theta = math.radians(LOCAL_TO_AMG55_ROTATION_DEG)
    cell = DEM_CELL_SIZE_M
    c, f = tarrawarra_to_amg55(header["west"], header["north"])
    return Affine(
        cell * math.cos(theta),
        cell * math.sin(theta),
        float(c),
        cell * math.sin(theta),
        -cell * math.cos(theta),
        float(f),
    )


def write_tarrawarra_dem_geotiff(
    dem_path: str | Path,
    out_tif: str | Path,
    nodata: float = -9999.0,
    zero_is_nodata: bool = True,
    convert_z_to_ahd: bool = True,
) -> Path:
    """Write the local-coordinate Tarrawarra DEM as a rotated AGD66/AMG55 GeoTIFF."""
    import rasterio

    dem_path = Path(dem_path)
    out_tif = Path(out_tif)
    out_tif.parent.mkdir(parents=True, exist_ok=True)
    header, data = read_tarrawarra_dem(dem_path)
    arr = data.astype("float32", copy=True)
    missing = ~np.isfinite(arr)
    if zero_is_nodata:
        missing |= arr == 0
    if convert_z_to_ahd:
        arr = arr + DEM_LOCAL_Z_TO_AHD_M
    arr[missing] = nodata

    with rasterio.open(
        out_tif,
        "w",
        driver="GTiff",
        height=arr.shape[0],
        width=arr.shape[1],
        count=1,
        dtype="float32",
        crs=SOURCE_CRS,
        transform=tarrawarra_dem_transform(header),
        nodata=nodata,
        compress="deflate",
        predictor=3,
    ) as dst:
        dst.write(arr, 1)
        dst.update_tags(
            source_dem=str(dem_path),
            source_crs="Tarrawarra local coordinates",
            converted_crs=SOURCE_CRS,
            vertical_adjustment="AHD = local_z - 2.6 m" if convert_z_to_ahd else "none",
            note="Rotated 5 m DEM; transform is official Readme.1st local-to-AMG55 affine.",
        )
    return out_tif


def _parse_tdr_metadata_and_rows(path: Path) -> tuple[dict, list[list[str]]]:
    metadata: dict[str, str] = {}
    rows: list[list[str]] = []
    with path.open(encoding="latin-1") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            if TDR_DATE_RE.match(stripped):
                parts = stripped.split()
                if len(parts) >= 6:
                    rows.append(parts[:6])
                continue
            if ":" in line:
                key, value = line.split(":", 1)
                metadata[key.strip().lower().replace(" ", "_")] = value.strip().strip('"')
    return metadata, rows


def _depth_cm(metadata: dict) -> float | None:
    text = metadata.get("measurement_depth", "")
    match = re.search(r"([0-9.]+)\s*cm", text, flags=re.I)
    return float(match.group(1)) if match else None


def _point_id(prefix: str, x: float, y: float, coordinate_kind: str) -> str:
    xi = int(round(x)) if abs(x - round(x)) < 1e-6 else round(x, 3)
    yi = int(round(y)) if abs(y - round(y)) < 1e-6 else round(y, 3)
    return f"{prefix}_{coordinate_kind}_{xi}_{yi}"


def read_tdr_pattern(path: str | Path, point_prefix: str = "tarrawarra") -> pd.DataFrame:
    """Read one Tarrawarra `.tdr` soil-moisture pattern and convert to lon/lat."""
    path = Path(path)
    metadata, rows = _parse_tdr_metadata_and_rows(path)
    if not rows:
        raise ValueError(f"No TDR data rows found in {path}")

    df = pd.DataFrame(
        rows,
        columns=["raw_date", "measurement_time", "x", "y", "dielectric_constant", "obs_sm_pct"],
    )
    for col in ["x", "y", "dielectric_constant", "obs_sm_pct"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["raw_date"], format="%d-%b-%y").dt.date.astype(str)

    coord_text = metadata.get("coordinate_system", "")
    is_utm = bool(re.search(r"(utm|universal\s+transverse)", coord_text, flags=re.I))
    if is_utm:
        easting = df["x"].to_numpy(dtype=float)
        northing = df["y"].to_numpy(dtype=float)
        coordinate_kind = "amg55"
        df["tarrawarra_x"] = np.nan
        df["tarrawarra_y"] = np.nan
    else:
        easting, northing = tarrawarra_to_amg55(df["x"], df["y"])
        coordinate_kind = "local"
        df["tarrawarra_x"] = df["x"]
        df["tarrawarra_y"] = df["y"]
    lon, lat = amg55_to_wgs84(easting, northing)

    source_row = np.arange(1, len(df) + 1)
    out = pd.DataFrame(
        {
            "model_name": "observation_only",
            "point_id": [
                _point_id(point_prefix, float(x), float(y), coordinate_kind)
                for x, y in zip(df["x"], df["y"])
            ],
            "date": df["date"],
            "lon": lon,
            "lat": lat,
            "obs_sm_pct": df["obs_sm_pct"],
            "pred_sm_pct": np.nan,
            "measurement_time": df["measurement_time"],
            "depth_cm": _depth_cm(metadata),
            "dielectric_constant": df["dielectric_constant"],
            "tarrawarra_x": df["tarrawarra_x"],
            "tarrawarra_y": df["tarrawarra_y"],
            "easting_agd66_amg55": easting,
            "northing_agd66_amg55": northing,
            "coordinate_system_original": coord_text,
            "coordinate_transform": "Tarrawarra local -> EPSG:20255 -> EPSG:4326"
            if not is_utm
            else "EPSG:20255 -> EPSG:4326",
            "source_file": path.name,
            "source_row": source_row,
            "raw_date": df["raw_date"],
        }
    )
    return out


def read_tdr_patterns(paths: Iterable[str | Path], point_prefix: str = "tarrawarra") -> pd.DataFrame:
    frames = [read_tdr_pattern(path, point_prefix=point_prefix) for path in paths]
    if not frames:
        raise ValueError("No TDR pattern files supplied")
    return pd.concat(frames, ignore_index=True)


def bbox_from_points(df: pd.DataFrame, padding_deg: float = 0.002) -> dict:
    """Return W/S/E/N bbox from observation coordinates, not the DEM footprint."""
    return {
        "west": float(df["lon"].min() - padding_deg),
        "south": float(df["lat"].min() - padding_deg),
        "east": float(df["lon"].max() + padding_deg),
        "north": float(df["lat"].max() + padding_deg),
        "padding_deg": float(padding_deg),
        "source": "transformed observation point coordinates",
        "order": "west,south,east,north",
    }


def write_json(path: str | Path, payload: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
