from typing import List, Dict
import pandas as pd
import config
from patterns.utils import rolling_avg_volume


def detect_double_top(df: pd.DataFrame, ph: pd.Series, pl: pd.Series) -> List[Dict]:
    signals: List[Dict] = []
    reported: set = set()
    ph_idx = ph.index.tolist()
    pl_idx = pl.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(ph_idx) - 1):
        i1, i2 = ph_idx[k], ph_idx[k + 1]
        p1, p2 = ph[i1], ph[i2]

        if not (config.MIN_PATTERN_BARS <= i2 - i1 <= config.MAX_PATTERN_BARS):
            continue
        mean_top = (p1 + p2) / 2
        if abs(p1 - p2) / mean_top > config.PATTERN_TOLERANCE:
            continue

        valley_candidates = [j for j in pl_idx if i1 < j < i2]
        if not valley_candidates:
            continue
        valley_i = min(valley_candidates, key=lambda j: pl[j])
        valley_v = pl[valley_i]

        if (mean_top - valley_v) / mean_top < 0.01:
            continue

        for j in range(i2 + 1, min(i2 + config.BREAKOUT_WINDOW + 1, len(df))):
            if j in reported:
                continue
            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[j] >= avg_vol.iloc[j])
            if df['close'].iloc[j] < valley_v and vol_ok:
                signals.append({'bar_index': j, 'pattern': 'double_top',
                                 'direction': 'short', 'key_level': valley_v})
                reported.add(j)
                break

    return signals


def detect_double_bottom(df: pd.DataFrame, ph: pd.Series, pl: pd.Series) -> List[Dict]:
    signals: List[Dict] = []
    reported: set = set()
    pl_idx = pl.index.tolist()
    ph_idx = ph.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(pl_idx) - 1):
        i1, i2 = pl_idx[k], pl_idx[k + 1]
        p1, p2 = pl[i1], pl[i2]

        if not (config.MIN_PATTERN_BARS <= i2 - i1 <= config.MAX_PATTERN_BARS):
            continue
        mean_bot = (p1 + p2) / 2
        if abs(p1 - p2) / mean_bot > config.PATTERN_TOLERANCE:
            continue

        peak_candidates = [j for j in ph_idx if i1 < j < i2]
        if not peak_candidates:
            continue
        peak_i = max(peak_candidates, key=lambda j: ph[j])
        peak_v = ph[peak_i]

        if (peak_v - mean_bot) / mean_bot < 0.01:
            continue

        for j in range(i2 + 1, min(i2 + config.BREAKOUT_WINDOW + 1, len(df))):
            if j in reported:
                continue
            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[j] >= avg_vol.iloc[j])
            if df['close'].iloc[j] > peak_v and vol_ok:
                signals.append({'bar_index': j, 'pattern': 'double_bottom',
                                 'direction': 'long', 'key_level': peak_v})
                reported.add(j)
                break

    return signals