from typing import List, Dict
import pandas as pd
import config
from patterns.utils import get_pivot_highs, get_pivot_lows, compute_atr
from patterns.head_and_shoulders import detect_hs, detect_inverse_hs
from patterns.double_patterns   import detect_double_top, detect_double_bottom
from patterns.flags              import detect_bull_flag, detect_bear_flag
from patterns.triangles          import detect_ascending_triangle, detect_descending_triangle


def detect_all(df: pd.DataFrame) -> List[Dict]:
    """Run every pattern detector and return a time-sorted signal list."""
    ph  = get_pivot_highs(df, config.PIVOT_ORDER)
    pl  = get_pivot_lows (df, config.PIVOT_ORDER)
    atr = compute_atr    (df, config.ATR_PERIOD)

    signals: List[Dict] = []
    signals += detect_hs                  (df, ph, pl)
    signals += detect_inverse_hs          (df, ph, pl)
    signals += detect_double_top          (df, ph, pl)
    signals += detect_double_bottom       (df, ph, pl)
    signals += detect_bull_flag           (df)
    signals += detect_bear_flag           (df)
    signals += detect_ascending_triangle  (df, ph, pl)
    signals += detect_descending_triangle (df, ph, pl)

    for sig in signals:
        i = sig['bar_index']
        sig['atr'] = float(atr.iloc[i] if i < len(atr) else atr.iloc[-1])

    signals.sort(key=lambda s: s['bar_index'])
    return signals