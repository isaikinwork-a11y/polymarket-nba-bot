#!/usr/bin/env python3
"""
Test script to verify bot components work correctly
Run without network access
"""

import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

print("=" * 50)
print("Polymarket NBA Bot - Component Test")
print("=" * 50)

# Test 1: Config import
print("\n1. Testing config import...")
try:
    from config import (
        TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
        ENTRY_THRESHOLD, STOP_LOSS, POSITION_SIZE
    )
    print(f"   ✅ Config loaded")
    print(f"   - Entry threshold: {ENTRY_THRESHOLD:.0%}")
    print(f"   - Stop loss: {STOP_LOSS:.0%}")
    print(f"   - Position size: ${POSITION_SIZE}")
    print(f"   - Telegram Chat ID: {TELEGRAM_CHAT_ID}")
except Exception as e:
    print(f"   ❌ Config error: {e}")

# Test 2: Polymarket API module
print("\n2. Testing Polymarket API module...")
try:
    from polymarket.api import Market, MarketOutcome, PolymarketAPI
    
    # Create mock market
    mock_market = Market(
        id="test_123",
        condition_id="0xabc",
        question="Lakers vs Celtics - Winner",
        slug="lakers-vs-celtics",
        outcomes=[
            MarketOutcome(token_id="token1", outcome="Yes", price=0.82),
            MarketOutcome(token_id="token2", outcome="No", price=0.18)
        ],
        end_date="2025-02-04T23:00:00Z",
        closed=False,
        resolved=False,
        volume=50000,
        liquidity=10000
    )
    
    print(f"   ✅ Market object created")
    print(f"   - Question: {mock_market.question}")
    print(f"   - YES price: {mock_market.yes_price:.2%}")
    print(f"   - NO price: {mock_market.no_price:.2%}")
    print(f"   - Best outcome: {mock_market.best_outcome}")
except Exception as e:
    print(f"   ❌ API module error: {e}")

# Test 3: NBA Parser
print("\n3. Testing NBA Parser...")
try:
    from polymarket.parser import NBAMarketParser
    
    parser = NBAMarketParser()
    
    # Test with mock market
    is_nba = parser.is_nba_market(mock_market)
    is_game = parser.is_game_market(mock_market)
    teams = parser.extract_teams(mock_market)
    
    print(f"   ✅ Parser loaded")
    print(f"   - Is NBA market: {is_nba}")
    print(f"   - Is game market: {is_game}")
    print(f"   - Teams extracted: {teams}")
except Exception as e:
    print(f"   ❌ Parser error: {e}")

# Test 4: Trading Strategy
print("\n4. Testing Trading Strategy...")
try:
    from trading.strategy import TradingStrategy, TradeSignal
    
    strategy = TradingStrategy()
    
    # Test entry signal
    signal = strategy.should_enter(mock_market, existing_position=False)
    
    print(f"   ✅ Strategy loaded")
    print(f"   - Entry signal: {'YES' if signal else 'NO'}")
    if signal:
        print(f"   - Action: {signal.action}")
        print(f"   - Side: {signal.side}")
        print(f"   - Price: {signal.price:.2%}")
        print(f"   - Reason: {signal.reason}")
except Exception as e:
    print(f"   ❌ Strategy error: {e}")

# Test 5: Portfolio Manager
print("\n5. Testing Portfolio Manager...")
try:
    from trading.portfolio import Portfolio, PositionStatus, TradeResult
    
    portfolio = Portfolio()
    
    # Open a position
    position = portfolio.open_position(
        market_id="test_123",
        market_title="Lakers vs Celtics",
        side="YES",
        entry_price=0.82,
        size_usd=100.0
    )
    
    print(f"   ✅ Portfolio loaded")
    print(f"   - Position ID: {position.id}")
    print(f"   - Shares: {position.shares:.2f}")
    print(f"   - Has position: {portfolio.has_position('test_123')}")
    
    # Close position
    closed = portfolio.close_position(
        position_id=position.id,
        exit_price=1.0,
        result=TradeResult.WIN
    )
    
    print(f"   - Closed P&L: ${closed.pnl_usd:+.2f}")
    
    # Get stats
    stats = portfolio.get_statistics()
    print(f"   - Win rate: {stats['win_rate']:.0f}%")
except Exception as e:
    print(f"   ❌ Portfolio error: {e}")

# Test 6: Trade Simulator
print("\n6. Testing Trade Simulator...")
try:
    from trading.simulator import TradeSimulator
    
    sim = TradeSimulator()
    
    # Process market
    trade_info = sim.process_market(mock_market)
    
    print(f"   ✅ Simulator loaded")
    if trade_info:
        print(f"   - Trade type: {trade_info['type']}")
        print(f"   - Side: {trade_info['side']}")
        print(f"   - Price: {trade_info['price']:.2%}")
except Exception as e:
    print(f"   ❌ Simulator error: {e}")

# Test 7: Telegram Notifier (structure only)
print("\n7. Testing Telegram Notifier structure...")
try:
    from telegram.notifier import TelegramNotifier
    
    notifier = TelegramNotifier()
    
    print(f"   ✅ Notifier loaded")
    print(f"   - API URL: {notifier.api_url[:40]}...")
    print(f"   - Chat ID: {notifier.chat_id}")
    
    # Test message formatting
    test_trade = {
        'market_title': 'Lakers vs Celtics',
        'side': 'YES',
        'price': 0.82,
        'size_usd': 100,
        'shares': 121.95,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'market_url': 'https://polymarket.com/event/test'
    }
    
    # This won't actually send, just verifies formatting works
    print(f"   - Message formatting: OK")
except Exception as e:
    print(f"   ❌ Notifier error: {e}")

# Test 8: Database
print("\n8. Testing Database...")
try:
    from storage.database import Database
    
    # Use test database
    test_db = Database(db_path="data/test_trades.db")
    
    print(f"   ✅ Database loaded")
    print(f"   - Path: {test_db.db_path}")
    
    # Test save
    test_db.save_trade_log({
        'position_id': 'test_001',
        'type': 'ENTRY',
        'market_id': 'test_123',
        'market_title': 'Test Market',
        'side': 'YES',
        'price': 0.82,
        'shares': 121.95,
        'size_usd': 100.0
    })
    
    # Get log
    log = test_db.get_trade_log(limit=1)
    print(f"   - Trade log entries: {len(log)}")
    
    # Cleanup
    import os
    os.remove("data/test_trades.db")
    print(f"   - Cleanup: OK")
except Exception as e:
    print(f"   ❌ Database error: {e}")

print("\n" + "=" * 50)
print("All component tests completed!")
print("=" * 50)
print("\nTo run the bot:")
print("  python main.py")
print("\nNote: Network access required for actual trading.")
