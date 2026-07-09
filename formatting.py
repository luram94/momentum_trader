"""
Percentage Formatting Helpers
==============================
Single source of truth for displaying return values.

Convention: all return values are stored as decimal fractions
(0.0523 means 5.23%) -- in the database, in scan results, and in
chart inputs. Convert to percent only at the display boundary, and
only via these helpers, so tables, charts, and cards can never
disagree on scale.
"""

from __future__ import annotations

from typing import Iterable, Optional

import pandas as pd


def frac_to_pct(value):
    """
    Convert a decimal fraction to a percent number (0.0523 -> 5.23).

    Accepts scalars or pandas Series/arrays. NaN passes through.
    """
    return value * 100


def format_pct(value: Optional[float], decimals: int = 2, signed: bool = False) -> str:
    """
    Format a decimal fraction as a percent string (0.0523 -> '5.23%').

    Args:
        value: Decimal fraction (0.0523 means 5.23%). None/NaN allowed.
        decimals: Number of decimal places.
        signed: Prefix positive values with '+'.

    Returns:
        Formatted percent string, or 'N/A' for None/NaN.
    """
    if value is None or pd.isna(value):
        return 'N/A'
    spec = f"+.{decimals}f" if signed else f".{decimals}f"
    return f"{format(value * 100, spec)}%"


def frac_cols_to_pct(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    """
    Return a copy of df with the given fraction columns scaled to percent.

    Columns not present in the DataFrame are ignored, so callers can pass
    the full list of potential return columns.

    Args:
        df: Source DataFrame (not modified).
        columns: Column names holding decimal fractions.

    Returns:
        Copy of df with listed columns multiplied by 100.
    """
    df = df.copy()
    for col in columns:
        if col in df.columns:
            df[col] = df[col] * 100
    return df
