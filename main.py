#!/usr/bin/env python3
"""
Polymarket NBA Trading Bot
Main entry point
"""

import sys
import time
import signal
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import (
    CHECK_INTERVAL, ENTRY_THRESHOLD, STOP_LOSS, 
    POSITION_SIZE, LOG_LEVEL, LOG_FILE
)
from polymarket.api import api
from polymarket.parser import parser
from trading.simulator import simulator
from telegram.notifier import notifier
from storage.database import db

# Setup logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, mode='a')
    ]
)
logger = logging.getLogger(__name__)


class NBABot:
    """
    Main bot class that orchestrates market scanning and trading
    """
    
    def __init__(self):
        self.running = False
        self.cycle_count = 0
        
    def start(self):
        """Start the bot"""
        logger.info("=" * 50)
        logger.info("Starting Polymarket NBA Trading Bot")
        logger.info("=" * 50)
        
        # Test Telegram connection
        if not notifier.test_connection():
            logger.error("Failed to connect to Telegram. Check your bot token.")
            return
        
        # Send startup notification
        notifier.notify_startup({
            'entry_threshold': int(ENTRY_THRESHOLD * 100),
            'stop_loss': int(STOP_LOSS * 100),
            'position_size': POSITION_SIZE,
            'check_interval': CHECK_INTERVAL
        })
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        
        self.running = True
        
        logger.info(f"Bot started. Checking markets every {CHECK_INTERVAL} seconds.")
        logger.info(f"Entry threshold: {ENTRY_THRESHOLD:.0%}")
        logger.info(f"Stop loss: {STOP_LOSS:.0%}")
        logger.info(f"Position size: ${POSITION_SIZE}")
        
        # Main loop
        while self.running:
            try:
                self._run_cycle()
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                notifier.notify_error(f"Ошибка в главном цикле: {str(e)}")
            
            # Wait for next cycle
            if self.running:
                time.sleep(CHECK_INTERVAL)
        
        logger.info("Bot stopped.")
    
    def _run_cycle(self):
        """Run one scan cycle"""
        self.cycle_count += 1
        logger.info(f"--- Cycle {self.cycle_count} ---")
        
        # 1. Fetch NBA markets
        markets = parser.fetch_nba_markets()
        logger.info(f"Found {len(markets)} NBA markets")
        
        if not markets:
            logger.warning("No NBA markets found")
            return
        
        # 2. Filter for likely live markets
        live_markets = [m for m in markets if parser.is_likely_live(m)]
        logger.info(f"Found {len(live_markets)} potentially live markets")
        
        # 3. Process each market
        for market in live_markets:
            try:
                self._process_market(market)
            except Exception as e:
                logger.error(f"Error processing market {market.question}: {e}")
        
        # 4. Check existing positions for exits
        self._check_open_positions(markets)
        
        # 5. Log statistics periodically
        if self.cycle_count % 10 == 0:
            stats = simulator.get_statistics()
            logger.info(f"Stats: {stats}")
    
    def _process_market(self, market):
        """Process a single market for potential entry"""
        market_id = market.id or market.condition_id
        
        # Skip if already have position
        if simulator.portfolio.has_position(market_id):
            return
        
        # Get best outcome
        best_side, best_price = market.best_outcome
        
        # Check if meets threshold
        if best_price >= ENTRY_THRESHOLD:
            logger.info(
                f"Signal detected: {market.question} - "
                f"{best_side} at {best_price:.1%}"
            )
            
            # Execute simulated trade
            trade_info = simulator.process_market(market)
            
            if trade_info and trade_info['type'] == 'ENTRY':
                # Save to database
                db.save_trade_log(trade_info)
                
                # Send Telegram notification
                notifier.notify_entry(trade_info)
                
                logger.info(f"Entered position: {trade_info}")
    
    def _check_open_positions(self, current_markets):
        """Check open positions for exit signals"""
        open_positions = simulator.get_open_positions()
        
        if not open_positions:
            return
        
        # Create market lookup
        market_lookup = {}
        for m in current_markets:
            market_lookup[m.id] = m
            market_lookup[m.condition_id] = m
        
        for position in open_positions:
            market = market_lookup.get(position.market_id)
            
            if not market:
                # Try to fetch market directly
                logger.debug(f"Market {position.market_id} not in current batch, fetching...")
                # For now, skip - in production would fetch individually
                continue
            
            # Check for exit signal
            trade_info = simulator.process_market(market)
            
            if trade_info and trade_info['type'] == 'EXIT':
                # Save to database
                db.save_trade_log(trade_info)
                
                # Update position in database
                db.save_position(position.to_dict())
                
                # Send Telegram notification
                notifier.notify_exit(trade_info)
                
                logger.info(f"Exited position: {trade_info}")
    
    def _handle_shutdown(self, signum, frame):
        """Handle shutdown signal"""
        logger.info(f"Received shutdown signal ({signum})")
        self.running = False
        
        # Send final statistics
        stats = simulator.get_statistics()
        notifier.notify_daily_summary(stats)


def main():
    """Main entry point"""
    # Ensure data directory exists
    Path("data").mkdir(exist_ok=True)
    
    bot = NBABot()
    bot.start()


if __name__ == "__main__":
    main()
