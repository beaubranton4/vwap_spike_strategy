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
import random
import traceback
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
        
        # Initialize tracking variables
        self.message_buffer: List[str] = []
        self.is_running = False
        self.message_count = 0
        self.stream_start_time: Optional[datetime] = None
        self.active_short_positions = {}  # {symbol: entry_price}
        self.closed_positions = set()
        self.last_known_prices = {}
        self.symbols_to_remove = set()
        
        # Set up timezone
        self.et_timezone = pytz.timezone('US/Eastern')
        
        # Initialize streamer first
        if not use_mock_data:
            self._setup_authentication()
            self._initialize_client()
            self.streamer = self.client.stream
        else:
            logger.info("Initializing with mock data streamer")
            # Set up simulated start time at midnight ET today
            today = datetime.now(self.et_timezone).date()
            start_time = datetime.combine(today, datetime.strptime("00:00", "%H:%M").time())
            start_time = self.et_timezone.localize(start_time)
            
            self.streamer = MockMarketDataStreamer(
                symbols=[],  # Empty list for now, will be populated later
                base_prices={},  # Empty dict for now, will be populated later
                start_time=start_time,
                time_multiplier=60
            )
        
        # Now we can safely get market times
        self.market_open_time = self._get_market_open_time()
        self.strategy_end_time = self._get_strategy_end_time()
        self.premarket_highs = {}
        
        # Add DataFrame to track all events
        self.trading_events = pd.DataFrame({
            'timestamp': pd.Series(dtype='str'),
            'symbol': pd.Series(dtype='str'),
            'price': pd.Series(dtype='float64'),
            'event_type': pd.Series(dtype='str'),
            'details': pd.Series(dtype='str')
        })
        
        # Add DataFrame to track all price data
        self.price_history = pd.DataFrame(columns=[
            'timestamp',
            'symbol',
            'price',
            'simulated_time'
        ])

        # Add last_position_print_time to track when we last printed positions
        self.last_position_print_time = datetime.now(self.et_timezone)

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
        """Calculate strategy end time based on market close and configured threshold - take earlier of strategy end and market close"""
        try:
            # Get NYSE schedule
            nyse = mcal.get_calendar('NYSE')
            
            # Use simulated time if mock data is enabled
            if self.use_mock_data and hasattr(self, 'streamer'):
                today = self.streamer.get_current_time().date()
            else:
                today = datetime.now().date()
                
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
            
            # Get market close time
            market_close = schedule.iloc[0]['market_close'].tz_convert('US/Eastern')
            
            # Get the time from the SELL_TIME_THRESHOLD list
            sell_time = SELL_TIME_THRESHOLD[0]  # Get first (and presumably only) time object from list
                
            # Get strategy cutoff time using appropriate time source
            if self.use_mock_data and hasattr(self, 'streamer'):
                now = self.streamer.get_current_time()
            else:
                now = datetime.now(self.et_timezone)
                
            strategy_cutoff = now.replace(
                hour=sell_time.hour,
                minute=sell_time.minute,
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
            # Default to 3:30 PM ET using appropriate time source
            if self.use_mock_data and hasattr(self, 'streamer'):
                now = self.streamer.get_current_time()
            else:
                now = datetime.now(self.et_timezone)
            default_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            logger.warning(f"Using default end time: {default_close.strftime('%H:%M:%S')} ET")
            return default_close

    def _get_market_open_time(self) -> datetime:
        """Get market open time from NYSE calendar"""
        try:
            nyse = mcal.get_calendar('NYSE')
            
            # Use simulated time if mock data is enabled
            if self.use_mock_data and hasattr(self, 'streamer'):
                today = self.streamer.get_current_time().date()
            else:
                today = datetime.now().date()
                
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
            
            open_time = schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
            logger.info(f"Market opens at: {open_time.strftime('%H:%M:%S')} ET")
            return open_time
            
        except Exception as e:
            logger.error(f"Error getting market open time: {e}")
            # Default to 9:30 AM ET using appropriate time source
            if self.use_mock_data and hasattr(self, 'streamer'):
                now = self.streamer.get_current_time()
            else:
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
        """Check if strategy should still be active"""
        if self.use_mock_data and hasattr(self, 'streamer'):
            current_time = self.streamer.get_current_time()
        else:
            current_time = datetime.now(self.et_timezone)
        
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
        """Process market data messages during regular trading"""
        try:
            for rtype, services in message.items():
                if rtype == "data":
                    for service in services:
                        contents = service.get("content", [])
                        simulated_time = service.get("simulated_time", None)
                        
                        # Get current time based on mode
                        if self.use_mock_data and simulated_time:
                            current_time = datetime.strptime(simulated_time, '%Y-%m-%d %H:%M:%S')
                            current_time = self.et_timezone.localize(current_time)
                        else:
                            current_time = datetime.now(self.et_timezone)
                        
                        # Print positions once per minute
                        if (current_time - self.last_position_print_time).total_seconds() >= 60:
                            logger.info("\n" + "="*50)
                            logger.info(f"Position Update - {current_time.strftime('%H:%M:%S')} ET")
                            logger.info(f"Active Positions: {self.active_short_positions}")
                            logger.info(f"Closed Positions: {self.closed_positions}")
                            logger.info("="*50 + "\n")
                            self.last_position_print_time = current_time
                        
                        # Process each symbol's data
                        for content in contents:
                            if content.get('key') and content.get('1'):
                                symbol = content.get('key')
                                price = float(content.get('1'))
                                
                                # Track price history for mock data
                                if self.use_mock_data:
                                    new_price = pd.DataFrame([{
                                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                        'symbol': symbol,
                                        'price': price,
                                        'simulated_time': simulated_time
                                    }])
                                    self.price_history = pd.concat([self.price_history, new_price], ignore_index=True)
                                
                                # Update last known price
                                self.last_known_prices[symbol] = price
                                
                                # Check if symbol is eligible for trading
                                if symbol in self.df['Ticker'].values and symbol not in self.symbols_to_remove:
                                    symbol_data = self.df.loc[self.df['Ticker'] == symbol].iloc[0]
                                
                                    
                                    # Check if we're in market hours
                                    market_hours = (self.market_open_time.time() <= current_time.time() <= 
                                                  self.strategy_end_time.time())
                                    
                                    if market_hours:
                                        if symbol in self.active_short_positions:
                                            # Check exit conditions for active positions
                                            self._check_exit_conditions(symbol, price, symbol_data, current_time)
                                        else:
                                            # Check entry conditions for new positions
                                            self._check_entry_conditions(symbol, price, symbol_data, current_time)
                            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.error(f"Message content: {message}")

    def handle_market_data(self, services: List[Dict[str, Any]]) -> None:
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
        if symbol in self.active_short_positions and symbol not in self.closed_positions:
            entry_price = self.active_short_positions[symbol]
            
            # Calculate stop and target prices based on entry price
            stop_price = entry_price * (1 + STOP[0])  # Add percentage for stop loss (going up)
            target_price = entry_price * (1 - TARGET[0])  # Subtract percentage for profit target (going down)
            
            if price >= stop_price or price <= target_price:
                logger.info(f"\n{'='*50}")
                if price >= stop_price:
                    logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                              f"${price:.2f} | 📉 Stop loss hit at ${stop_price:.2f} | Entry: ${entry_price:.2f}")
                else:
                    logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                              f"${price:.2f} | 📈 Profit target at ${target_price:.2f} | Entry: ${entry_price:.2f}")
                logger.info(f"{'='*50}\n")
                
                # Add to closed positions
                self.closed_positions.add(symbol)
                
                # Track the exit
                new_event = pd.DataFrame([{
                    'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'symbol': symbol,
                    'price': price,
                    'event_type': 'COVER_SHORT',
                    'details': f"{'Stop loss' if price >= stop_price else 'Profit target'} hit | " +
                              f"Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f} | Target: ${target_price:.2f}"
                }])
                self.trading_events = pd.concat([self.trading_events, new_event], ignore_index=True)

    def _check_entry_conditions(self, symbol: str, price: float, symbol_data: pd.Series,
                              current_time: datetime) -> None:
        """Check if new short position should be opened"""
        try:
            if symbol in self.active_short_positions:
                logger.info(f"\n{'='*50}")
                logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                    f"${price:.2f} | NO SIGNAL - Stock is already Shorted @ ${self.active_short_positions[symbol]:.2f}")
                logger.info(f"{'='*50}\n")
                return
                
            if price < symbol_data['Target Entry']:
                logger.info(f"\n{'='*50}")
                logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                    f"${price:.2f} | NO SIGNAL - Price did not hit target")
                logger.info(f"{'='*50}\n")
                return

            if (price > symbol_data['Target Entry'] and 
                symbol not in self.active_short_positions and 
                symbol not in self.closed_positions):
                
                logger.info(f"\n{'='*50}")
                logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                          f"${price:.2f} | 🔴 SHORT SIGNAL | Target: ${symbol_data['Target Entry']:.2f}")
                
                # Place the short order only if not using mock data
                if not self.use_mock_data:
                    limit_price = max(symbol_data['Target Entry'], price)
                    quantity = 1
                    
                    try:
                        order_result = place_short_order(self.client, symbol, quantity, limit_price)
                        
                        # Only add to active positions if order was successful
                        if order_result.get('status') == 'SUCCESS':
                            logger.info(f"✅ Order successfully placed and confirmed")
                            self.active_short_positions[symbol] = price  # Store entry price
                        else:
                            logger.error(f"❌ Order placement failed: {order_result.get('message', 'Unknown error')}")
                        
                    except Exception as e:
                        logger.error(f"❌ Error during order placement: {str(e)}")
                
                else:
                    logger.info(f"✅ Mock data mode: Order would have been placed")
                    self.active_short_positions[symbol] = price  # Store entry price

                # Track the signal regardless of mock/real mode
                new_event = pd.DataFrame([{
                    'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'symbol': symbol,
                    'price': price,
                    'event_type': 'SHORT_SIGNAL',
                    'details': f"Price ${price:.2f} crossed above Target Entry ${symbol_data['Target Entry']:.2f}"
                }])
                self.trading_events = pd.concat([self.trading_events, new_event], ignore_index=True)
                
                logger.info(f"{'='*50}\n")
                
                # Important: Keep the stream alive by not blocking
                sleep(0.1)  # Small delay to prevent overwhelming the system
                    
        except Exception as e:
            logger.error(f"Error in entry conditions for {symbol}: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")

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
        # Get current time based on mode
        if self.use_mock_data and hasattr(self, 'streamer'):
            current_time = self.streamer.get_current_time()
        else:
            current_time = datetime.now(self.et_timezone)
        
        seconds_to_close = (self.strategy_end_time - current_time).total_seconds()
        print(f"Seconds to close: {seconds_to_close}")
        if seconds_to_close <= 30:
            remaining_positions = set(self.active_short_positions.keys()) - self.closed_positions
            if remaining_positions:
                logger.info(f"\n{'='*50}")
                logger.info(f"{current_time.strftime('%H:%M:%S')} ET | END OF DAY CLOSING")
                logger.info(f"Closing {len(remaining_positions)} positions")
                
                for symbol in remaining_positions:
                    current_price = float(self.last_known_prices.get(symbol, 0))
                    entry_price = self.active_short_positions[symbol]
                    
                    logger.info(f"{symbol}: ${current_price:.2f} | Entry: ${entry_price:.2f} | ⏰ END OF DAY CLOSE")
                    
                    # Add to trading events
                    new_event = pd.DataFrame([{
                        'timestamp': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'symbol': symbol,
                        'price': current_price,
                        'event_type': 'EOD_CLOSE',
                        'details': f'End of day position close at ${current_price:.2f}'
                    }])
                    self.trading_events = pd.concat([self.trading_events, new_event], ignore_index=True)
                    
                    # Add to closed positions
                    self.closed_positions.add(symbol)
                
                logger.info(f"{'='*50}\n")

    def execute_vwap_spike_strategy(self, df: pd.DataFrame) -> None:
        """Main method to execute the VWAP spike trading strategy"""
        try:
            self.df = df
            
            # Print initial stock list in a clean format
            logger.info("\n" + "="*50)
            logger.info("Starting Strategy with Stocks:")
            for _, row in df.iterrows():
                logger.info(f"{row['Ticker']:<6} | Target Entry: ${row['Target Entry']:.2f}")
            logger.info("="*50 + "\n")

            pre_market_symbols = df['Ticker'].unique().tolist()

            if self.use_mock_data:
                # Generate base prices for mock data
                base_prices = {}
                for symbol in pre_market_symbols:
                    target_entry = df.loc[df['Ticker'] == symbol, 'Target Entry'].iloc[0]
                    discount = random.uniform(0.001, 0.02)  # 0.1% to 2% discount
                    base_prices[symbol] = target_entry * (1 - discount)
                
                # Update mock streamer configuration
                self.streamer.symbols = pre_market_symbols
                self.streamer.base_prices = base_prices
            
            # First track pre-market highs and filter stocks
            logger.info("Starting pre-market tracking phase...")
            filtered_df = self.track_premarket_highs(df)
            
            # Update streamer with filtered symbols
            symbols = filtered_df['Ticker'].unique().tolist()
            
            # Start the main trading stream
            logger.info("\n" + "="*50)
            logger.info("Starting main trading stream...")
            logger.info(f"Tracking {len(symbols)} symbols")
            logger.info(f"Market open: {self.market_open_time.strftime('%H:%M:%S')} ET")
            logger.info(f"Strategy end: {self.strategy_end_time.strftime('%H:%M:%S')} ET")
            logger.info("="*50 + "\n")
            
            self.streamer.start(self.handle_stream_message)
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.L1_FIELDS
            ))
            
            self.is_running = True
            while self.is_running and self.get_current_time() < self.strategy_end_time:
                if self.use_mock_data:
                    mock_message = self.streamer.generate_mock_message()
                    self.handle_stream_message(mock_message)
                
                while self.message_buffer:
                    try:
                        message = json.loads(self.message_buffer.pop(0))
                        self.process_message(message)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                
                # Check for end of day positions
                self.check_end_of_day_positions()
                
                sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)
                
        except Exception as e:
            logger.error(f"Error in strategy execution: {e}")
            raise
            
        finally:
            # Export trading events and price history
            if hasattr(self, 'trading_events') and not self.trading_events.empty:
                # Export trading events
                if not os.path.exists('mock_stream'):
                    os.makedirs('mock_stream')
                    
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                events_filename = f'mock_stream/trading_events_{timestamp}.xlsx'
                prices_filename = f'mock_stream/details_{timestamp}.xlsx'
                
                # Export trading events
                with pd.ExcelWriter(events_filename, engine='openpyxl') as writer:
                    self.trading_events.to_excel(writer, sheet_name='All Events', index=False)
                    summary = self.trading_events['event_type'].value_counts()
                    summary.to_frame('Count').to_excel(writer, sheet_name='Event Summary')
                    symbol_summary = self.trading_events.groupby(['symbol', 'event_type']).size().unstack(fill_value=0)
                    symbol_summary.to_excel(writer, sheet_name='Symbol Summary')
                
                # Export price history
                if hasattr(self, 'price_history') and not self.price_history.empty:
                    with pd.ExcelWriter(prices_filename, engine='openpyxl') as writer:
                        # All price data
                        self.price_history.to_excel(writer, sheet_name='All Prices', index=False)
                        
                        # Price summary by symbol
                        price_summary = self.price_history.groupby('symbol').agg({
                            'price': ['min', 'max', 'mean', 'std']
                        }).round(4)
                        price_summary.columns = ['Min Price', 'Max Price', 'Avg Price', 'Std Dev']
                        price_summary.to_excel(writer, sheet_name='Price Summary')
                        
                        # Price movement by time
                        pivot_table = self.price_history.pivot_table(
                            values='price',
                            index='simulated_time',
                            columns='symbol',
                            aggfunc='first'
                        )
                        pivot_table.to_excel(writer, sheet_name='Price Timeline')
                
                logger.info(f"Trading events saved to {events_filename}")
                logger.info(f"Price details saved to {prices_filename}")
            
            if hasattr(self, 'streamer') and self.streamer is not None:
                self.streamer.stop()

######################### PRE-MARKET TRACKING ######################### 

    def track_premarket_highs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Track pre-market highs and filter stocks before market open"""
        self.df = df.copy()
        self.message_buffer = []
        self.symbols_to_remove = set()
        
        logger.info("\n" + "="*50)
        logger.info("Starting pre-market tracking...")
        logger.info(f"Initial symbols: {len(self.df)}")
        logger.info(f"Current time: {self.get_current_time().strftime('%H:%M:%S')} ET")
        logger.info(f"Market opens at: {self.market_open_time.strftime('%H:%M:%S')} ET")
        logger.info("="*50 + "\n")
        
        try:
            self.streamer.start(self.handle_stream_message)
            symbols = self.df['Ticker'].unique().tolist()
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.L1_FIELDS
            ))
            
            self.is_running = True
            start_time = datetime.now()
            last_status_time = start_time
            
            while self.is_running and self.get_current_time() < self.market_open_time:
                if self.use_mock_data:
                    mock_message = self.streamer.generate_mock_message()
                    self.handle_stream_message(mock_message)
                
                while self.message_buffer:
                    try:
                        message = json.loads(self.message_buffer.pop(0))
                        self.process_premarket_message(message)
                    except Exception as e:
                        logger.error(f"Error processing pre-market message: {e}")
                
                current_time = self.get_current_time()
                if (current_time - last_status_time.astimezone(self.et_timezone)).seconds >= 3600:  # 1 hour
                    self.print_premarket_status(current_time)
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
        try:
            for rtype, services in message.items():
                if rtype == "data":
                    for service in services:
                        contents = service.get("content", [])
                        simulated_time = service.get("simulated_time", "Unknown time")
                        
                        for content in contents:
                            if content.get('key') and content.get('1'):
                                symbol = content.get('key')
                                current_price = float(content.get('1'))
                                
                                # Initialize premarket_highs for the symbol if not exists
                                if symbol not in self.premarket_highs:
                                    self.premarket_highs[symbol] = current_price
                                
                                if symbol in self.df['Ticker'].values and symbol not in self.symbols_to_remove:
                                    yesterday_high = self.df.loc[
                                        self.df['Ticker'] == symbol, 
                                        'Yesterday High'
                                    ].iloc[0]
                                    
                                    # Update premarket high if current price is higher
                                    if current_price > self.premarket_highs[symbol]:
                                        self.premarket_highs[symbol] = current_price
                                        logger.info(f"{simulated_time} | {symbol} New high: ${current_price:.2f} | Yesterday High: ${yesterday_high:.2f}")
                                    
                                    if self.premarket_highs[symbol] > yesterday_high:
                                        # Track removal event
                                        new_event = pd.DataFrame([{
                                            'timestamp': simulated_time,
                                            'symbol': symbol,
                                            'price': current_price,
                                            'event_type': 'REMOVED_PREMARKET',
                                            'details': f"Pre-market high ${self.premarket_highs[symbol]:.2f} breached yesterday's high ${yesterday_high:.2f}"
                                        }])
                                        self.trading_events = pd.concat([self.trading_events, new_event], ignore_index=True)
                                        self.symbols_to_remove.add(symbol)
                                        logger.info(f"{simulated_time} | {symbol} REMOVED - Breached yesterday's high")
        except Exception as e:
            logger.error(f"Error processing pre-market message: {str(e)}")
            logger.error(f"Message content: {message}")

    def print_premarket_status(self, simulated_time: datetime) -> None:
        """Print periodic pre-market status update using simulated time"""
        # Calculate hours until market open using simulated time
        hours_to_open = (self.market_open_time - simulated_time).total_seconds() / 3600
        
        logger.info("\n" + "="*50)
        logger.info(f"Pre-market status - {simulated_time.strftime('%H:%M:%S')} ET")
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
