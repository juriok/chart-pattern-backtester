from typing import List, Dict
import pandas as pd
import config
from patterns.utils import rolling_avg_volume, line_val


def detect_hs(df: pd.DataFrame, ph: pd.Series, pl: pd.Series) -> List[Dict]:
    """Left shoulder + head + right shoulder, sloped neckline → SHORT breakdown."""
    signals: List[Dict] = []
    reported: set = set()
    ph_idx = ph.index.tolist()
    pl_idx = pl.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(ph_idx) - 2):
        i1, i2, i3 = ph_idx[k], ph_idx[k + 1], ph_idx[k + 2]
        p1, p2, p3 = ph[i1], ph[i2], ph[i3]

        span = i3 - i1
        if not (config.MIN_PATTERN_BARS <= span <= config.MAX_PATTERN_BARS):
            continue

        # Head must stand out clearly above both shoulders.
        if (p2 - p1) / p1 < config.MIN_HEAD_PROMINENCE:
            continue
        if (p2 - p3) / p3 < config.MIN_HEAD_PROMINENCE:
            continue

        # Shoulders roughly symmetric in height.
        mean_sh = (p1 + p3) / 2
        if abs(p1 - p3) / mean_sh > config.PATTERN_TOLERANCE:
            continue

        # The two troughs either side of the head define the (sloped) neckline.
        left_troughs  = [j for j in pl_idx if i1 < j < i2]
        right_troughs = [j for j in pl_idx if i2 < j < i3]
        if not left_troughs or not right_troughs:
            continue

        n1 = min(left_troughs,  key=lambda j: pl[j])
        n2 = min(right_troughs, key=lambda j: pl[j])

        for j in range(i3 + 1, min(i3 + config.BREAKOUT_WINDOW + 1, len(df))):
            if j in reported:
                continue
            neckline = line_val(n1, pl[n1], n2, pl[n2], j)
            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[j] >= avg_vol.iloc[j])
            if df['close'].iloc[j] < neckline and vol_ok:
                signals.append({'bar_index': j, 'pattern': 'head_and_shoulders',
                                 'direction': 'short', 'key_level': float(neckline)})
                reported.add(j)
                break

    return signals


def detect_inverse_hs(df: pd.DataFrame, ph: pd.Series, pl: pd.Series) -> List[Dict]:
    """Mirror of detect_hs on pivot lows → LONG breakout."""
    signals: List[Dict] = []
    reported: set = set()
    ph_idx = ph.index.tolist()
    pl_idx = pl.index.tolist()
    avg_vol = rolling_avg_volume(df)

    for k in range(len(pl_idx) - 2):
        i1, i2, i3 = pl_idx[k], pl_idx[k + 1], pl_idx[k + 2]
        p1, p2, p3 = pl[i1], pl[i2], pl[i3]

        span = i3 - i1
        if not (config.MIN_PATTERN_BARS <= span <= config.MAX_PATTERN_BARS):
            continue

        # Head must stand out clearly below both shoulders.
        if (p1 - p2) / p1 < config.MIN_HEAD_PROMINENCE:
            continue
        if (p3 - p2) / p3 < config.MIN_HEAD_PROMINENCE:
            continue

        mean_sh = (p1 + p3) / 2
        if abs(p1 - p3) / mean_sh > config.PATTERN_TOLERANCE:
            continue

        left_peaks  = [j for j in ph_idx if i1 < j < i2]
        right_peaks = [j for j in ph_idx if i2 < j < i3]
        if not left_peaks or not right_peaks:
            continue

        n1 = max(left_peaks,  key=lambda j: ph[j])
        n2 = max(right_peaks, key=lambda j: ph[j])

        for j in range(i3 + 1, min(i3 + config.BREAKOUT_WINDOW + 1, len(df))):
            if j in reported:
                continue
            neckline = line_val(n1, ph[n1], n2, ph[n2], j)
            vol_ok = (not config.VOLUME_FILTER or
                      df['volume'].iloc[j] >= avg_vol.iloc[j])
            if df['close'].iloc[j] > neckline and vol_ok:
                signals.append({'bar_index': j, 'pattern': 'inverse_head_and_shoulders',
                                 'direction': 'long', 'key_level': float(neckline)})
                reported.add(j)
                break

    return signals
