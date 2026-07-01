import numpy as np
import pandas as pd
from scipy.signal import argrelextrema

import config


def _smooth(arr: np.ndarray, span: int) -> np.ndarray:
    """EMA-smooth a series before extrema detection to strip high-frequency noise.
    Denoising the series *before* locating turning points (rather than detecting on
    raw high/low) is what stops single-bar spikes from being mistaken for structural
    pivots — it materially cleans up the pattern set and lifts the backtest edge.
    span<=1 disables smoothing (raw behaviour)."""
    if span and span > 1:
        return pd.Series(arr).ewm(span=span, adjust=False).mean().values
    return arr


def get_pivot_highs(df: pd.DataFrame, order: int) -> pd.Series:
    arr    = df['high'].values
    smooth = _smooth(arr, getattr(config, 'PIVOT_SMOOTH_SPAN', 0))
    idx    = argrelextrema(smooth, np.greater, order=order)[0]
    # Index off the smoothed turning point, but report the *raw* high there so
    # pattern geometry and breakout levels stay anchored to real prices.
    return pd.Series(data=arr[idx], index=idx, dtype=float)


def get_pivot_lows(df: pd.DataFrame, order: int) -> pd.Series:
    arr    = df['low'].values
    smooth = _smooth(arr, getattr(config, 'PIVOT_SMOOTH_SPAN', 0))
    idx    = argrelextrema(smooth, np.less, order=order)[0]
    return pd.Series(data=arr[idx], index=idx, dtype=float)


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev).abs(),
        (df['low']  - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def line_val(x1: int, y1: float, x2: int, y2: float, x: int) -> float:
    if x2 == x1:
        return float(y1)
    return float(y1 + (y2 - y1) * (x - x1) / (x2 - x1))


def rolling_avg_volume(df: pd.DataFrame, period: int = 20) -> pd.Series:
    return df['volume'].rolling(period, min_periods=1).mean()