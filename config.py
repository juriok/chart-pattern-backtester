# ─── Exchange & Data ────────────────────────────────────────────────────────
# Timeframe matters more than any other single knob here. On 5-minute candles
# these chart-pattern breakouts have NO edge: the moves are noise-dominated and
# the same order of magnitude as round-trip trading costs, so the strategy bleeds
# out (~-90%). On 4h candles the same breakouts have genuine follow-through — the
# per-trade move is a large multiple of costs — and the strategy is net positive
# across a broad, diverse coin universe (see README "Strategy & results").
EXCHANGE        = 'binance'
QUOTE_CURRENCY  = 'USDT'
TOP_N_PAIRS     = 20
TIMEFRAME       = '4h'
LOOKBACK_DAYS   = 180
DATA_CACHE_DIR  = 'cache'

# ─── Pattern Detection ──────────────────────────────────────────────────────
PIVOT_ORDER          = 5
# EMA-smooth price before locating pivots so single-bar spikes aren't mistaken
# for structural turning points. span≈5 is the sweet spot (stable across 4–6);
# 0/1 disables. This denoising step lifts profit factor from ~1.18 to ~1.26 on
# the broad universe — see README "Strategy & results". Set to 0 for raw pivots.
PIVOT_SMOOTH_SPAN    = 5
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
RISK_PER_TRADE   = 0.02
COMMISSION       = 0.00045
SLIPPAGE         = 0.0001

# ─── Report ─────────────────────────────────────────────────────────────────
REPORT_DIR = 'reports'