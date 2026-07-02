import logging
import os
import sys
from typing import Dict, List, Tuple

import pandas as pd
from tqdm import tqdm

import config
from data.fetcher import top_pairs, fetch_ohlcv
from patterns.detector import detect_all
from backtest.engine import Trade
from backtest.portfolio import PortfolioEngine
from report.reporter import save_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def load_universe() -> Dict[str, Tuple[pd.DataFrame, List[dict]]]:
    """Fetch data and detect signals for every tradeable pair."""
    pairs = top_pairs(config.TOP_N_PAIRS)
    data: Dict[str, Tuple[pd.DataFrame, List[dict]]] = {}

    for symbol in tqdm(pairs, desc='Pairs', unit='pair'):
        df = fetch_ohlcv(symbol, days=config.LOOKBACK_DAYS)
        if len(df) < 500:
            log.warning(f'{symbol}: only {len(df)} rows, skipping.')
            continue
        signals = detect_all(df)
        log.info(f'{symbol}: {len(signals)} signals detected.')
        data[symbol] = (df, signals)

    return data


def main():
    data = load_universe()
    if not data:
        log.warning('No tradeable pairs found.')
        return

    # ONE shared capital pool across all symbols (see backtest/portfolio.py).
    # Unlike the old per-symbol silo model, capital freed by any symbol's exit
    # is immediately available to any other symbol's entry, and portfolio-wide
    # position/leverage caps actually bind.
    trades = PortfolioEngine(data).run()
    log.info(f'{len(trades)} trades completed across {len(data)} symbols.')

    if not trades:
        log.warning('No trades generated.')
        return

    # entry_ts is exact cross-symbol chronology (set by the engine), so the
    # combined equity curve is genuinely time-ordered.
    trades.sort(key=lambda t: t.entry_ts)

    # Quiet per-symbol trade logs (no console spam), full report for the pool.
    os.makedirs(config.REPORT_DIR, exist_ok=True)
    by_sym: Dict[str, List[Trade]] = {}
    for t in trades:
        by_sym.setdefault(t.symbol, []).append(t)
    for sym, sym_trades in by_sym.items():
        path = os.path.join(config.REPORT_DIR,
                            f"trades_{sym.replace('/', '_')}.csv")
        pd.DataFrame([vars(t) for t in sym_trades]).to_csv(path, index=False)

    save_report(trades, label='portfolio', capital_base=config.INITIAL_CAPITAL)


if __name__ == '__main__':
    main()
