# ─── Exchange & Data ────────────────────────────────────────────────────────
EXCHANGE        = 'binance'
QUOTE_CURRENCY  = 'USDT'
TOP_N_PAIRS     = 10
TIMEFRAME       = '5m'
LOOKBACK_DAYS   = 180
DATA_CACHE_DIR  = 'cache'

# ─── Pattern Detection ──────────────────────────────────────────────────────
PIVOT_ORDER          = 5
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
ATR_PERIOD       = 14
SL_ATR_MULT      = 1.5
TP_ATR_MULT      = 3.0
MAX_TRADE_BARS   = 50
MIN_ATR_PCT      = 0.0005   # skip instruments whose ATR is < 0.05% of price (e.g. stablecoin pairs)
MAX_POSITION_PCT = 0.5      # hard cap: a single trade can never exceed 50% of capital notional

# ─── Backtest ───────────────────────────────────────────────────────────────
INITIAL_CAPITAL  = 10_000
RISK_PER_TRADE   = 0.02
COMMISSION       = 0.001
SLIPPAGE         = 0.0005

# ─── Report ─────────────────────────────────────────────────────────────────
REPORT_DIR = 'reports'