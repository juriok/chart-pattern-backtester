from typing import List, Dict
import pandas as pd
import config
from patterns.utils import get_pivot_highs, get_pivot_lows, compute_atr
from patterns.head_and_shoulders import detect_hs, detect_inverse_hs
from patterns.double_patterns   import detect_double_top, detect_double_bottom
from patterns.flags              import detect_bull_flag, detect_bear_flag
from patterns.triangles          import detect_ascending_triangle, detect_descending_triangle


def detect_all(df: pd.DataFrame) -> List[Dict]:
    """Run every enabled pattern detector and return a time-sorted signal list.

    Detectors named in config.DISABLED_PATTERNS are skipped entirely — used to
    drop patterns with proven negative out-of-sample expectancy (see config)."""
    ph  = get_pivot_highs(df, config.PIVOT_ORDER)
    pl  = get_pivot_lows (df, config.PIVOT_ORDER)
    atr = compute_atr    (df, config.ATR_PERIOD)

    detectors = {
        'head_and_shoulders'        : lambda: detect_hs                  (df, ph, pl),
        'inverse_head_and_shoulders': lambda: detect_inverse_hs          (df, ph, pl),
        'double_top'                : lambda: detect_double_top          (df, ph, pl),
        'double_bottom'             : lambda: detect_double_bottom       (df, ph, pl),
        'bull_flag'                 : lambda: detect_bull_flag           (df),
        'bear_flag'                 : lambda: detect_bear_flag           (df),
        'ascending_triangle'        : lambda: detect_ascending_triangle  (df, ph, pl),
        'descending_triangle'       : lambda: detect_descending_triangle (df, ph, pl),
    }
    disabled = getattr(config, 'DISABLED_PATTERNS', set()) or set()

    signals: List[Dict] = []
    for name, detect in detectors.items():
        if name not in disabled:
            signals += detect()

    for sig in signals:
        i = sig['bar_index']
        sig['atr'] = float(atr.iloc[i] if i < len(atr) else atr.iloc[-1])

    signals.sort(key=lambda s: s['bar_index'])
    return signals