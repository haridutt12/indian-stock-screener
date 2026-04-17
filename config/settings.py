import pytz

# Timezone
IST = pytz.timezone("Asia/Kolkata")

# Market hours (IST)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 15
MARKET_CLOSE_HOUR = 15
MARKET_CLOSE_MINUTE = 30
PRE_MARKET_OPEN_HOUR = 9
PRE_MARKET_OPEN_MINUTE = 0

# Cache TTLs (seconds)
CACHE_TTL_PRICE_INTRADAY = 300       # 5 min
CACHE_TTL_PRICE_DAILY = 86400        # 1 day
CACHE_TTL_FUNDAMENTALS = 604800      # 1 week
CACHE_TTL_NEWS = 14400               # 4 hours
CACHE_TTL_SENTIMENT = 14400          # 4 hours
CACHE_TTL_SIGNALS = 300              # 5 min (intraday), refreshed by scheduler

# Data store
CACHE_DB_PATH = "data_store/cache.db"

# yfinance settings
YFINANCE_PERIOD_DAILY = "6mo"
YFINANCE_PERIOD_INTRADAY = "5d"
YFINANCE_INTERVAL_DAILY = "1d"
YFINANCE_INTERVAL_INTRADAY = "5m"

# Technical indicator parameters
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14
SMA_SHORT = 20
SMA_MID = 50
SMA_LONG = 200
EMA_FAST = 9
EMA_SLOW = 21
VOLUME_AVG_PERIOD = 20

# Screening thresholds
MIN_MARKET_CAP_CR = 500       # Minimum market cap in crores
MIN_VOLUME_LAKHS = 10         # Minimum avg daily volume in lakhs
VOLUME_SPIKE_MULTIPLIER = 1.5 # Volume spike threshold vs avg

# Signal generation
MIN_RISK_REWARD = 2.0         # Minimum R:R for trade signals
MAX_SWING_SIGNALS = 10
MAX_INTRADAY_SIGNALS = 8
INTRADAY_LIQUID_STOCKS = 30   # Top N stocks by volume for intraday

# Indices (yfinance tickers)
INDICES = {
    "Nifty 50":       "^NSEI",
    "Bank Nifty":     "^NSEBANK",
    "Sensex":         "^BSESN",
    "Nifty IT":       "^CNXIT",
    "Nifty Pharma":   "^CNXPHARMA",
    "Nifty FMCG":     "^CNXFMCG",
    "Nifty Auto":     "^CNXAUTO",
    "Nifty Metal":    "^CNXMETAL",
    "Nifty Realty":   "^CNXREALTY",
    "Nifty Energy":   "^CNXENERGY",
    "Nifty Finance":  "^CNXFINANCE",
    "Nifty Infra":    "^CNXINFRA",
    "Nifty Media":    "^CNXMEDIA",
    "Nifty MidCap":   "^CNXMIDCAP",
    "Nifty SmallCap": "^CNXSMALLCAP",
    "Nifty PSU Bank": "^CNXPSUBANK",
}

# Sector display names
SECTOR_NAMES = [
    "IT", "Banking", "Pharma", "FMCG", "Auto",
    "Metal", "Realty", "Energy", "Infrastructure", "Media"
]
