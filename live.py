"""Live paper-trading daemon.

Runs the exact backtest strategy forward on real closed 4h candles:
same detectors, same config, same portfolio rules (one equity pool,
0.5% risk per trade, per-symbol slots, portfolio position + leverage caps),
same cost model (taker commission, slippage, flat funding accrual).

No orders are sent anywhere — fills are simulated ("paper") and logged, so
the output is a forward test to compare against backtest expectations.

Usage:
    python live.py           # daemon: wakes on every 4h candle close
    python live.py --once    # process the latest closed candle, then exit

State (survives restarts) lives in state/paper_state.json; every closed trade
is appended to state/paper_trades.csv. Optional Telegram alerts if
TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars are set.
"""
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd

import config
from data.fetcher import _make_exchange, top_pairs
from patterns.detector import detect_all
from backtest.engine import _bar_hours

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)-8s  %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
)
log = logging.getLogger('live')

STATE_DIR   = 'state'
STATE_PATH  = os.path.join(STATE_DIR, 'paper_state.json')
TRADES_PATH = os.path.join(STATE_DIR, 'paper_trades.csv')
DETECT_BARS = 300          # candles fetched per symbol per cycle (detection window)
BAR_MS      = int(_bar_hours() * 3_600_000)


# ── State ────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        'equity'      : config.INITIAL_CAPITAL,
        'peak_equity' : config.INITIAL_CAPITAL,
        'positions'   : [],     # open paper positions
        'handled'     : [],     # signal keys already acted on (dedup across cycles)
        'last_cycle'  : None,
    }


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_PATH)


def append_trade(row: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    header = not os.path.exists(TRADES_PATH)
    pd.DataFrame([row]).to_csv(TRADES_PATH, mode='a', header=header, index=False)


# ── Alerts ───────────────────────────────────────────────────────────────────

def notify(msg: str) -> None:
    log.info(msg)
    token = os.environ.get('TELEGRAM_BOT_TOKEN')
    chat  = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        return
    try:
        import requests
        requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                      json={'chat_id': chat, 'text': msg}, timeout=10)
    except Exception as e:                                   # alerts must never kill the loop
        log.warning(f'Telegram alert failed: {e}')


# ── Market data ──────────────────────────────────────────────────────────────

def fetch_closed_candles(ex, symbol: str, limit: int = DETECT_BARS) -> pd.DataFrame:
    """Fetch the most recent CLOSED candles (drops the in-progress one)."""
    rows = ex.fetch_ohlcv(symbol, config.TIMEFRAME, limit=limit + 1)
    df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    now_ms = ex.milliseconds()
    df = df[df['timestamp'] + BAR_MS <= now_ms]              # keep fully closed bars only
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    return df.set_index('timestamp')


# ── Paper trading mechanics (mirrors backtest/portfolio.py exactly) ──────────

def _slip(price: float, direction: str, exit: bool) -> float:
    s = config.SLIPPAGE
    if direction == 'long':
        return price * (1 + s) if not exit else price * (1 - s)
    return price * (1 - s) if not exit else price * (1 + s)


def close_position(state: dict, pos: dict, exit_price: float, result: str,
                   ts) -> None:
    if pos['direction'] == 'long':
        gross = (exit_price - pos['entry_price']) * pos['qty']
    else:
        gross = (pos['entry_price'] - exit_price) * pos['qty']

    commission = (pos['entry_price'] + exit_price) * pos['qty'] * config.COMMISSION

    frate   = getattr(config, 'FUNDING_RATE_8H', 0.0)
    hours   = pos['bars_held'] * _bar_hours()
    funding = pos['entry_price'] * pos['qty'] * frate * (hours / 8.0)
    if pos['direction'] == 'long':
        funding = -funding

    pnl = gross - commission + funding
    state['equity'] += pnl
    state['peak_equity'] = max(state['peak_equity'], state['equity'])
    dd = state['equity'] / state['peak_equity'] - 1

    row = {**pos, 'exit_price': exit_price, 'exit_ts': str(ts),
           'pnl': round(pnl, 2), 'result': result,
           'equity_after': round(state['equity'], 2)}
    append_trade(row)
    notify(f"CLOSE {pos['symbol']} {pos['direction']} [{pos['pattern']}] -> {result.upper()} "
           f"pnl {pnl:+,.2f} | equity {state['equity']:,.2f} (DD {100*dd:.1f}%)")


def check_exits(state: dict, candles: dict) -> None:
    """Evaluate the just-closed candle of each symbol against SL/TP/timeout."""
    remaining = []
    for pos in state['positions']:
        df = candles.get(pos['symbol'])
        if df is None or df.empty:
            remaining.append(pos)               # no fresh data — keep and retry next cycle
            continue
        last = df.iloc[-1]
        ts   = df.index[-1]
        if str(ts) == pos.get('last_seen_bar'):
            remaining.append(pos)               # candle already processed
            continue
        pos['bars_held']    = pos.get('bars_held', 0) + 1
        pos['last_seen_bar'] = str(ts)

        high, low, open_ = float(last['high']), float(last['low']), float(last['open'])
        if pos['direction'] == 'long':
            sl_hit, tp_hit = low <= pos['sl'], high >= pos['tp']
        else:
            sl_hit, tp_hit = high >= pos['sl'], low <= pos['tp']

        if sl_hit and tp_hit:                   # both in one candle → same rule as backtest
            if pos['direction'] == 'long' and open_ >= pos['tp']:
                sl_hit = False
            elif pos['direction'] == 'short' and open_ <= pos['tp']:
                sl_hit = False
            else:
                tp_hit = False                  # conservative: assume SL first

        if tp_hit:
            close_position(state, pos, _slip(pos['tp'], pos['direction'], True), 'tp', ts)
        elif sl_hit:
            close_position(state, pos, _slip(pos['sl'], pos['direction'], True), 'sl', ts)
        elif pos['bars_held'] >= config.MAX_TRADE_BARS:
            close_position(state, pos, _slip(float(last['close']), pos['direction'], True),
                           'timeout', ts)
        else:
            remaining.append(pos)
    state['positions'] = remaining


def try_entries(state: dict, candles: dict) -> None:
    """Act on signals whose bar_index is the just-closed candle."""
    max_sym      = getattr(config, 'MAX_CONCURRENT_POSITIONS', 1)
    max_port     = getattr(config, 'MAX_PORTFOLIO_POSITIONS', 10)
    max_notional = getattr(config, 'MAX_PORTFOLIO_NOTIONAL_PCT', 2.0)
    handled      = set(state['handled'])

    for sym, df in candles.items():
        if df is None or len(df) < 150:
            continue
        try:
            signals = detect_all(df)
        except Exception as e:
            log.warning(f'{sym}: detection failed: {e}')
            continue
        last_i = len(df) - 1
        for sig in signals:
            if sig['bar_index'] != last_i:
                continue
            key = f"{sym}|{sig['pattern']}|{df.index[last_i]}"
            if key in handled:
                continue
            handled.add(key)

            if state['equity'] <= 0:
                continue
            if sum(1 for p in state['positions'] if p['symbol'] == sym) >= max_sym:
                continue
            if len(state['positions']) >= max_port:
                continue

            atr = sig['atr']
            # paper fill: market entry right after candle close
            entry = _slip(float(df['close'].iloc[-1]), sig['direction'], False)
            if not atr or atr <= 0 or atr / entry < config.MIN_ATR_PCT:
                continue

            if sig['direction'] == 'long':
                sl, tp = entry - config.SL_ATR_MULT * atr, entry + config.TP_ATR_MULT * atr
            else:
                sl, tp = entry + config.SL_ATR_MULT * atr, entry - config.TP_ATR_MULT * atr

            risk = abs(entry - sl)
            if risk < 1e-10:
                continue
            qty = (state['equity'] * config.RISK_PER_TRADE) / risk
            qty = min(qty, (state['equity'] * config.MAX_POSITION_PCT) / entry)

            held   = sum(p['entry_price'] * p['qty'] for p in state['positions'])
            budget = max_notional * state['equity'] - held
            if entry * qty > budget:
                qty = budget / entry
            if qty * entry < 0.01 * state['equity']:
                continue

            pos = {'symbol': sym, 'pattern': sig['pattern'],
                   'direction': sig['direction'],
                   'entry_ts': str(df.index[last_i]), 'entry_price': entry,
                   'sl': sl, 'tp': tp, 'qty': qty,
                   'bars_held': 0, 'last_seen_bar': str(df.index[last_i])}
            state['positions'].append(pos)
            notify(f"OPEN {sym} {sig['direction']} [{sig['pattern']}] @ {entry:.6g} "
                   f"SL {sl:.6g} TP {tp:.6g} qty {qty:.6g} "
                   f"| {len(state['positions'])}/{max_port} slots")

    # prune dedup keys older than ~3 days so the list can't grow unboundedly
    cutoff = pd.Timestamp.now(tz=timezone.utc) - pd.Timedelta(days=3)
    state['handled'] = [k for k in handled
                        if pd.Timestamp(k.rsplit('|', 1)[1]) >= cutoff]


def run_cycle(state: dict) -> None:
    ex = _make_exchange()

    try:
        universe = top_pairs(config.TOP_N_PAIRS)
    except Exception as e:
        log.warning(f'top_pairs failed ({e}); reusing symbols of open positions only.')
        universe = []
    # always keep managing symbols we still hold, even if they left the top-N
    symbols = list(dict.fromkeys(universe + [p['symbol'] for p in state['positions']]))

    candles = {}
    for sym in symbols:
        try:
            candles[sym] = fetch_closed_candles(ex, sym)
        except Exception as e:
            log.warning(f'{sym}: fetch failed: {e}')

    check_exits(state, candles)     # exits release slots/capital first
    try_entries(state, candles)

    state['last_cycle'] = str(datetime.now(timezone.utc))
    save_state(state)

    dd = state['equity'] / state['peak_equity'] - 1
    log.info(f"cycle done: equity {state['equity']:,.2f} (DD {100*dd:.1f}%), "
             f"{len(state['positions'])} open, {len(candles)} symbols scanned")


def seconds_to_next_close() -> float:
    now_ms  = int(time.time() * 1000)
    next_ms = (now_ms // BAR_MS + 1) * BAR_MS
    return (next_ms - now_ms) / 1000 + 90        # +90s so the candle is finalized


def main():
    state = load_state()
    log.info(f"paper trading start: equity {state['equity']:,.2f}, "
             f"{len(state['positions'])} open positions")

    if '--once' in sys.argv:
        run_cycle(state)
        return

    while True:
        wait = seconds_to_next_close()
        log.info(f'sleeping {wait/3600:.2f}h until next {config.TIMEFRAME} close')
        time.sleep(wait)
        try:
            run_cycle(state)
        except Exception as e:
            log.exception(f'cycle failed: {e}')   # never die; retry next candle


if __name__ == '__main__':
    main()
