# ─── Exchange & Data ────────────────────────────────────────────────────────
# Timeframe matters more than any other single knob here. On 5-minute candles
# these chart-pattern breakouts have NO edge: the moves are noise-dominated and
# the same order of magnitude as round-trip trading costs, so the strategy bleeds
# out (~-90%). On 4h candles the same breakouts have genuine follow-through — the
# per-trade move is a large multiple of costs — and the strategy is net positive
# across a broad, diverse coin universe (see README "Strategy & results").
EXCHANGE        = 'binance'
QUOTE_CURRENCY  = 'USDT'
TOP_N_PAIRS     = 50
TIMEFRAME       = '4h'
# 730 days ≈ 2 years, deliberately long: the strategy parameters were tuned on a
# ~180-day window, so a 2-year default backtest is dominated by data those
# parameters never saw. The number it prints is the honest out-of-sample figure
# (PF ~1.2x), not the flattering in-sample one (PF ~1.4).
LOOKBACK_DAYS   = 730
DATA_CACHE_DIR  = 'cache'

# ─── Pattern Detection ──────────────────────────────────────────────────────
PIVOT_ORDER          = 5
# EMA-smooth price before locating pivots so single-bar spikes aren't mistaken
# for structural turning points. span≈5 is the sweet spot (stable across 4–6);
# 0/1 disables. This denoising step lifts profit factor from ~1.18 to ~1.26 on
# the broad universe — see README "Strategy & results". Set to 0 for raw pivots.
PIVOT_SMOOTH_SPAN    = 5
# Patterns whose signals are discarded, each on FULL-2y broad-universe evidence
# (never a recent window — short-window pattern rankings invert; bear_flag
# looked best on 180d and is flat over 2y):
#   ascending_triangle — PF 0.92, green 2/8 quarters (123 trades, 16 majors).
#   bull_flag          — net -$12.9k over 942 trades on the top-50 universe,
#                        green 4/9 quarters with a -$13.8k single-quarter tail
#                        (PF 0.39 in 2025Q4). Mildly positive on curated majors
#                        only (+$3k, PF 1.10) — the breadth evidence wins.
#                        Mechanism: long continuation entries after pumps get
#                        mean-reverted in anything but the very top caps.
DISABLED_PATTERNS    = {'ascending_triangle', 'bull_flag'}
PATTERN_TOLERANCE    = 0.03
MIN_PATTERN_BARS     = 15
MAX_PATTERN_BARS     = 100
BREAKOUT_WINDOW      = 20
MIN_HEAD_PROMINENCE  = 0.015
VOLUME_FILTER        = True

# Flag-specific
MIN_POLE_PCT         = 0.025
POLE_BARS            = 12
MIN_FLAG_BARS        = 5
MAX_FLAG_BARS        = 20
MAX_FLAG_CHANNEL_W   = 0.05
MAX_FLAG_SLOPE       = 0.002

# ─── Risk Management ────────────────────────────────────────────────────────
# Stop distance is deliberately wide (2.5 ATR). On 4h candles a 1.5-ATR stop gets
# knocked out by ordinary intrabar noise before the breakout has room to work; at
# 2.5 ATR the winner rate on breakouts rises to ~52% and the edge is stable across
# the whole stop/target grid (every sl∈[1.5,3.0] × tp∈[2.0,4.0] cell is profitable
# on the broad universe — the mark of a real edge, not a curve-fit spike).
ATR_PERIOD       = 14
SL_ATR_MULT      = 2.5
TP_ATR_MULT      = 3.0
MAX_TRADE_BARS   = 50
MIN_ATR_PCT      = 0.0005   # skip instruments whose ATR is < 0.05% of price (e.g. stablecoin pairs)
MAX_POSITION_PCT = 0.5      # hard cap: a single trade can never exceed 50% of capital notional

# ─── Backtest ───────────────────────────────────────────────────────────────
# Costs are modelled for Binance USD-M perpetual FUTURES, which is the correct
# venue: this is a long/short strategy (it shorts H&S / bear flags / breakdowns),
# and you cannot short on spot. Futures taker fee ≈ 0.045%/side; slippage on the
# liquid pairs traded here ≈ 0.01%/side (≈0.11% round trip).
#
# Importantly, the edge does NOT depend on these lower fees: at the original
# pessimistic *spot* assumptions (0.10% + 0.05%/side ≈ 0.30% round trip) the
# strategy is still net profitable (PF ~1.26 on the broad universe). Futures fees
# just reflect where it would actually trade and roughly double the net return.
INITIAL_CAPITAL  = 10_000
# % of current POOL equity risked per trade (portfolio engine). 0.5% looks
# small but the pool runs up to MAX_PORTFOLIO_POSITIONS trades at once, so
# portfolio heat is ~15% at full load. The 2y sweep shows risk/notional trace a
# pure leverage line (PF ~1.29-1.31 in EVERY cell — the edge doesn't change,
# only how hard it's geared): 0.5%/2x → 3.75x, DD -24%; 0.75%/3x → 7.1x,
# DD -37%. 0.5% + 2x notional is the shipped point: best PF, most trades
# (diversification), drawdown still sane for live/paper evaluation.
RISK_PER_TRADE   = 0.005
COMMISSION       = 0.00045
SLIPPAGE         = 0.0001

# Size trades off CURRENT equity instead of INITIAL_CAPITAL. Gains compound and
# losses de-risk (position size shrinks in a drawdown). Does not change the
# per-trade edge — it changes how the edge accumulates.
COMPOUND_SIZING  = True

# How many positions a single symbol's engine may hold at once. With 1 (the
# original behaviour) every signal that fires while a trade is open is silently
# skipped — that discarded roughly two-thirds of the strategy's own signals.
# 2y validation: conc=3 nearly doubles return (+16.8% -> +32.5%) at the SAME
# profit factor (~1.25, i.e. the extra trades are equal quality) with max DD
# only -4.9%. Beyond 3 it saturates: conc=8 adds just +1.2% return for -2.3%
# more drawdown. Note >1 stacks margin: worst case = conc x MAX_POSITION_PCT
# notional per symbol.
MAX_CONCURRENT_POSITIONS = 3

# Perpetual-futures funding, expressed per 8h period (Binance charges 3x/day).
# Crypto funding is positive on average (longs pay shorts, ~0.01%/8h baseline),
# and this strategy is short-heavy, so it net *collects* funding. Accrued
# pro-rata on bars held, on entry notional. Set to 0 to disable.
FUNDING_RATE_8H  = 0.0001

# ─── Portfolio (shared capital pool — backtest/portfolio.py) ────────────────
# One equity pool across all symbols; INITIAL_CAPITAL is the WHOLE account.
# RISK_PER_TRADE above is % of current *pool* equity per trade.
# At 0.5% risk the position-count cap stops binding around ~25 open trades
# (cap 30/40/60 all give identical results) — the notional cap below is the
# real constraint. Raising it to 3x lifts 2y return 3.75x→5x but DD -24%→-33%:
# pure leverage, not alpha. 2x matches what a real futures account can carry
# comfortably.
MAX_PORTFOLIO_POSITIONS   = 30    # open trades across all symbols
MAX_PORTFOLIO_NOTIONAL_PCT = 2.0  # total open notional <= 2x equity (leverage cap)

# ─── Report ─────────────────────────────────────────────────────────────────
REPORT_DIR = 'reports'