from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
import config


@dataclass
class Trade:
    symbol:      str
    pattern:     str
    direction:   str
    entry_bar:   int
    entry_price: float
    sl:          float
    tp:          float
    qty:         float
    exit_bar:    int   = -1
    exit_price:  float = 0.0
    pnl:         float = 0.0
    result:      str   = ''   # 'tp' | 'sl' | 'timeout'


class BacktestEngine:
    def __init__(self, symbol: str, df, signals: List[Dict]):
        self.symbol  = symbol
        self.df      = df
        self.signals = sorted(signals, key=lambda s: s['bar_index'])
        self.equity  = config.INITIAL_CAPITAL

    def run(self) -> List[Trade]:
        trades: List[Trade] = []
        open_pos: Optional[Trade] = None
        sig_ptr = 0
        n = len(self.df)

        for i in range(n):
            # ── 1. Check exit conditions for open position ───────────────
            if open_pos is not None:
                open_pos = self._check_exit(open_pos, i, trades)

            # ── 2. Consume signals generated at bar i (enter at bar i+1) ─
            while (sig_ptr < len(self.signals) and
                   self.signals[sig_ptr]['bar_index'] == i):
                sig = self.signals[sig_ptr]
                sig_ptr += 1

                if open_pos is not None:
                    continue   # already in a position

                entry_bar = i + 1
                if entry_bar >= n:
                    continue

                trade = self._open_trade(sig, entry_bar)
                if trade is not None:
                    open_pos = trade

        # ── Force-close any remaining position at last bar ───────────────
        if open_pos is not None:
            last       = n - 1
            exit_price = self._slip(float(self.df['close'].iloc[last]),
                                    open_pos.direction, exit=True)
            self._close(open_pos, last, exit_price, 'timeout', trades)

        return trades

    # ── Private helpers ───────────────────────────────────────────────────

    def _open_trade(self, sig: Dict, entry_bar: int) -> Optional[Trade]:
        # Account wiped out by prior losses — no capital left to risk.
        # Sizing is computed off INITIAL_CAPITAL (see Known limitations in
        # README), so without this guard the simulation would keep "trading"
        # past zero equity, which is not something that can happen for real.
        if self.equity <= 0:
            return None

        raw    = float(self.df['open'].iloc[entry_bar])
        entry  = self._slip(raw, sig['direction'], exit=False)
        atr    = sig['atr']

        if not np.isfinite(atr) or atr <= 0:
            return None

        # Near-zero-volatility instruments (e.g. stablecoin pairs) produce a
        # microscopic ATR, which blows up risk-based position sizing below.
        # If the instrument isn't moving meaningfully, ATR-based sizing isn't
        # a meaningful concept for it — skip rather than size a trade off noise.
        if atr / entry < config.MIN_ATR_PCT:
            return None

        if sig['direction'] == 'long':
            sl, tp = entry - config.SL_ATR_MULT * atr, entry + config.TP_ATR_MULT * atr
        else:
            sl, tp = entry + config.SL_ATR_MULT * atr, entry - config.TP_ATR_MULT * atr

        risk = abs(entry - sl)
        if risk < 1e-10:
            return None

        qty = (config.INITIAL_CAPITAL * config.RISK_PER_TRADE) / risk

        # Hard safety cap: even with a legitimate ATR, never let a single
        # trade's notional exposure exceed MAX_POSITION_PCT of capital.
        # This is a backstop against any other edge case that could inflate
        # qty, not just the near-zero-ATR case above.
        max_qty = (config.INITIAL_CAPITAL * config.MAX_POSITION_PCT) / entry
        qty = min(qty, max_qty)

        return Trade(symbol=self.symbol, pattern=sig['pattern'],
                     direction=sig['direction'], entry_bar=entry_bar,
                     entry_price=entry, sl=sl, tp=tp, qty=qty)

    def _check_exit(self, pos: Trade, i: int,
                    trades: List[Trade]) -> Optional[Trade]:
        row  = self.df.iloc[i]
        high = float(row['high'])
        low  = float(row['low'])
        open_= float(row['open'])

        if pos.direction == 'long':
            sl_hit = low  <= pos.sl
            tp_hit = high >= pos.tp
        else:
            sl_hit = high >= pos.sl
            tp_hit = low  <= pos.tp

        # Both hit in same candle → check open for gap-favour
        if sl_hit and tp_hit:
            if pos.direction == 'long'  and open_ >= pos.tp:
                sl_hit = False
            elif pos.direction == 'short' and open_ <= pos.tp:
                sl_hit = False
            else:
                tp_hit = False   # conservative: assume SL

        if tp_hit:
            ep = self._slip(pos.tp, pos.direction, exit=True)
            self._close(pos, i, ep, 'tp', trades)
            return None

        if sl_hit:
            ep = self._slip(pos.sl, pos.direction, exit=True)
            self._close(pos, i, ep, 'sl', trades)
            return None

        if (i - pos.entry_bar) >= config.MAX_TRADE_BARS:
            ep = self._slip(float(row['close']), pos.direction, exit=True)
            self._close(pos, i, ep, 'timeout', trades)
            return None

        return pos

    def _close(self, pos: Trade, exit_bar: int, exit_price: float,
               result: str, trades: List[Trade]) -> None:
        if pos.direction == 'long':
            gross = (exit_price - pos.entry_price) * pos.qty
        else:
            gross = (pos.entry_price - exit_price) * pos.qty

        commission   = (pos.entry_price + exit_price) * pos.qty * config.COMMISSION
        pos.exit_bar   = exit_bar
        pos.exit_price = exit_price
        pos.pnl        = gross - commission
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