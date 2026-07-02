"""Shared-capital portfolio backtest across many symbols.

The per-symbol BacktestEngine gives every symbol its own isolated capital silo,
which leaves most capital idle at any moment (a symbol's engine skips signals
while its silo is busy, even though the pool as a whole has room). This engine
runs ONE equity pool over a global, timestamp-ordered event stream:

  - every trade risks RISK_PER_TRADE of *current pool equity* (compounding),
  - per-symbol slots (MAX_CONCURRENT_POSITIONS) still apply,
  - plus two portfolio-wide guards: MAX_PORTFOLIO_POSITIONS open trades total,
    and total open notional <= MAX_PORTFOLIO_NOTIONAL_PCT x equity (a real
    leverage cap, which the silo model never had).

Within one timestamp, all exits (all symbols) settle before any entry is
considered, so freed slots/capital are immediately reusable; entry order within
a timestamp follows the symbol iteration order (deterministic).
"""
from typing import List, Dict, Optional, Tuple
import numpy as np
import config
from backtest.engine import Trade, _bar_hours


class PortfolioEngine:
    def __init__(self, data: Dict[str, Tuple[object, List[Dict]]]):
        """data: {symbol: (ohlcv_df, signals)} — signals as from detect_all()."""
        self.data   = data
        self.equity = config.INITIAL_CAPITAL

    def run(self) -> List[Trade]:
        # signal lookup per (symbol, bar) and the global timestamp event stream
        sigs_at: Dict[str, Dict[int, List[Dict]]] = {}
        events:  Dict[object, List[Tuple[str, int]]] = {}
        for sym, (df, sigs) in self.data.items():
            d: Dict[int, List[Dict]] = {}
            for s in sigs:
                d.setdefault(s['bar_index'], []).append(s)
            sigs_at[sym] = d
            for i, ts in enumerate(df.index):
                events.setdefault(ts, []).append((sym, i))

        trades:   List[Trade] = []
        open_pos: Dict[str, List[Trade]] = {sym: [] for sym in self.data}
        pending:  Dict[str, Dict[int, List[Dict]]] = {sym: {} for sym in self.data}

        max_sym      = getattr(config, 'MAX_CONCURRENT_POSITIONS', 1)
        max_port     = getattr(config, 'MAX_PORTFOLIO_POSITIONS', 10)
        max_notional = getattr(config, 'MAX_PORTFOLIO_NOTIONAL_PCT', 2.0)

        for ts in sorted(events):
            bars = events[ts]

            # 1. Exits first, across ALL symbols, so freed capital/slots are
            #    available to any entry at this same timestamp.
            for sym, i in bars:
                df = self.data[sym][0]
                open_pos[sym] = [p for p in open_pos[sym]
                                 if self._check_exit(p, df, i, trades) is not None]

            # 2. Entries scheduled for this bar (signal fired on previous bar).
            for sym, i in bars:
                waiting = pending[sym].pop(i, None)
                if not waiting:
                    continue
                df = self.data[sym][0]
                for sig in waiting:
                    if len(open_pos[sym]) >= max_sym:
                        continue
                    if sum(len(v) for v in open_pos.values()) >= max_port:
                        continue
                    held = sum(p.entry_price * p.qty
                               for v in open_pos.values() for p in v)
                    budget = max_notional * self.equity - held
                    trade  = self._open_trade(sym, df, sig, i, budget)
                    if trade is not None:
                        open_pos[sym].append(trade)

            # 3. Signals generated at this bar enter at the NEXT bar's open.
            for sym, i in bars:
                sigs = sigs_at[sym].get(i)
                if sigs and i + 1 < len(self.data[sym][0]):
                    pending[sym].setdefault(i + 1, []).extend(sigs)

        # Force-close whatever is still open at each symbol's final bar.
        for sym, poss in open_pos.items():
            df   = self.data[sym][0]
            last = len(df) - 1
            for pos in poss:
                ep = self._slip(float(df['close'].iloc[last]),
                                pos.direction, exit=True)
                self._close(pos, df, last, ep, 'timeout', trades)

        return trades

    # ── Private helpers (same trade mechanics as BacktestEngine, pool-sized) ──

    def _open_trade(self, sym: str, df, sig: Dict, entry_bar: int,
                    notional_budget: float) -> Optional[Trade]:
        if self.equity <= 0:
            return None

        raw   = float(df['open'].iloc[entry_bar])
        entry = self._slip(raw, sig['direction'], exit=False)
        atr   = sig['atr']

        if not np.isfinite(atr) or atr <= 0:
            return None
        if atr / entry < config.MIN_ATR_PCT:
            return None

        if sig['direction'] == 'long':
            sl, tp = entry - config.SL_ATR_MULT * atr, entry + config.TP_ATR_MULT * atr
        else:
            sl, tp = entry + config.SL_ATR_MULT * atr, entry - config.TP_ATR_MULT * atr

        risk = abs(entry - sl)
        if risk < 1e-10:
            return None

        qty = (self.equity * config.RISK_PER_TRADE) / risk
        qty = min(qty, (self.equity * config.MAX_POSITION_PCT) / entry)

        # Portfolio leverage cap: shrink into whatever notional room is left;
        # skip if there's no meaningful room (< 1% of equity).
        if entry * qty > notional_budget:
            qty = notional_budget / entry
        if qty * entry < 0.01 * self.equity:
            return None

        return Trade(symbol=sym, pattern=sig['pattern'],
                     direction=sig['direction'], entry_bar=entry_bar,
                     entry_price=entry, sl=sl, tp=tp, qty=qty,
                     entry_ts=df.index[entry_bar])

    def _check_exit(self, pos: Trade, df, i: int,
                    trades: List[Trade]) -> Optional[Trade]:
        row  = df.iloc[i]
        high = float(row['high'])
        low  = float(row['low'])
        open_ = float(row['open'])

        if pos.direction == 'long':
            sl_hit = low  <= pos.sl
            tp_hit = high >= pos.tp
        else:
            sl_hit = high >= pos.sl
            tp_hit = low  <= pos.tp

        if sl_hit and tp_hit:
            if pos.direction == 'long' and open_ >= pos.tp:
                sl_hit = False
            elif pos.direction == 'short' and open_ <= pos.tp:
                sl_hit = False
            else:
                tp_hit = False   # conservative: assume SL

        if tp_hit:
            self._close(pos, df, i, self._slip(pos.tp, pos.direction, exit=True),
                        'tp', trades)
            return None
        if sl_hit:
            self._close(pos, df, i, self._slip(pos.sl, pos.direction, exit=True),
                        'sl', trades)
            return None
        if (i - pos.entry_bar) >= config.MAX_TRADE_BARS:
            self._close(pos, df, i,
                        self._slip(float(row['close']), pos.direction, exit=True),
                        'timeout', trades)
            return None
        return pos

    def _close(self, pos: Trade, df, exit_bar: int, exit_price: float,
               result: str, trades: List[Trade]) -> None:
        if pos.direction == 'long':
            gross = (exit_price - pos.entry_price) * pos.qty
        else:
            gross = (pos.entry_price - exit_price) * pos.qty

        commission = (pos.entry_price + exit_price) * pos.qty * config.COMMISSION

        frate   = getattr(config, 'FUNDING_RATE_8H', 0.0)
        hours   = (exit_bar - pos.entry_bar) * _bar_hours()
        funding = pos.entry_price * pos.qty * frate * (hours / 8.0)
        if pos.direction == 'long':
            funding = -funding

        pos.exit_bar   = exit_bar
        pos.exit_price = exit_price
        pos.exit_ts    = df.index[exit_bar]
        pos.pnl        = gross - commission + funding
        pos.result     = result
        trades.append(pos)
        self.equity   += pos.pnl

    @staticmethod
    def _slip(price: float, direction: str, exit: bool) -> float:
        s = config.SLIPPAGE
        if direction == 'long':
            return price * (1 + s) if not exit else price * (1 - s)
        else:
            return price * (1 - s) if not exit else price * (1 + s)
