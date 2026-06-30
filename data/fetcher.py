import os
import logging
import time
from datetime import datetime, timedelta, timezone

import ccxt
import pandas as pd
from tqdm import tqdm

import config

log = logging.getLogger(__name__)
_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']


def _make_exchange() -> ccxt.Exchange:
    ex = getattr(ccxt, config.EXCHANGE)({'enableRateLimit': True})
    ex.load_markets()
    return ex


def top_pairs(n: int = config.TOP_N_PAIRS) -> list:
    """Return top-N USDT spot pairs ranked by 24h quote volume."""
    log.info('Loading ticker data to rank pairs ...')
    ex = _make_exchange()
    tickers = ex.fetch_tickers()
    usdt_pairs = {
        sym: t for sym, t in tickers.items()
        if (
            sym.endswith(f'/{config.QUOTE_CURRENCY}')
            and ':' not in sym
            and t.get('quoteVolume') is not None
            and t['quoteVolume'] > 0
        )
    }
    ranked = sorted(usdt_pairs.items(),
                    key=lambda kv: kv[1]['quoteVolume'], reverse=True)
    selected = [sym for sym, _ in ranked[:n]]
    log.info(f'Top {n} pairs: {selected}')
    return selected


def fetch_ohlcv(symbol: str, days: int = config.LOOKBACK_DAYS) -> pd.DataFrame:
    """Download OHLCV history. Uses CSV cache if fresh (< 12 h old)."""
    os.makedirs(config.DATA_CACHE_DIR, exist_ok=True)
    safe = symbol.replace('/', '_')
    path = os.path.join(config.DATA_CACHE_DIR,
                        f'{safe}_{config.TIMEFRAME}_{days}d.csv')

    if os.path.exists(path):
        age = datetime.now(tz=timezone.utc) - datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc)
        if age < timedelta(hours=12):
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            log.info(f'[cache] {symbol}: {len(df):,} rows')
            return df

    ex = _make_exchange()
    now_ms   = ex.milliseconds()
    start_ms = now_ms - days * 86_400_000

    rows = []
    since = start_ms
    with tqdm(total=days * 288, desc=f'Fetching {symbol}',
              unit='candle', leave=False) as pbar:
        while since < now_ms:
            try:
                batch = ex.fetch_ohlcv(symbol, config.TIMEFRAME,
                                       since=since, limit=1000)
            except ccxt.NetworkError as e:
                log.warning(f'Network error, retrying: {e}')
                time.sleep(5)
                continue
            except ccxt.ExchangeError as e:
                log.error(f'Exchange error for {symbol}: {e}')
                break
            if not batch:
                break
            rows.extend(batch)
            since = batch[-1][0] + 1
            pbar.update(len(batch))
            if batch[-1][0] >= now_ms:
                break

    if not rows:
        log.warning(f'{symbol}: no data returned.')
        return pd.DataFrame(columns=_COLUMNS[1:])

    df = pd.DataFrame(rows, columns=_COLUMNS)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('timestamp', inplace=True)
    df = df[~df.index.duplicated()].sort_index()
    df.to_csv(path)
    log.info(f'[fetch] {symbol}: {len(df):,} rows saved.')
    return df