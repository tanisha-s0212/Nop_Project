"""Leakage-safe calendar and lag features for monthly count forecasts."""

from __future__ import annotations

import math
import re
from typing import Sequence

import numpy as np
import pandas as pd

MIN_HISTORY = 12
LAGS = (1, 3, 6, 12)
FEATURE_COLUMNS = (
    "year",
    "quarter",
    *(f"month_{month:02d}" for month in range(1, 13)),
    *(f"lag_{lag}" for lag in LAGS),
)


def _period(value: object) -> pd.Period:
    try:
        if isinstance(value, str) and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value):
            raise ValueError
        if not isinstance(value, (str, pd.Period)):
            raise ValueError
        result = pd.Period(value, freq="M")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid monthly period: {value!r}") from exc
    if pd.isna(result):
        raise ValueError(f"Invalid monthly period: {value!r}")
    return result


def _validate_history(periods: Sequence[object], counts: Sequence[object]) -> tuple[list[pd.Period], list[float]]:
    if len(periods) != len(counts):
        raise ValueError("periods and counts must have the same length")
    if len(counts) < MIN_HISTORY:
        raise ValueError(f"At least {MIN_HISTORY} consecutive monthly observations are required")
    parsed = [_period(p) for p in periods]
    values: list[float] = []
    for value in counts:
        if isinstance(value, bool) or not isinstance(value, (int, float, np.integer, np.floating)):
            raise ValueError("invoice counts must be numeric, non-boolean, and finite")
        try:
            number = float(value)
        except (OverflowError, TypeError, ValueError) as exc:
            raise ValueError("invoice counts must be finite and non-negative") from exc
        if not math.isfinite(number) or number < 0:
            raise ValueError("invoice counts must be finite and non-negative")
        values.append(number)
    if any(b.ordinal - a.ordinal != 1 for a, b in zip(parsed, parsed[1:])):
        raise ValueError("history must contain exactly one observation per consecutive month")
    return parsed, values


def build_feature_row(period: object, history_periods: Sequence[object], history_counts: Sequence[object]) -> dict[str, float]:
    """Build one feature row using only observations before the requested month."""
    target_period = _period(period)
    parsed, values = _validate_history(history_periods, history_counts)
    if target_period.ordinal != parsed[-1].ordinal + 1:
        raise ValueError("prediction period must immediately follow the latest history month")
    if len(values) < MIN_HISTORY:
        raise ValueError(f"At least {MIN_HISTORY} months of history are required")

    result: dict[str, float] = {"year": float(target_period.year), "quarter": float((target_period.month - 1) // 3 + 1)}
    result.update({f"month_{month:02d}": float(target_period.month == month) for month in range(1, 13)})
    for lag in LAGS:
        result[f"lag_{lag}"] = values[-lag]
    return result


def build_supervised_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Build training rows; each target month uses strictly earlier count values."""
    required = {"period", "invoice_count"}
    if not required.issubset(frame.columns):
        raise ValueError("dataset must contain period and invoice_count columns")
    periods, counts = _validate_history(frame["period"].tolist(), frame["invoice_count"].tolist())
    rows: list[dict[str, float]] = []
    targets: list[float] = []
    for index in range(MIN_HISTORY, len(counts)):
        rows.append(build_feature_row(periods[index], periods[:index], counts[:index]))
        targets.append(counts[index])
    if not rows:
        raise ValueError(f"At least {MIN_HISTORY + 1} observations are required to construct a training row")
    features = pd.DataFrame(rows, columns=FEATURE_COLUMNS, dtype=float)
    return features, pd.Series(targets, name="invoice_count", dtype=float)
