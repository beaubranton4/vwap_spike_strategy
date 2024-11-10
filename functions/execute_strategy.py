from datetime import datetime, timedelta
import schwabdev
import logging
import dotenv
from time import sleep
import json
import os
import pytz
import signal
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from functions import *
from config import *
import pandas as pd
from functions.mock_market_data import MockMarketDataStreamer
# Use the format_tokens_for_client function from schwab_functions


dotenv.load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@dataclass
class ExecuteStrategyConfig:
    """Configuration settings for the market data stream"""
    MAX_RUNTIME: int = 120  # seconds
    HEARTBEAT_INTERVAL: int = 60  # seconds
    SLEEP_INTERVAL: float = 0.1  # seconds
    L1_FIELDS: str = "0,1"
    L2_FIELDS: str = "0,1,2,3"  # Level 2 fields

class ExecuteStrategy:
    """
    A class to execute real-time trading strategies by streaming market data.
    Handles authentication, market data streaming, and trade execution.
    """
    def __init__(self, use_mock_data: bool = False):
        """Initialize with option for mock data"""
        self.use_mock_data = use_mock_data
        dotenv.load_dotenv()
        
        if not use_mock_data:
            self._setup_authentication()
            self._initialize_client()
            self.streamer = self.client.stream
        else:
            logger.info("Initializing with mock data streamer")
            self.streamer = None  # Will be set in execute_vwap_spike_strategy
        
        # Initialize tracking variables
        self.message_buffer: List[str] = []
        self.is_running = False
        self.message_count = 0
        self.stream_start_time: Optional[datetime] = None
        self.active_short_positions = set()
        self.closed_positions = set()
        self.last_known_prices = {}
        
        # Set up timezone and market hours
        self.et_timezone = pytz.timezone('US/Eastern')
        self.market_open_time = self._get_market_open_time()
        self.strategy_end_time = self._get_strategy_end_time()
        self.premarket_highs = {}
        self.simulated_time = None  # Add this line
        
    def _setup_authentication(self):
        """Set up authentication tokens for Schwab API"""
        try:
            # Check if tokens file exists
            if not os.path.exists("auth/schwab_dev_tokens.json"):
                logger.error("schwab_dev_tokens.json not found in auth directory")
                raise FileNotFoundError("schwab_dev_tokens.json not found")
                
            logger.info("Authentication tokens found")
                
        except Exception as e:
            logger.error(f"Token setup error: {e}")
            raise

    def _initialize_client(self):
        """Initialize Schwab API client"""
        try:
            app_key = os.getenv('appKey')
            app_secret = os.getenv('appSecret')
            callback_url = os.getenv('callback_url')
            
            if not all([app_key, app_secret, callback_url]):
                raise ValueError("Missing required environment variables")
            
            # Initialize client
            self.client = schwabdev.Client(
                app_key,
                app_secret,
                callback_url,
                tokens_file="auth/schwab_dev_tokens.json",
                timeout=10,
                update_tokens_auto=True
            )
            
            logger.info("Client initialized successfully")
            
        except Exception as e:
            logger.error(f"Client initialization error: {e}")
            raise

    def _get_strategy_end_time(self) -> datetime:
        """Calculate strategy end time based on market close and configured threshold"""
        try:
            # Get NYSE schedule
            nyse = mcal.get_calendar('NYSE')
            today = datetime.now().date()
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
            
            # Get market close time
            market_close = schedule.iloc[0]['market_close'].tz_convert('US/Eastern')
            
            # Get strategy cutoff time
            now = datetime.now(self.et_timezone)
            strategy_cutoff = now.replace(
                hour=SELL_TIME_THRESHOLD.hour,
                minute=SELL_TIME_THRESHOLD.minute,
                second=0,
                microsecond=0
            )
            
            # Use earlier of market close or cutoff
            strategy_end = min(market_close, strategy_cutoff)
            
            logger.info(f"Market closes at: {market_close.strftime('%H:%M:%S')} ET")
            logger.info(f"Strategy ends at: {strategy_end.strftime('%H:%M:%S')} ET")
            return strategy_end
            
        except Exception as e:
            logger.error(f"Error getting strategy end time: {e}")
            # Default to 3:30 PM ET
            now = datetime.now(self.et_timezone)
            default_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            logger.warning(f"Using default end time: {default_close.strftime('%H:%M:%S')} ET")
            return default_close

    def _get_market_open_time(self) -> datetime:
        """Get market open time from NYSE calendar"""
        try:
            nyse = mcal.get_calendar('NYSE')
            today = datetime.now().date()
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
            
            open_time = schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
            logger.info(f"Market opens at: {open_time.strftime('%H:%M:%S')} ET")
            return open_time
            
        except Exception as e:
            logger.error(f"Error getting market open time: {e}")
            # Default to 9:30 AM ET
            now = datetime.now(self.et_timezone)
            default_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            logger.warning(f"Using default open time: {default_open.strftime('%H:%M:%S')} ET")
            return default_open

    def get_current_time(self) -> datetime:
        """Get either real or simulated time"""
        if self.use_mock_data and hasattr(self, 'streamer'):
            return self.streamer.get_current_time()
        return datetime.now(self.et_timezone)
        
    def is_strategy_active(self) -> bool:
        """Check if strategy should still be running"""
        current_time = self.get_current_time()
        return current_time < self.strategy_end_time

    def handle_stream_message(self, message: str) -> None:
        """Callback handler for stream messages"""
        self.message_buffer.append(message)

    def setup_signal_handlers(self) -> None:
        """Set up handlers for graceful shutdown on system signals"""
        def signal_handler(signum, frame):
            logger.info("\nShutdown signal received. Cleaning up...")
            self.is_running = False
            self.streamer.stop()
            logger.info("Stream stopped. Exiting...")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def process_message(self, message: Dict[str, Any]) -> None:
        """Process messages from the market data stream"""
        for msg_type, services in message.items():
            if msg_type == "data":
                self._handle_market_data(services)
            elif msg_type == "response":
                logger.info(f"Response received: {services}")
            elif msg_type == "notify":
                logger.debug(f"Heartbeat received: {services}")
            else:
                logger.warning(f"Unknown message type: {message}")

    def _handle_market_data(self, services: List[Dict[str, Any]]) -> None:
        """Process market data messages and execute trading logic"""
        for service in services:
            contents = service.get("content", [])
            
            for content in contents:
                if content.get('key') and content.get('1'):
                    symbol = content.get('key')
                    price = content.get('1')
                    
                    current_time = datetime.now(self.et_timezone)
                    
                    try:
                        if symbol in self.df['Ticker'].values:
                            current_price = float(price)
                            self.last_known_prices[symbol] = current_price
                            
                            # Get trading parameters for symbol
                            symbol_data = self.df[self.df['Ticker'] == symbol].iloc[0]
                            
                            # Check existing positions
                            if symbol in self.active_short_positions and symbol not in self.closed_positions:
                                self._check_exit_conditions(symbol, current_price, symbol_data, current_time)
                                continue
                            
                            # Check entry conditions
                            self._check_entry_conditions(symbol, current_price, symbol_data, current_time)
                            
                    except Exception as e:
                        logger.error(f"Error processing {symbol}: {e}")

    def _check_exit_conditions(self, symbol: str, price: float, symbol_data: pd.Series, 
                             current_time: datetime) -> None:
        """Check if position should be closed based on price targets"""
        if price >= symbol_data['Stop Price'] or price <= symbol_data['Sell Price']:
            print(f"\n{'='*50}")
            if price >= symbol_data['Stop Price']:
                print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                      f"${price:.4f} | 📉 Stop loss hit at ${symbol_data['Stop Price']:.4f}")
            else:
                print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                      f"${price:.4f} | 📈 Profit target at ${symbol_data['Sell Price']:.4f}")
            print(f"{'='*50}\n")
            
            self.closed_positions.add(symbol)
        else:
            print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                  f"${price:.4f} | NO SIGNAL - Already short")

    def _check_entry_conditions(self, symbol: str, price: float, symbol_data: pd.Series,
                              current_time: datetime) -> None:
        """Check if new short position should be opened"""
        market_hours = (self.market_open_time.time() <= current_time.time() <= 
                       self.strategy_end_time.time())
        
        if (price > symbol_data['Target Entry'] and 
            symbol not in self.closed_positions and
            market_hours):
            
            print(f"\n{'='*50}")
            print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                  f"${price:.4f} | 🔴 SHORT SIGNAL | Target: ${symbol_data['Target Entry']:.4f}")
            print(f"{'='*50}\n")
            
            self.active_short_positions.add(symbol)
        else:
            print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                  f"${price:.4f} | NO SIGNAL - Below ${symbol_data['Target Entry']:.4f}")

    def print_status_update(self) -> None:
        """Print periodic performance statistics"""
        if not self.stream_start_time:
            return
            
        elapsed_time = (datetime.now() - self.stream_start_time).seconds
        if elapsed_time > 0 and elapsed_time % ExecuteStrategyConfig.HEARTBEAT_INTERVAL == 0:
            logger.info("\nStatus Update:")
            logger.info(f"Running time: {elapsed_time} seconds")
            logger.info(f"Messages received: {self.message_count}")
            logger.info(f"Messages per second: {self.message_count/elapsed_time:.2f}")

    def check_end_of_day_positions(self) -> None:
        """Close any remaining positions at strategy end time"""
        current_time = datetime.now(self.et_timezone)
        seconds_to_close = (self.strategy_end_time - current_time).total_seconds()
        
        if seconds_to_close <= 30:
            for symbol in self.active_short_positions - self.closed_positions:
                current_price = float(self.last_known_prices.get(symbol, 0))
                
                print(f"\n{'='*50}")
                print(f"{current_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: "
                      f"${current_price:.4f} | ❓ COVERED SHORT (End of Day)")
                print(f"{'='*50}\n")
                
                self.closed_positions.add(symbol)

    def execute_vwap_spike_strategy(self, df: pd.DataFrame) -> None:
        """Main method to execute the VWAP spike trading strategy"""
        try:
            self.df = df
            self.setup_signal_handlers()
            
            symbols = df['Ticker'].unique().tolist()
            
            # Initialize real or mock streamer
            if self.use_mock_data:
                # Set up simulated start time at midnight ET today
                today = datetime.now(self.et_timezone).date()
                start_time = datetime.combine(today, datetime.strptime("00:00", "%H:%M").time())
                start_time = self.et_timezone.localize(start_time)
                
                base_prices = {
                    row['Ticker']: row['Last Price'] 
                    for _, row in df.iterrows()
                }
                self.streamer = MockMarketDataStreamer(
                    symbols=symbols,
                    base_prices=base_prices,
                    start_time=start_time,
                    time_multiplier=60  # Run 60x faster than real-time
                )
                logger.info("Using mock market data streamer")
            
            start_time = self.get_current_time()
            logger.info(f"Strategy starting at {start_time.strftime('%H:%M:%S')} ET")
            logger.info(f"Running until {self.strategy_end_time.strftime('%H:%M:%S')} ET")
            
            # Track pre-market data if using mock streamer
            if self.use_mock_data:
                self.track_premarket_highs(df)
            
            self.streamer.start(self.handle_stream_message)
            
            # Subscribe to market data
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.L1_FIELDS
            ))

            self.is_running = True
            self.stream_start_time = datetime.now()

            # Main processing loop
            while self.is_running and self.is_strategy_active():
                self.check_end_of_day_positions()
                
                # Generate mock data if using mock streamer
                if self.use_mock_data:
                    mock_message = self.streamer.generate_mock_message()
                    self.handle_stream_message(mock_message)
                
                while self.message_buffer:
                    try:
                        message = json.loads(self.message_buffer.pop(0))
                        self.message_count += 1
                        self.process_message(message)
                    except Exception as e:
                        logger.error(f"Message processing error: {e}")
                
                sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)

        except Exception as e:
            logger.error(f"Strategy execution error: {e}")
        finally:
            self.check_end_of_day_positions()
            end_time = datetime.now(self.et_timezone)
            logger.info(f"\nStrategy completed at {end_time.strftime('%H:%M:%S')} ET")
            self.streamer.stop()

######################### PRE-MARKET TRACKING ######################### 

    def track_premarket_highs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Track pre-market highs and filter stocks before market open"""
        self.df = df.copy()
        self.shared_list = []
        self.symbols_to_remove = set()
        
        logger.info("\n" + "="*50)
        logger.info("Starting pre-market tracking...")
        logger.info(f"Initial symbols: {len(self.df)}")
        logger.info(f"Current time: {datetime.now(self.et_timezone).strftime('%H:%M:%S')} ET")
        logger.info(f"Market opens at: {self.market_open_time.strftime('%H:%M:%S')} ET")
        logger.info("="*50 + "\n")
        
        try:
            self.streamer.start(self.response_handler)
            symbols = self.df['Ticker'].unique().tolist()
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.L1_FIELDS
            ))
            
            self.running = True
            start_time = datetime.now()
            last_status_time = start_time
            
            while self.running and datetime.now(self.et_timezone) < self.market_open_time:
                while self.shared_list:
                    try:
                        message = json.loads(self.shared_list.pop(0))
                        self.process_premarket_message(message)
                    except Exception as e:
                        logger.error(f"Error processing pre-market message: {e}")
                
                # Print hourly status
                current_time = datetime.now()
                if (current_time - last_status_time).seconds >= 3600:  # 1 hour
                    self.print_premarket_status()
                    last_status_time = current_time
                
                sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)
            
            # Final summary before market open
            self.print_premarket_summary()
            
            # Remove filtered symbols and return updated DataFrame
            if self.symbols_to_remove:
                self.df = self.df[~self.df['Ticker'].isin(self.symbols_to_remove)]
            
            return self.df
            
        except Exception as e:
            logger.error(f"Error during pre-market tracking: {e}")
            raise
        finally:
            self.streamer.stop()

    def process_premarket_message(self, message: Dict[str, Any]) -> None:
        """Process pre-market data messages"""
        for rtype, services in message.items():
            if rtype == "data":
                for service in services:
                    contents = service.get("content", [])
                    for content in contents:
                        if content.get('key') and content.get('1'):
                            symbol = content.get('key')
                            current_price = float(content.get('1'))
                            
                            if symbol in self.df['Ticker'].values and symbol not in self.symbols_to_remove:
                                # Update pre-market high
                                if symbol not in self.premarket_highs:
                                    self.premarket_highs[symbol] = current_price
                                else:
                                    self.premarket_highs[symbol] = max(
                                        self.premarket_highs[symbol], 
                                        current_price
                                    )
                                
                                # Check against yesterday's high
                                yesterday_high = self.df.loc[
                                    self.df['Ticker'] == symbol, 
                                    'Yesterday High'
                                ].iloc[0]
                                
                                if self.premarket_highs[symbol] > yesterday_high:
                                    eastern_time = datetime.now(self.et_timezone)
                                    logger.info(f"\n{'='*50}")
                                    logger.info(f"{eastern_time.strftime('%H:%M:%S')} ET | {symbol} removed from watchlist")
                                    logger.info(f"Pre-market high: ${self.premarket_highs[symbol]:.2f}")
                                    logger.info(f"Yesterday high: ${yesterday_high:.2f}")
                                    logger.info(f"{'='*50}\n")
                                    self.symbols_to_remove.add(symbol)

    def print_premarket_status(self) -> None:
        """Print periodic pre-market status update"""
        eastern_time = datetime.now(self.et_timezone)
        hours_to_open = (self.market_open_time - eastern_time).seconds / 3600
        
        logger.info("\n" + "="*50)
        logger.info(f"Pre-market status - {eastern_time.strftime('%H:%M:%S')} ET")
        logger.info(f"Hours until market open: {hours_to_open:.1f}")
        logger.info(f"Symbols being tracked: {len(self.df) - len(self.symbols_to_remove)}")
        logger.info(f"Symbols removed: {len(self.symbols_to_remove)}")
        logger.info("="*50 + "\n")

    def print_premarket_summary(self) -> None:
        """Print final pre-market summary"""
        if self.symbols_to_remove:
            logger.info("\n" + "="*50)
            logger.info("Pre-market tracking completed")
            logger.info(f"Removed {len(self.symbols_to_remove)} symbols that exceeded yesterday's high:")
            for symbol in sorted(self.symbols_to_remove):
                logger.info(f"- {symbol}: Pre-market high ${self.premarket_highs[symbol]:.2f} > Yesterday high ${self.df.loc[self.df['Ticker'] == symbol, 'Yesterday High'].iloc[0]:.2f}")
            logger.info(f"Symbols remaining: {len(self.df)} → {len(self.df) - len(self.symbols_to_remove)}")
            logger.info("="*50 + "\n")
