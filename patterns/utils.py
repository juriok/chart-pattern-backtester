import numpy as np
import pandas as pd
from scipy.signal import argrelextrema


def get_pivot_highs(df: pd.DataFrame, order: int) -> pd.Series:
    arr = df['high'].values
    idx = argrelextrema(arr, np.greater, order=order)[0]
    return pd.Series(data=arr[idx], index=idx, dtype=float)


def get_pivot_lows(df: pd.DataFrame, order: int) -> pd.Series:
    arr = df['low'].values
    idx = argrelextrema(arr, np.less, order=order)[0]
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