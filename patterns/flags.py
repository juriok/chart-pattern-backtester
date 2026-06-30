from typing import List, Dict
import numpy as np
import pandas as pd
import config
from patterns.utils import rolling_avg_volume


def _slope_norm(arr: np.ndarray) -> float:
    if len(arr) < 2 or arr[0] == 0:
        return 0.0
    x = np.arange(len(arr), dtype=float)
    return float(np.polyfit(x, arr, 1)[0] / arr[0])


def detect_bull_flag(df: pd.DataFrame) -> List[Dict]:
    signals: List[Dict] = []
    reported: set = set()
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values
    avg_vol = rolling_avg_volume(df)

    for i in range(config.POLE_BARS + config.MIN_FLAG_BARS, len(df)):
        if i in reported:
            continue
        for flag_len in range(config.MIN_FLAG_BARS,
                              min(config.MAX_FLAG_BARS + 1, i - config.POLE_BARS + 1)):
            pole_start = i - flag_len - config.POLE_BARS
            pole_end   = i - flag_len
            if pole_start < 0:
                continue

            if (closes[pole_end] - closes[pole_start]) / closes[pole_start] < config.MIN_POLE_PCT:
                continue

            f_h = highs[pole_end:i]
            f_l = lows[pole_end:i]
            s_h, s_l = _slope_norm(f_h), _slope_norm(f_l)

            if s_h >= 0 or s_l >= 0:
                continue
            if s_h < -config.MAX_FLAG_SLOPE or s_l < -config.MAX_FLAG_SLOPE:
                continue
            if (f_h.max() - f_l.min()) / closes[pole_end] > config.MAX_FLAG_CHANNEL_W:
                continue

            x = np.arange(len(f_h), dtype=float)
            upper = np.polyval(np.polyfit(x, f_h, 1), float(len(f_h)))

            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[i] >= avg_vol.iloc[i])
            if closes[i] > upper and vol_ok:
                signals.append({'bar_index': i, 'pattern': 'bull_flag',
                                 'direction': 'long', 'key_level': float(upper)})
                reported.add(i)
                break

    return signals


def detect_bear_flag(df: pd.DataFrame) -> List[Dict]:
    signals: List[Dict] = []
    reported: set = set()
    closes = df['close'].values
    highs  = df['high'].values
    lows   = df['low'].values
    avg_vol = rolling_avg_volume(df)

    for i in range(config.POLE_BARS + config.MIN_FLAG_BARS, len(df)):
        if i in reported:
            continue
        for flag_len in range(config.MIN_FLAG_BARS,
                              min(config.MAX_FLAG_BARS + 1, i - config.POLE_BARS + 1)):
            pole_start = i - flag_len - config.POLE_BARS
            pole_end   = i - flag_len
            if pole_start < 0:
                continue

            if (closes[pole_start] - closes[pole_end]) / closes[pole_start] < config.MIN_POLE_PCT:
                continue

            f_h = highs[pole_end:i]
            f_l = lows[pole_end:i]
            s_h, s_l = _slope_norm(f_h), _slope_norm(f_l)

            if s_h <= 0 or s_l <= 0:
                continue
            if s_h > config.MAX_FLAG_SLOPE or s_l > config.MAX_FLAG_SLOPE:
                continue
            if (f_h.max() - f_l.min()) / closes[pole_end] > config.MAX_FLAG_CHANNEL_W:
                continue

            x = np.arange(len(f_l), dtype=float)
            lower = np.polyval(np.polyfit(x, f_l, 1), float(len(f_l)))

            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[i] >= avg_vol.iloc[i])
            if closes[i] < lower and vol_ok:
                signals.append({'bar_index': i, 'pattern': 'bear_flag',
                                 'direction': 'short', 'key_level': float(lower)})
                reported.add(i)
                break

    return signals