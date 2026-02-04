#!/usr/bin/env python3
"""
Polymarket NBA Trading Bot - Single File Version
For easy deployment on Railway/Heroku/etc
"""

import os
import sys
import time
import signal
import logging
import sqlite3
import json
import re
import requests
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# ===========================================
# CONFIGURATION
# ===========================================

# Telegram settings - can be overridden by environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8322947345:AAHWiYZKi514cVHqSueLgRV1WZYsnncQJos")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "440615055")

# Polymarket API endpoints
GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"

# Trading strategy parameters
ENTRY_THRESHOLD = float(os.environ.get("ENTRY_THRESHOLD", "0.80"))  # 80%
POSITION_SIZE = float(os.environ.get("POSITION_SIZE", "100.0"))  # $100
STOP_LOSS = float(os.environ.get("STOP_LOSS", "0.60"))  # 60%
TAKE_PROFIT = 1.0

# Bot settings
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))  # seconds

# NBA keywords for filtering
NBA_KEYWORDS = [
    "nba", "basketball",
    "lakers", "celtics", "warriors", "knicks", "heat", "bucks",
    "nets", "76ers", "sixers", "bulls", "cavaliers", "cavs",
    "mavericks", "mavs", "rockets", "clippers", "suns", "nuggets",
    "timberwolves", "wolves", "thunder", "spurs", "grizzlies",
    "pelicans", "trail blazers", "blazers", "jazz", "kings",
    "pacers", "hawks", "hornets", "magic", "pistons", "raptors",
    "wizards",
]

LIVE_INDICATORS = ["live", "in-progress", "today", "tonight", "vs", "v.", "versus"]

# Database & Logging
DATABASE_PATH = os.environ.get("DATABASE_PATH", "trades.db")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ===========================================
# DATA MODELS
# ===========================================

@dataclass
class MarketOutcome:
    token_id: str
    outcome: str
    price: float


@dataclass
class Market:
    id: str
    condition_id: str
    question: str
    slug: str
    outcomes: list
    end_date: Optional[str]
    closed: bool
    resolved: bool
    volume: float
    liquidity: float

    @property
    def yes_price(self) -> float:
        for outcome in self.outcomes:
            if outcome.outcome.lower() == "yes":
                return outcome.price
        return 0.0

    @property
    def no_price(self) -> float:
        for outcome in self.outcomes:
            if outcome.outcome.lower() == "no":
                return outcome.price
        return 0.0

    @property
    def best_outcome(self) -> tuple:
        if self.yes_price >= self.no_price:
            return ("YES", self.yes_price)
        return ("NO", self.no_price)


class PositionStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TradeResult(Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    STOPPED = "STOPPED"
    PENDING = "PENDING"


@dataclass
class Position:
    id: str
    market_id: str
    market_title: str
    side: str
    entry_price: float
    entry_time: datetime
    size_usd: float
    shares: float
    status: PositionStatus = PositionStatus.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    pnl_usd: Optional[float] = None
    pnl_percent: Optional[float] = None
    result: TradeResult = TradeResult.PENDING

    def to_dict(self) -> dict:
        data = asdict(self)
        data['status'] = self.status.value
        data['result'] = self.result.value
        data['entry_time'] = self.entry_time.isoformat()
        if self.exit_time:
            data['exit_time'] = self.exit_time.isoformat()
        return data


@dataclass
class TradeSignal:
    market: Market
    action: str
    side: str
    price: float
    reason: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ===========================================
# POLYMARKET API CLIENT
# ===========================================

class PolymarketAPI:
    def __init__(self):
        self.gamma_url = GAMMA_API_URL
        self.clob_url = CLOB_API_URL
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

    def get_markets(self, closed: bool = False, limit: int = 100, offset: int = 0) -> list:
        params = {
            "closed": str(closed).lower(),
            "limit": limit,
            "offset": offset,
            "order": "id",
            "ascending": "false"
        }
        try:
            response = self.session.get(f"{self.gamma_url}/markets", params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching markets: {e}")
            return []

    def search_markets(self, query: str, limit: int = 50) -> list:
        params = {"q": query, "limit": limit}
        try:
            response = self.session.get(f"{self.gamma_url}/search", params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data.get("markets", []) if isinstance(data, dict) else data
        except requests.RequestException as e:
            logger.error(f"Error searching markets: {e}")
            return []

    def get_price(self, token_id: str) -> Optional[float]:
        try:
            response = self.session.get(f"{self.clob_url}/price", params={"token_id": token_id}, timeout=10)
            response.raise_for_status()
            return float(response.json().get("price", 0))
        except:
            return None

    def parse_market(self, raw: dict) -> Optional[Market]:
        try:
            outcomes = []
            clob_token_ids = raw.get("clobTokenIds", [])
            outcome_names = raw.get("outcomes", ["Yes", "No"])
            outcome_prices = raw.get("outcomePrices", [])

            for i, token_id in enumerate(clob_token_ids):
                outcome_name = outcome_names[i] if i < len(outcome_names) else f"Outcome {i}"
                if outcome_prices and i < len(outcome_prices):
                    try:
                        price = float(outcome_prices[i])
                    except:
                        price = 0.0
                else:
                    price = self.get_price(token_id) or 0.0
                outcomes.append(MarketOutcome(token_id=token_id, outcome=outcome_name, price=price))

            return Market(
                id=raw.get("id", ""),
                condition_id=raw.get("conditionId", ""),
                question=raw.get("question", raw.get("title", "")),
                slug=raw.get("slug", ""),
                outcomes=outcomes,
                end_date=raw.get("endDate"),
                closed=raw.get("closed", False),
                resolved=raw.get("resolved", False),
                volume=float(raw.get("volume", 0) or 0),
                liquidity=float(raw.get("liquidity", 0) or 0)
            )
        except Exception as e:
            logger.error(f"Error parsing market: {e}")
            return None


# ===========================================
# NBA MARKET PARSER
# ===========================================

class NBAMarketParser:
    def __init__(self, api: PolymarketAPI):
        self.api = api
        self.keywords = [kw.lower() for kw in NBA_KEYWORDS]
        self.live_indicators = [ind.lower() for ind in LIVE_INDICATORS]

    def is_nba_market(self, market: Market) -> bool:
        text = f"{market.question} {market.slug}".lower()
        return any(kw in text for kw in self.keywords)

    def is_game_market(self, market: Market) -> bool:
        text = market.question.lower()
        exclude = [r"champion\s*\d{4}", r"mvp", r"finals", r"playoff", r"conference", r"season", r"all-?star", r"rookie", r"draft", r"trade"]
        if any(re.search(p, text) for p in exclude):
            return False
        include = [r"vs\.?", r"versus", r"win", r"beat", r"@"]
        return any(re.search(p, text) for p in include)

    def is_likely_live(self, market: Market) -> bool:
        text = market.question.lower()
        if any(ind in text for ind in self.live_indicators):
            return True
        if market.end_date:
            try:
                end_dt = datetime.fromisoformat(market.end_date.replace('Z', '+00:00'))
                hours_until_end = (end_dt - datetime.now(timezone.utc)).total_seconds() / 3600
                if 0 < hours_until_end < 6:
                    return True
            except:
                pass
        return not market.closed and not market.resolved and market.liquidity > 1000

    def fetch_nba_markets(self) -> list:
        nba_markets = []
        raw_markets = self.api.search_markets("NBA", limit=100)
        logger.info(f"Fetched {len(raw_markets)} markets via search")

        if len(raw_markets) < 20:
            all_markets = self.api.get_markets(closed=False, limit=200)
            raw_markets.extend(all_markets)

        seen_ids = set()
        for raw in raw_markets:
            market_id = raw.get("id", raw.get("conditionId", ""))
            if market_id in seen_ids:
                continue
            seen_ids.add(market_id)

            market = self.api.parse_market(raw)
            if not market:
                continue
            if not self.is_nba_market(market):
                continue
            if not self.is_game_market(market):
                continue
            nba_markets.append(market)

        logger.info(f"Found {len(nba_markets)} active NBA game markets")
        return nba_markets


# ===========================================
# TRADING STRATEGY
# ===========================================

class TradingStrategy:
    def __init__(self):
        self.entry_threshold = ENTRY_THRESHOLD
        self.stop_loss = STOP_LOSS
        self.take_profit = TAKE_PROFIT
        self.position_size = POSITION_SIZE

    def should_enter(self, market: Market, existing_position: bool = False) -> Optional[TradeSignal]:
        if existing_position or market.closed or market.resolved:
            return None
        best_side, best_price = market.best_outcome
        if best_price >= self.entry_threshold:
            return TradeSignal(
                market=market, action="BUY", side=best_side, price=best_price,
                reason=f"Entry signal: {best_side} at {best_price:.1%} >= {self.entry_threshold:.0%} threshold"
            )
        return None

    def should_exit(self, market: Market, entry_price: float, entry_side: str) -> Optional[TradeSignal]:
        current_price = market.yes_price if entry_side == "YES" else market.no_price
        if market.resolved or market.closed:
            reason = "WIN - Market resolved in our favor" if current_price >= 0.99 else "LOSS - Market resolved against us" if current_price <= 0.01 else "Market resolved"
            return TradeSignal(market=market, action="SELL", side=entry_side, price=current_price, reason=reason)
        if current_price <= self.stop_loss:
            return TradeSignal(market=market, action="SELL", side=entry_side, price=current_price, reason=f"STOP LOSS: {current_price:.1%} <= {self.stop_loss:.0%}")
        if current_price >= self.take_profit:
            return TradeSignal(market=market, action="SELL", side=entry_side, price=current_price, reason=f"TAKE PROFIT: {current_price:.1%}")
        return None


# ===========================================
# PORTFOLIO MANAGER
# ===========================================

class Portfolio:
    def __init__(self):
        self.positions: dict = {}
        self._counter = 0

    def _generate_id(self) -> str:
        self._counter += 1
        return f"pos_{self._counter:04d}"

    def has_position(self, market_id: str) -> bool:
        return any(p.market_id == market_id and p.status == PositionStatus.OPEN for p in self.positions.values())

    def get_position(self, market_id: str) -> Optional[Position]:
        for p in self.positions.values():
            if p.market_id == market_id and p.status == PositionStatus.OPEN:
                return p
        return None

    def open_position(self, market_id: str, market_title: str, side: str, entry_price: float, size_usd: float) -> Position:
        shares = size_usd / entry_price if entry_price > 0 else 0
        position = Position(
            id=self._generate_id(), market_id=market_id, market_title=market_title,
            side=side, entry_price=entry_price, entry_time=datetime.now(timezone.utc),
            size_usd=size_usd, shares=shares
        )
        self.positions[position.id] = position
        logger.info(f"Opened position {position.id}: {side} @ {entry_price:.2%}")
        return position

    def close_position(self, position_id: str, exit_price: float, result: TradeResult) -> Position:
        position = self.positions[position_id]
        pnl_per_share = exit_price - position.entry_price
        position.status = PositionStatus.CLOSED
        position.exit_price = exit_price
        position.exit_time = datetime.now(timezone.utc)
        position.pnl_usd = pnl_per_share * position.shares
        position.pnl_percent = (pnl_per_share / position.entry_price) * 100 if position.entry_price > 0 else 0
        position.result = result
        logger.info(f"Closed position {position_id}: {result.value} P&L: ${position.pnl_usd:+.2f}")
        return position

    def get_open_positions(self) -> list:
        return [p for p in self.positions.values() if p.status == PositionStatus.OPEN]

    def get_statistics(self) -> dict:
        closed = [p for p in self.positions.values() if p.status == PositionStatus.CLOSED]
        if not closed:
            return {"total_trades": 0, "wins": 0, "losses": 0, "stopped": 0, "win_rate": 0.0, "total_pnl": 0.0, "open_positions": len(self.get_open_positions())}
        wins = [p for p in closed if p.result == TradeResult.WIN]
        losses = [p for p in closed if p.result == TradeResult.LOSS]
        stopped = [p for p in closed if p.result == TradeResult.STOPPED]
        return {
            "total_trades": len(closed), "wins": len(wins), "losses": len(losses), "stopped": len(stopped),
            "win_rate": len(wins) / len(closed) * 100, "total_pnl": sum(p.pnl_usd or 0 for p in closed),
            "open_positions": len(self.get_open_positions())
        }


# ===========================================
# TELEGRAM NOTIFIER
# ===========================================

class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = requests.Session()

    def send_message(self, text: str) -> bool:
        try:
            response = self.session.post(
                f"{self.api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=10
            )
            return response.status_code == 200
        except:
            return False

    def test_connection(self) -> bool:
        try:
            response = self.session.get(f"{self.api_url}/getMe", timeout=10)
            if response.status_code == 200 and response.json().get("ok"):
                logger.info(f"Telegram connected: @{response.json()['result'].get('username')}")
                return True
        except:
            pass
        return False

    def notify_entry(self, trade_info: dict) -> bool:
        price_pct = trade_info['price'] * 100
        message = f"""🟢 <b>ПОЗИЦИЯ ОТКРЫТА</b>

🏀 <b>{trade_info['market_title']}</b>
📍 Ставка: <b>{trade_info['side']}</b>
💰 Цена входа: <b>{price_pct:.0f}¢</b> ({price_pct:.0f}%)
💵 Размер: <b>${trade_info['size_usd']:.0f}</b> → {trade_info['shares']:.2f} shares

⏰ {datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M UTC')}
🔗 <a href="{trade_info.get('market_url', '')}">Открыть на Polymarket</a>

<i>📊 Симуляция</i>"""
        return self.send_message(message)

    def notify_exit(self, trade_info: dict) -> bool:
        result = trade_info['result']
        if result == "WIN":
            header = "🔴 <b>ПОЗИЦИЯ ЗАКРЫТА — WIN</b> ✅"
        elif result == "STOPPED":
            header = "🟡 <b>СТОП-ЛОСС СРАБОТАЛ</b>"
        else:
            header = "🔴 <b>ПОЗИЦИЯ ЗАКРЫТА — LOSS</b> ❌"

        stats = trade_info.get('stats', {})
        stats_text = f"""
📊 <b>Статистика сессии:</b>
├ Всего сделок: {stats.get('total_trades', 0)}
├ Винрейт: {stats.get('win_rate', 0):.0f}% ({stats.get('wins', 0)}W/{stats.get('losses', 0)}L/{stats.get('stopped', 0)}S)
└ Общий P&L: <b>${stats.get('total_pnl', 0):+.2f}</b>""" if stats else ""

        message = f"""{header}

🏀 <b>{trade_info['market_title']}</b>
📍 {trade_info['side']}
💰 Вход: {trade_info['entry_price']*100:.0f}¢ → Выход: {trade_info['exit_price']*100:.0f}¢
💵 P&L: <b>${trade_info['pnl_usd']:+.2f}</b> ({trade_info['pnl_percent']:+.1f}%)

📝 {trade_info['reason']}
{stats_text}

<i>📊 Симуляция</i>"""
        return self.send_message(message)

    def notify_startup(self) -> bool:
        message = f"""🚀 <b>БОТ ЗАПУЩЕН</b>

⚙️ <b>Настройки:</b>
├ Порог входа: {int(ENTRY_THRESHOLD * 100)}%
├ Стоп-лосс: {int(STOP_LOSS * 100)}%
├ Размер позиции: ${POSITION_SIZE:.0f}
└ Интервал: {CHECK_INTERVAL} сек

🏀 Мониторинг NBA рынков...

<i>📊 Режим симуляции</i>"""
        return self.send_message(message)

    def notify_error(self, error: str) -> bool:
        return self.send_message(f"⚠️ <b>ОШИБКА</b>\n\n{error}")


# ===========================================
# TRADE SIMULATOR
# ===========================================

class TradeSimulator:
    def __init__(self, strategy: TradingStrategy, portfolio: Portfolio):
        self.strategy = strategy
        self.portfolio = portfolio

    def process_market(self, market: Market) -> Optional[dict]:
        market_id = market.id or market.condition_id
        existing = self.portfolio.get_position(market_id)

        if existing:
            return self._check_exit(market, existing)
        else:
            return self._check_entry(market)

    def _check_entry(self, market: Market) -> Optional[dict]:
        market_id = market.id or market.condition_id
        signal = self.strategy.should_enter(market, self.portfolio.has_position(market_id))

        if signal and signal.action == "BUY":
            position = self.portfolio.open_position(
                market_id=market_id, market_title=market.question,
                side=signal.side, entry_price=signal.price, size_usd=self.strategy.position_size
            )
            return {
                "type": "ENTRY", "position_id": position.id, "market_id": market_id,
                "market_title": market.question, "side": signal.side, "price": signal.price,
                "size_usd": position.size_usd, "shares": position.shares, "reason": signal.reason,
                "market_url": f"https://polymarket.com/event/{market.slug}"
            }
        return None

    def _check_exit(self, market: Market, position: Position) -> Optional[dict]:
        signal = self.strategy.should_exit(market, position.entry_price, position.side)

        if signal and signal.action == "SELL":
            result = TradeResult.WIN if "WIN" in signal.reason.upper() else TradeResult.STOPPED if "STOP" in signal.reason.upper() else TradeResult.LOSS
            closed = self.portfolio.close_position(position.id, signal.price, result)
            return {
                "type": "EXIT", "position_id": position.id, "market_id": position.market_id,
                "market_title": position.market_title, "side": position.side,
                "entry_price": position.entry_price, "exit_price": signal.price,
                "shares": position.shares, "pnl_usd": closed.pnl_usd, "pnl_percent": closed.pnl_percent,
                "result": result.value, "reason": signal.reason, "stats": self.portfolio.get_statistics()
            }
        return None


# ===========================================
# MAIN BOT
# ===========================================

class NBABot:
    def __init__(self):
        self.running = False
        self.cycle_count = 0
        self.api = PolymarketAPI()
        self.parser = NBAMarketParser(self.api)
        self.strategy = TradingStrategy()
        self.portfolio = Portfolio()
        self.simulator = TradeSimulator(self.strategy, self.portfolio)
        self.notifier = TelegramNotifier()

    def start(self):
        logger.info("=" * 50)
        logger.info("Starting Polymarket NBA Trading Bot")
        logger.info("=" * 50)

        if not self.notifier.test_connection():
            logger.error("Failed to connect to Telegram")
            return

        self.notifier.notify_startup()

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        self.running = True
        logger.info(f"Bot started. Checking every {CHECK_INTERVAL}s. Entry >= {ENTRY_THRESHOLD:.0%}")

        while self.running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                self.notifier.notify_error(str(e))
            if self.running:
                time.sleep(CHECK_INTERVAL)

        logger.info("Bot stopped.")

    def _run_cycle(self):
        self.cycle_count += 1
        logger.info(f"--- Cycle {self.cycle_count} ---")

        markets = self.parser.fetch_nba_markets()
        if not markets:
            logger.warning("No NBA markets found")
            return

        live_markets = [m for m in markets if self.parser.is_likely_live(m)]
        logger.info(f"Found {len(live_markets)} potentially live markets")

        for market in live_markets:
            try:
                self._process_market(market)
            except Exception as e:
                logger.error(f"Error processing {market.question}: {e}")

        self._check_open_positions(markets)

    def _process_market(self, market: Market):
        market_id = market.id or market.condition_id
        if self.portfolio.has_position(market_id):
            return

        best_side, best_price = market.best_outcome
        if best_price >= ENTRY_THRESHOLD:
            logger.info(f"Signal: {market.question} - {best_side} at {best_price:.1%}")
            trade_info = self.simulator.process_market(market)
            if trade_info and trade_info['type'] == 'ENTRY':
                self.notifier.notify_entry(trade_info)

    def _check_open_positions(self, current_markets: list):
        open_positions = self.portfolio.get_open_positions()
        if not open_positions:
            return

        market_lookup = {m.id: m for m in current_markets}
        market_lookup.update({m.condition_id: m for m in current_markets})

        for position in open_positions:
            market = market_lookup.get(position.market_id)
            if not market:
                continue
            trade_info = self.simulator.process_market(market)
            if trade_info and trade_info['type'] == 'EXIT':
                self.notifier.notify_exit(trade_info)

    def _shutdown(self, signum, frame):
        logger.info(f"Shutdown signal received ({signum})")
        self.running = False


# ===========================================
# ENTRY POINT
# ===========================================

if __name__ == "__main__":
    bot = NBABot()
    bot.start()
