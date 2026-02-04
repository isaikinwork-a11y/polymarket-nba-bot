"""
Configuration for Polymarket NBA Trading Bot
"""

# ===========================================
# TELEGRAM SETTINGS
# ===========================================
TELEGRAM_BOT_TOKEN = "8322947345:AAHWiYZKi514cVHqSueLgRV1WZYsnncQJos"
TELEGRAM_CHAT_ID = "440615055"

# ===========================================
# POLYMARKET API ENDPOINTS
# ===========================================
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"
DATA_API_URL = "https://data-api.polymarket.com"

# ===========================================
# TRADING STRATEGY PARAMETERS
# ===========================================

# Entry threshold - minimum probability to enter a position
ENTRY_THRESHOLD = 0.80  # 80%

# Position size in USD (simulation)
POSITION_SIZE = 100.0

# Stop loss - exit if price drops below this
STOP_LOSS = 0.60  # 60%

# Take profit - optional, exit if price reaches this (1.0 = win)
TAKE_PROFIT = 1.0

# ===========================================
# BOT SETTINGS
# ===========================================

# How often to check markets (seconds)
CHECK_INTERVAL = 60  # 1 minute

# Keywords to identify NBA markets
NBA_KEYWORDS = [
    "nba", "basketball",
    # Teams
    "lakers", "celtics", "warriors", "knicks", "heat", "bucks",
    "nets", "76ers", "sixers", "bulls", "cavaliers", "cavs",
    "mavericks", "mavs", "rockets", "clippers", "suns", "nuggets",
    "timberwolves", "wolves", "thunder", "spurs", "grizzlies",
    "pelicans", "trail blazers", "blazers", "jazz", "kings",
    "pacers", "hawks", "hornets", "magic", "pistons", "raptors",
    "wizards",
]

# Keywords that indicate a LIVE/in-progress game
LIVE_INDICATORS = [
    "live", "in-progress", "today", "tonight",
    "vs", "v.", "versus"
]

# ===========================================
# DATABASE
# ===========================================
DATABASE_PATH = "data/trades.db"

# ===========================================
# LOGGING
# ===========================================
LOG_LEVEL = "INFO"
LOG_FILE = "data/bot.log"
