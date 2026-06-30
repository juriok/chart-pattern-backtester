from typing import List, Dict
import numpy as np
import pandas as pd
import config
from patterns.utils import rolling_avg_volume

MIN_TOUCHES = 2


def detect_ascending_triangle(df: pd.DataFrame,
                               ph: pd.Series,
                               pl: pd.Series) -> List[Dict]:
    """Flat resistance + rising lows → LONG breakout."""
    signals: List[Dict] = []
    reported: set = set()
    ph_idx = ph.index.tolist()
    pl_idx = pl.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(ph_idx) - MIN_TOUCHES + 1):
        for num in range(MIN_TOUCHES, min(MIN_TOUCHES + 3, len(ph_idx) - k + 1)):
            grp = ph_idx[k: k + num]
            if len(grp) < MIN_TOUCHES:
                continue

            span = grp[-1] - grp[0]
            if not (config.MIN_PATTERN_BARS <= span <= config.MAX_PATTERN_BARS):
                continue

            grp_val = [ph[j] for j in grp]
            mean_r  = float(np.mean(grp_val))
            if max(abs(v - mean_r) / mean_r for v in grp_val) > config.PATTERN_TOLERANCE:
                continue

            i_start, i_end = grp[0], grp[-1]
            lows_in = [(j, pl[j]) for j in pl_idx if i_start <= j <= i_end]
            if len(lows_in) < MIN_TOUCHES:
                continue

            lx = [j for j, _ in lows_in]
            ly = [v for _, v in lows_in]
            if np.polyfit(lx, ly, 1)[0] <= 0:
                continue  # lows not rising

            for j in range(i_end + 1, min(i_end + config.BREAKOUT_WINDOW + 1, len(df))):
                if j in reported:
                    continue
                vol_ok = (not config.VOLUME_FILTER or
                          df['volume'].iloc[j] >= avg_vol.iloc[j])
                if df['close'].iloc[j] > mean_r and vol_ok:
                    signals.append({'bar_index': j, 'pattern': 'ascending_triangle',
                                     'direction': 'long', 'key_level': mean_r})
                    reported.add(j)
                    break

    return signals


def detect_descending_triangle(df: pd.DataFrame,
                                ph: pd.Series,
                                pl: pd.Series) -> List[Dict]:
    """Flat support + falling highs → SHORT breakdown."""
    signals: List[Dict] = []
    reported: set = set()
    ph_idx = ph.index.tolist()
    pl_idx = pl.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(pl_idx) - MIN_TOUCHES + 1):
        for num in range(MIN_TOUCHES, min(MIN_TOUCHES + 3, len(pl_idx) - k + 1)):
            grp = pl_idx[k: k + num]
            if len(grp) < MIN_TOUCHES:
                continue

            span = grp[-1] - grp[0]
            if not (config.MIN_PATTERN_BARS <= span <= config.MAX_PATTERN_BARS):
                continue

            grp_val = [pl[j] for j in grp]
            mean_s  = float(np.mean(grp_val))
            if max(abs(v - mean_s) / mean_s for v in grp_val) > config.PATTERN_TOLERANCE:
                continue

            i_start, i_end = grp[0], grp[-1]
            highs_in = [(j, ph[j]) for j in ph_idx if i_start <= j <= i_end]
            if len(highs_in) < MIN_TOUCHES:
                continue

            hx = [j for j, _ in highs_in]
            hy = [v for _, v in highs_in]
            if np.polyfit(hx, hy, 1)[0] >= 0:
                continue  # highs not falling

            for j in range(i_end + 1, min(i_end + config.BREAKOUT_WINDOW + 1, len(df))):
                if j in reported:
                    continue
                vol_ok = (not config.VOLUME_FILTER or
                          df['volume'].iloc[j] >= avg_vol.iloc[j])
                if df['close'].iloc[j] < mean_s and vol_ok:
                    signals.append({'bar_index': j, 'pattern': 'descending_triangle',
                                     'direction': 'short', 'key_level': mean_s})
                    reported.add(j)
                    break

    return signals