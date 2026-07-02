# Chart Pattern Backtester

Scans Binance USDT pairs for classic chart patterns (Head & Shoulders, Double Top/Bottom, Flags, Triangles), backtests them with ATR-based risk management, and reports win rate, profit factor, Sharpe, and max drawdown — with realistic commission and slippage baked into every trade.

## What this does

Pulls OHLCV history for the top-N Binance pairs by volume, runs 8 pattern detectors over each, and feeds every detected signal into a bar-by-bar backtest engine. Each trade is sized by fixed-fractional risk (% of capital per trade) with stop-loss and take-profit set as ATR multiples. Results are saved as a trade-log CSV and a 4-panel report chart (equity curve, win rate by pattern, P&L by pattern) per symbol, plus a combined report across all symbols.

## Status

🟢 All 8 detectors implemented and tested (Head & Shoulders, Inverse H&S, Double Top, Double Bottom, Bull Flag, Bear Flag, Ascending Triangle, Descending Triangle); ascending_triangle and bull_flag disabled by default on full-2y evidence
🟢 **Shared-capital portfolio engine**: one equity pool across all symbols, timestamp-ordered event stream, portfolio-wide position and leverage caps, compounding sizing, perp funding accrual
🟢 **$10k → $39.6k over the 2-year backtest** (3.96×, PF 1.31, Sharpe 1.91, closed-trade max DD −21%); every full quarter green, every enabled pattern profitable (see *Strategy & results*)
🟡 Next milestone: live signal mode for paper trading on the server

## Strategy & results

The single most important knob is **timeframe**. These chart-pattern breakouts have **no edge on 5-minute candles** — the moves they capture are the same order of magnitude as round-trip trading costs (~0.30%), and the strategy bled out to roughly **−88%** in testing. Worse than random, in fact: at a 2:1 target:stop, a driftless random entry hits its stop ~2/3 of the time (~33% win rate), and the 5m breakouts came in *below* that — they systematically precede reversals (false breakouts, a well-known low-timeframe phenomenon).

Push the same detectors up to **4-hour candles** and the picture flips: breakouts get real follow-through, the per-trade move becomes a large multiple of costs, and the strategy is **net profitable across a broad, diverse coin universe**. Four choices make it robust rather than curve-fit:

- **Trade the 4h timeframe** (`TIMEFRAME = '4h'`) — where breakouts have signal, not noise.
- **Wide stops, 2.5×ATR** (`SL_ATR_MULT = 2.5`) — a 1.5×ATR stop gets knocked out by ordinary 4h intrabar noise before the pattern can work. At 2.5×ATR the breakout win rate rises to ~53%.
- **EMA-smooth the price before locating pivots** (`PIVOT_SMOOTH_SPAN = 5`) — detecting turning points on a denoised series stops single-bar spikes from being mistaken for structural pivots. This one step lifts profit factor from ~1.18 to ~1.26 on the broad universe (stable across spans 4–6).
- **Model futures fees, not spot** (`COMMISSION = 0.00045`) — this is a long/short strategy (it shorts), so it runs on perpetual futures, where taker fees are ~0.045%/side, not the 0.10% of spot. *The edge does not depend on this:* at pessimistic spot fees (0.30% round trip) it is still profitable (PF ~1.26); futures just reflect where it actually trades.

On top of the entry edge, five **capital-efficiency and honesty upgrades** (each validated independently on 2-year data before being made default):

- **Drop `ascending_triangle` and `bull_flag`** (`DISABLED_PATTERNS`) — the two patterns with negative full-2y expectancy. ascending_triangle: PF 0.92, green in 2/8 quarters. bull_flag: −$12.9k over 942 trades on the top-50 universe with a −$13.8k single-quarter tail (mildly positive on curated majors only — breadth evidence wins; mechanism: long continuation entries after pumps mean-revert outside the very top caps). Both judged on the *full* 2y window: short-window pattern rankings invert (bear_flag looked best on 180d, mediocre over 2y), so never disable patterns off a recent window.
- **Concurrent positions** (`MAX_CONCURRENT_POSITIONS = 3`) — the single biggest lever found. With 1, every signal firing while a trade is open was silently skipped, discarding ~⅔ of the strategy's own signals. At 3 slots per symbol, 2y return nearly doubles at the *same* profit factor (the extra trades are equal quality). Saturates beyond 3 (conc=8 adds +1.2% return for −2.3% more DD).
- **Compounding sizing** (`COMPOUND_SIZING = True`) — trades risk 2% of *current* equity, not initial capital: gains compound, drawdowns automatically de-risk.
- **Perp funding accrual** (`FUNDING_RATE_8H = 0.0001`) — crypto funding averages positive (longs pay shorts); the strategy is short-heavy, so it slightly *collects* on net. Modeled pro-rata on bars held.

How robust: across a 24-coin universe (majors, alts, even forex/gold pairs), **every cell** of the stop/target grid (SL ∈ [1.5, 3.0] × TP ∈ [2.0, 4.0]) is profitable. A real edge shows up everywhere in the neighborhood; a curve-fit shows up in one lucky cell. This one is everywhere.

### The portfolio engine (the final and biggest lever)

Everything above was still simulated per-symbol: each coin traded its own isolated $10k silo, which left most capital idle at any moment and made the "combined" report a stapling-together of 43 separate accounts. `backtest/portfolio.py` replaces that with **one shared equity pool** over a global, timestamp-ordered event stream: every trade risks `RISK_PER_TRADE` (0.5%) of *current pool equity*, capital freed by any exit is immediately available to any symbol's next entry, and two account-level guards finally exist — `MAX_PORTFOLIO_POSITIONS` (30) and a real leverage cap (`MAX_PORTFOLIO_NOTIONAL_PCT` = 2× equity).

The sizing sweep shows risk/notional settings trace a pure **leverage line** — PF stays ~1.29–1.31 in *every* cell (the edge never changes, only how hard it's geared): 0.5%/2× → 3.75×, DD −24%; 0.75%/3× → 7.1×, DD −37%. The shipped point (0.5% risk, 2× notional) is the best-PF, most-diversified, sanest-drawdown corner — chosen for live/paper evaluation, not for the biggest headline.

**Latest default run** — top-50 pairs by volume (43 traded), 2 years of 4h candles, one $10,000 pool:

| Metric | Value |
|---|---|
| Final equity | **$39,630 from $10,000 (3.96× in 2 years, ≈ +99%/yr compounded)** |
| Profit factor | 1.31 |
| Win rate | 52.8% |
| Max drawdown | −21.3% (closed-trade basis; mark-to-market would be somewhat deeper) |
| Sharpe | 1.91 |
| Trades | 2,342 |
| Quarters profitable | every full quarter green (+1% to +40%); only the few-day partial stub at the data edge is red |
| Symbols profitable | 30 of 43 |
| Patterns profitable | 6 of 6 enabled |

**Why you can (mostly) believe these numbers:** parameters were tuned on a ~180-day window; everything before ~2026 is data those parameters never saw, and the edge holds across it (PF ~1.03–1.44 by quarter, no blow-up quarters). What the backtest still can't promise: pattern selection was itself decided on this 2y data, so live PF will likely land somewhat below backtest; profit leans heavily short (+$25.9k short vs +$3.7k long) so a violently bullish regime would mute it; the −21% drawdown figure is closed-trade (live equity dips mid-trade will look deeper); and 2 years is one market cycle, not many. **The headline number to plan around is not 99%/yr — it's "PF ~1.2–1.3 with ~25–35% drawdowns at 2× gearing"; paper trading is the next test it has to pass.**

The improvement ladder (per-symbol steps scored on the fixed 16-major silo setup; the last row is the portfolio engine on the top-50 pool):

| Config | 2y result | PF | Max DD |
|---|---|---|---|
| Original (5m, 1.5×ATR, spot fees) | −88% (in 180d!) | 0.42 | −88% |
| 4h + 2.5×ATR + smoothed pivots + futures fees | +16.8% | 1.23 | −3.2% |
| + drop ascending_triangle, + funding, + compounding | +18.3% | 1.25 | −4.0% |
| + 3 concurrent positions per symbol | +32.5% | 1.25 | −4.9% |
| **+ shared-pool portfolio engine (shipped)** | **+296% (3.96×)** | **1.31** | **−21.3%** |

The jump in the last row is *capital utilization and compounding*, not a better signal: the silo model wasted most of the account; the pool deploys it. The per-trade edge is identical.

`LOOKBACK_DAYS` defaults to **730** so the report you get from `python main.py` is the honest 2-year figure, not a flattering recent window.

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
1. Rank Binance USDT pairs by 24h volume and pick the top `TOP_N_PAIRS` (default 50, see `config.py`)
2. Download `LOOKBACK_DAYS` of `TIMEFRAME` candles per pair (default 730 days of 4h candles — see *Strategy & results* for why 4h, not 5m, and why 2 years), cached locally for 12h so repeat runs are fast
3. Run the enabled pattern detectors on each pair
4. Backtest every signal through the **shared-capital portfolio engine** (one equity pool across all symbols) and print the account-level report to the console
5. Save a trade log per symbol (`reports/trades_<symbol>.csv`) plus the portfolio report (`reports/trades_portfolio.csv`, `reports/report_portfolio.png`)

First run downloads candle data (730 days × 4h × 50 pairs ≈ 4,380 candles per pair) — a few minutes with rate limiting. Subsequent runs within 12h reuse the cache.

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
│   ├── engine.py                      # per-symbol simulation: entry, SL/TP, slippage, commission
│   └── portfolio.py                   # shared-capital pool across symbols (the default path)
└── report/
    └── reporter.py                    # stats, trade log CSV, equity curve chart
```

## Configuration

Every threshold lives in `config.py` — pivot sensitivity, pattern tolerance, ATR period, stop-loss/take-profit multiples, risk per trade, commission, and slippage. No magic numbers buried in the detector files.

Two safety knobs worth knowing about: `MIN_ATR_PCT` skips signals on instruments with near-zero volatility (e.g. stablecoin pairs), where ATR-based position sizing isn't a meaningful concept and would otherwise blow up. `MAX_POSITION_PCT` is a hard backstop that caps any single trade's notional exposure as a percentage of capital, regardless of how small the ATR-implied risk-per-unit is. Both exist because pure risk-based sizing (`capital × risk% ÷ stop-distance`) can imply absurd leverage whenever the stop distance is small relative to price — not just on stablecoins, it showed up even on BTC/USDT in testing (~5.7x implied leverage before the cap). Worth keeping in mind if you tune `SL_ATR_MULT` down or trade lower-volatility pairs.

On top of that, the engine tracks running equity and stops opening new trades once it's exhausted (`self.equity <= 0`), so a wiped-out backtest correctly stops near -100% drawdown instead of continuing into nonsensical negative-equity territory.

## Known limitations

These are deliberate simplifications, not bugs — worth knowing before reading too much into the numbers:

- **Drawdown is measured on closed trades.** The equity curve advances when trades *close*; adverse excursion while positions are open isn't marked to market. With up to 30 open positions at 0.5% risk each, live equity can sit meaningfully below the closed-trade curve mid-trade — read "−21% max DD" as "−25 to −35% on a real account".
- **Funding is a flat average, not historical rates.** `FUNDING_RATE_8H` applies one constant (default 0.01%/8h, the long-run positive average) to all pairs and periods. Real funding varies by pair and regime and occasionally flips negative; the effect on results is small but it is an approximation.
- **Fills are idealized.** SL/TP fill exactly at their levels (plus slippage) even through gaps; a candle that jumps past the stop fills at the stop price, not the open beyond it. Real fills through fast moves will be worse.
- **Entry order within a bar is deterministic but arbitrary.** When several symbols signal on the same 4h candle and slots are scarce, the engine admits them in symbol iteration order — a real account would face the same arbitrary choice, but a different order gives slightly different trades.
- **Sharpe ratio uses a per-trade annualization shortcut** (`√252`), which is only exactly correct if trade frequency is close to one per day. It's an approximation, not a precise risk-adjusted return figure.

## Next steps

- **Live signal mode for paper trading** — run detectors on closed 4h candles against the same config, emit entries/exits (Discord/Telegram or a simple log), and track paper fills vs backtest expectations. This is the actual next milestone: the strategy has passed every historical test available; only forward data can grade it now.
- Mark-to-market equity tracking (per-bar open-position valuation) for honest live-style drawdown
- Automated walk-forward split built into the backtester (train/test windows) so future tuning stays honest
- Historical per-pair funding rates instead of the flat average
