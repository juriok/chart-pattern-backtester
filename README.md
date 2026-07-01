# Chart Pattern Backtester

Scans Binance USDT pairs for classic chart patterns (Head & Shoulders, Double Top/Bottom, Flags, Triangles), backtests them with ATR-based risk management, and reports win rate, profit factor, Sharpe, and max drawdown — with realistic commission and slippage baked into every trade.

## What this does

Pulls OHLCV history for the top-N Binance pairs by volume, runs 8 pattern detectors over each, and feeds every detected signal into a bar-by-bar backtest engine. Each trade is sized by fixed-fractional risk (% of capital per trade) with stop-loss and take-profit set as ATR multiples. Results are saved as a trade-log CSV and a 4-panel report chart (equity curve, win rate by pattern, P&L by pattern) per symbol, plus a combined report across all symbols.

## Status

🟢 All 8 detectors implemented and tested (Head & Shoulders, Inverse H&S, Double Top, Double Bottom, Bull Flag, Bear Flag, Ascending Triangle, Descending Triangle)
🟢 Backtest engine: slippage + commission modeled on both legs of every trade
🟢 Combined multi-symbol report is chronologically sorted (see *Known limitations* below for what that does and doesn't mean)
🟢 **Net profitable** on the default universe, Sharpe ~2.5 (see *Strategy & results*)

## Strategy & results

The single most important knob is **timeframe**. These chart-pattern breakouts have **no edge on 5-minute candles** — the moves they capture are the same order of magnitude as round-trip trading costs (~0.30%), and the strategy bled out to roughly **−88%** in testing. Worse than random, in fact: at a 2:1 target:stop, a driftless random entry hits its stop ~2/3 of the time (~33% win rate), and the 5m breakouts came in *below* that — they systematically precede reversals (false breakouts, a well-known low-timeframe phenomenon).

Push the same detectors up to **4-hour candles** and the picture flips: breakouts get real follow-through, the per-trade move becomes a large multiple of costs, and the strategy is **net profitable across a broad, diverse coin universe**. Four choices make it robust rather than curve-fit:

- **Trade the 4h timeframe** (`TIMEFRAME = '4h'`) — where breakouts have signal, not noise.
- **Wide stops, 2.5×ATR** (`SL_ATR_MULT = 2.5`) — a 1.5×ATR stop gets knocked out by ordinary 4h intrabar noise before the pattern can work. At 2.5×ATR the breakout win rate rises to ~53%.
- **EMA-smooth the price before locating pivots** (`PIVOT_SMOOTH_SPAN = 5`) — detecting turning points on a denoised series stops single-bar spikes from being mistaken for structural pivots. This one step lifts profit factor from ~1.18 to ~1.26 on the broad universe (stable across spans 4–6).
- **Model futures fees, not spot** (`COMMISSION = 0.00045`) — this is a long/short strategy (it shorts), so it runs on perpetual futures, where taker fees are ~0.045%/side, not the 0.10% of spot. *The edge does not depend on this:* at pessimistic spot fees (0.30% round trip) it is still profitable (PF ~1.26); futures just reflect where it actually trades.

How robust: across a 24-coin universe (majors, alts, even forex/gold pairs), **every cell** of the stop/target grid (SL ∈ [1.5, 3.0] × TP ∈ [2.0, 4.0]) is profitable. A real edge shows up everywhere in the neighborhood; a curve-fit shows up in one lucky cell. This one is everywhere.

Latest default run (top-20 by volume, 18 traded, futures fees):

| Metric | Value |
|---|---|
| Total P&L | **+$9,490** (on $180k base = 18 symbols × $10k) |
| Return (180 days) | +5.3% |
| Profit factor | 1.40 |
| Win rate | 52.7% |
| Max drawdown | −2.33% |
| Sharpe | 2.48 |
| Trades | 334 |
| Symbols profitable | 12 of 18 |

The improvement ladder is worth keeping in mind — each step is a deliberate, independently-validated change, not a joint fit:

| Config | Cost model | P&L | PF | Sharpe |
|---|---|---|---|---|
| Original (5m, 1.5×ATR stop) | spot | −$61.8k (−88%) | 0.42 | — |
| 4h + 2.5×ATR stops | spot | +$3.3k | 1.11 | 0.79 |
| + EMA-smoothed pivots | spot | ~+$4k | 1.26 | — |
| + futures fees (**shipped default**) | futures | **+$9.5k** | **1.40** | **2.48** |

One honest note about this specific 180-day sample: profit is spread across both directions (longs ≈ +$3.2k, shorts ≈ +$6.3k) — earlier, pre-smoothing versions leaned almost entirely on shorts, so the denoising also made the strategy noticeably *less* regime-dependent. Results are still a single full-period backtest, not walk-forward (see *Known limitations*).

## Setup

```bash
git clone <repo-url>
cd chart-pattern-backtester
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

No API keys needed — Binance OHLCV data is public.

## Running it

```bash
python main.py
```

This will:
1. Rank Binance USDT pairs by 24h volume and pick the top `TOP_N_PAIRS` (default 20, see `config.py`)
2. Download `LOOKBACK_DAYS` of `TIMEFRAME` candles per pair (default 180 days of 4h candles — see *Strategy & results* for why 4h, not 5m), cached locally for 12h so repeat runs are fast
3. Run all 8 pattern detectors on each pair
4. Backtest every signal and print a report to the console
5. Save a trade log (`reports/trades_<symbol>.csv`) and a chart (`reports/report_<symbol>.png`) per pair, plus combined versions across all pairs

First run downloads candle data (180 days × 4h × 20 pairs) — at 4h that's only ~1,080 candles per pair, so it's quick. Subsequent runs within 12h reuse the cache.

## How pattern detection works

Pivots (local highs/lows) are found with `scipy.signal.argrelextrema` over a configurable window (`PIVOT_ORDER`). Each detector looks for a specific geometric arrangement of pivots — e.g. Head & Shoulders requires three consecutive pivot highs where the middle one is prominently higher than both outer ones (`MIN_HEAD_PROMINENCE`) and the outer two are roughly symmetric (`PATTERN_TOLERANCE`), with the neckline computed as the (possibly sloped) line between the two troughs on either side of the head. A signal fires when price closes through the relevant level — neckline, valley, channel line, or resistance/support — within a bounded window after the pattern completes, with an optional volume confirmation filter.

## Project structure

```
chart-pattern-backtester/
├── config.py                          # all thresholds in one place
├── main.py                            # entry point
├── requirements.txt
├── data/
│   └── fetcher.py                     # Binance OHLCV fetch + local CSV cache
├── patterns/
│   ├── utils.py                       # pivot detection, ATR, line interpolation
│   ├── detector.py                    # runs all 8 detectors, attaches ATR to each signal
│   ├── head_and_shoulders.py          # H&S + inverse H&S
│   ├── double_patterns.py             # double top + double bottom
│   ├── flags.py                       # bull + bear flags
│   └── triangles.py                   # ascending + descending triangles
├── backtest/
│   └── engine.py                      # bar-by-bar simulation: entry, SL/TP, slippage, commission
└── report/
    └── reporter.py                    # stats, trade log CSV, equity curve chart
```

## Configuration

Every threshold lives in `config.py` — pivot sensitivity, pattern tolerance, ATR period, stop-loss/take-profit multiples, risk per trade, commission, and slippage. No magic numbers buried in the detector files.

Two safety knobs worth knowing about: `MIN_ATR_PCT` skips signals on instruments with near-zero volatility (e.g. stablecoin pairs), where ATR-based position sizing isn't a meaningful concept and would otherwise blow up. `MAX_POSITION_PCT` is a hard backstop that caps any single trade's notional exposure as a percentage of capital, regardless of how small the ATR-implied risk-per-unit is. Both exist because pure risk-based sizing (`capital × risk% ÷ stop-distance`) can imply absurd leverage whenever the stop distance is small relative to price — not just on stablecoins, it showed up even on BTC/USDT in testing (~5.7x implied leverage before the cap). Worth keeping in mind if you tune `SL_ATR_MULT` down or trade lower-volatility pairs.

On top of that, the engine tracks running equity and stops opening new trades once it's exhausted (`self.equity <= 0`). Since position sizing is computed off `INITIAL_CAPITAL`, not current equity (see below), a strategy with negative expectancy run over thousands of signals would otherwise keep "trading" past zero — which can't happen for a real account. With this guard, a wiped-out backtest correctly stops near -100% drawdown instead of continuing into nonsensical negative-equity territory.

## Known limitations

These are deliberate simplifications, not bugs — worth knowing before reading too much into the numbers:

- **Combined report capital handling.** The combined report across all symbols treats each symbol as if it had its own independent starting capital (`INITIAL_CAPITAL` per symbol, not split across them) — running with N symbols implicitly assumes capital for N simultaneous independent positions, not one shared pool. The combined report's % stats (drawdown, Sharpe) are scaled against the true total capital (`INITIAL_CAPITAL × number of symbols that traded`), printed in the report header, so they're meaningful rather than relative to a single symbol's $10k. What's still *not* modeled is genuine shared-pool capital allocation across symbols (e.g. one strategy drawing down capital that another symbol could have used) — that's a real portfolio-backtest feature, not a quick fix. Per-symbol reports are unaffected either way.
- **Position sizing is fixed-risk off initial capital, not compounding.** Every trade risks a fixed % of `INITIAL_CAPITAL`, not current equity — so position size doesn't shrink as losses accumulate or grow as the account compounds (it does stop opening new trades entirely once equity is exhausted, see above, but sizing itself isn't equity-scaled in between). Equity-based sizing would be a straightforward extension.
- **Sharpe ratio uses a per-trade annualization shortcut** (`√252`), which is only exactly correct if trade frequency is close to one per day. At 5-minute resolution it's an approximation, not a precise risk-adjusted return figure.

## Next steps

- Equity-based (compounding) position sizing as a config toggle
- Proper portfolio-level backtest: shared capital across symbols, true position-count limits
- Walk-forward / out-of-sample split instead of a single full-period backtest
- Live signal mode (Discord/Telegram alerts) reusing the same detector layer — same pattern as my [arb-bot](https://github.com/juriok/arb-bot) project
