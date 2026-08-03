from __future__ import annotations

import pandas as pd


SEASON_ORDER = ["spring", "summer", "autumn", "winter"]


def southern_hemisphere_season(timestamp) -> str:
    """Return the Australian/southern-hemisphere season for a date-like value."""
    month = pd.Timestamp(timestamp).month
    if month in (9, 10, 11):
        return "spring"
    if month in (12, 1, 2):
        return "summer"
    if month in (3, 4, 5):
        return "autumn"
    return "winter"


def southern_hemisphere_season_year(timestamp) -> int:
    """Return season year, assigning December to the following summer year."""
    ts = pd.Timestamp(timestamp)
    if ts.month == 12:
        return ts.year + 1
    return ts.year


def add_season_columns(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    out = df.copy()
    dates = pd.to_datetime(out[date_col])
    out["season"] = dates.map(southern_hemisphere_season)
    out["season_year"] = dates.map(southern_hemisphere_season_year)
    out["season"] = pd.Categorical(out["season"], categories=SEASON_ORDER, ordered=True)
    return out

