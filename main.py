import logging
import sys
from typing import List

from tqdm import tqdm

import config
from data.fetcher import top_pairs, fetch_ohlcv
from patterns.detector import detect_all
from backtest.engine import BacktestEngine, Trade
from report.reporter import save_report

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%H:%M:%S',
    stream=sys.stdout,
)
log = logging.getLogger(__name__)


def run_pair(symbol: str) -> List[Trade]:
    log.info(f'── {symbol} ──────────────────────────────────')
    df = fetch_ohlcv(symbol, days=config.LOOKBACK_DAYS)

    if len(df) < 500:
        log.warning(f'{symbol}: only {len(df)} rows, skipping.')
        return []

    signals = detect_all(df)
    log.info(f'{symbol}: {len(signals)} signals detected.')

    trades = BacktestEngine(symbol=symbol, df=df, signals=signals).run()
    log.info(f'{symbol}: {len(trades)} trades completed.')

    if trades:
        save_report(trades, label=symbol.replace('/', '_'))

    return trades


def main():
    pairs = top_pairs(config.TOP_N_PAIRS)

    all_trades: List[Trade] = []
    for symbol in tqdm(pairs, desc='Pairs', unit='pair'):
        all_trades.extend(run_pair(symbol))

    if all_trades:
        # NOTE: every symbol is fetched for the same LOOKBACK_DAYS/TIMEFRAME at
        # roughly the same wall-clock time, so entry_bar is a valid chronological
        # proxy across symbols. Sorting here makes the *combined* equity curve
        # actually time-ordered instead of "all of symbol A, then all of symbol B".
        all_trades.sort(key=lambda t: t.entry_bar)

        # Each symbol is backtested with its own independent INITIAL_CAPITAL
        # (see README "Known limitations" — this isn't a shared portfolio
        # pool). The combined report's % stats (drawdown, Sharpe) are only
        # meaningful relative to the TRUE total capital that was actually in
        # play, not a single symbol's $10k — so scale the capital base by how
        # many distinct symbols actually produced trades.
        n_symbols = len({t.symbol for t in all_trades})
        combined_capital_base = config.INITIAL_CAPITAL * n_symbols

        save_report(all_trades, label='combined', capital_base=combined_capital_base)
    else:
        log.warning('No trades generated across all pairs.')


if __name__ == '__main__':
    main()
