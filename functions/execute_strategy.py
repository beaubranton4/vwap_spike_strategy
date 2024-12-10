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

# Modify the setup_logger function
def setup_logger():
    """Set up logging with both file and console handlers"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Clear any existing handlers
    logger.handlers = []
    
    # Create logs/execute_strategy directory if it doesn't exist
    log_dir = 'logs/execute_strategy'
    os.makedirs(log_dir, exist_ok=True)
    
    # Create a unique log file name with timestamp and date
    et_tz = pytz.timezone('US/Eastern')
    timestamp = datetime.now(et_tz).strftime('%Y-%m-%d')
    log_file = f'{log_dir}/{timestamp}.log'
    
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # Create formatter with ET timezone
    class ETFormatter(logging.Formatter):
        def converter(self, timestamp):
            dt = datetime.fromtimestamp(timestamp)
            et_tz = pytz.timezone('US/Eastern')
            return dt.astimezone(et_tz).timetuple()
            
        def formatTime(self, record, datefmt=None):
            dt = self.converter(record.created)
            if datefmt:
                return datetime(*dt[:6]).strftime(datefmt)
            return datetime(*dt[:6]).strftime('%Y-%m-%d %H:%M:%S ET')
            
    formatter = ETFormatter('%(asctime)s | %(levelname)s | %(message)s')
    
    # Add formatter to handlers
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized. Log file: {log_file}")
    return logger

@dataclass
class ExecuteStrategyConfig:
    """Configuration settings for the market data stream"""
    MAX_RUNTIME: int = 120  # seconds
    HEARTBEAT_INTERVAL: int = 60  # seconds
    SLEEP_INTERVAL: float = 0.1  # seconds
    L1_FIELDS: str = "0,1"
    L2_FIELDS: str = "0,1,2,3"  # Level 2 fields

class InsufficientFundsError(Exception):
    pass

class ExecuteStrategy:
    """
    A class to execute real-time trading strategies by streaming market data.
    Handles authentication, market data streaming, and trade execution.
    """
    def __init__(self, use_mock_data: bool = False):
        """Initialize with option for mock data"""
        # Setup logger first
        self.logger = setup_logger()
        
        self.use_mock_data = use_mock_data
        dotenv.load_dotenv()
        
        # Initialize tracking variables
        self.message_buffer: List[str] = []
        self.is_running = False
        self.message_count = 0
        self.stream_start_time: Optional[datetime] = None
        self.active_short_positions = {}  # {symbol: {'entry_price': float, 'trade_time': datetime}}
        self.closed_positions = set()
        self.last_known_prices = {}
        self.symbols_to_remove = set()
        
        # Set up timezone
        self.et_timezone = pytz.timezone('US/Eastern')
        
        # Initialize client for both mock and real modes
        try:
            self._setup_authentication()
            self._initialize_client()
        except Exception as e:
            if not use_mock_data:
                raise
            else:
                self.logger.warning(f"Failed to initialize real client in mock mode: {e}")
                self.client = None
        
        # Initialize streamer
        if not use_mock_data:
            self.streamer = self.client.stream
        else:
            self.logger.info("Initializing with mock data streamer")
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
        
        # Initialize trading_events with explicit dtypes
        self.trading_events = pd.DataFrame({
            'timestamp': pd.Series(dtype='datetime64[ns]'),
            'symbol': pd.Series(dtype='str'),
            'price': pd.Series(dtype='float64'),
            'event_type': pd.Series(dtype='str'),
            'details': pd.Series(dtype='str')
        })

        # Add last_position_print_time to track when we last printed positions
        self.last_position_print_time = datetime.now(self.et_timezone)

    def _setup_authentication(self):
        """Set up authentication tokens for Schwab API"""
        try:
            # Check if tokens file exists
            if not os.path.exists("auth/schwab_dev_tokens.json"):
                self.logger.error("schwab_dev_tokens.json not found in auth directory")
                raise FileNotFoundError("schwab_dev_tokens.json not found")
                
            self.logger.info("Authentication tokens found")
                
        except Exception as e:
            self.logger.error(f"Token setup error: {e}")
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
            
            self.logger.info("Client initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Client initialization error: {e}")
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
            sell_time = market_close # Get first (and presumably only) time object from list
                
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
            # strategy_end = min(market_close, strategy_cutoff)
            strategy_end = strategy_cutoff
            
            self.logger.info(f"Market closes at: {market_close.strftime('%H:%M:%S')} ET")
            self.logger.info(f"Strategy ends at: {strategy_end.strftime('%H:%M:%S')} ET")
            return strategy_end
            
        except Exception as e:
            self.logger.error(f"Error getting strategy end time: {e}")
            # Default to 4:00 PM ET using appropriate time source
            if self.use_mock_data and hasattr(self, 'streamer'):
                now = self.streamer.get_current_time()
            else:
                now = datetime.now(self.et_timezone)
            default_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            self.logger.warning(f"Using default end time: {default_close.strftime('%H:%M:%S')} ET")
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
            self.logger.info(f"Market opens at: {open_time.strftime('%H:%M:%S')} ET")
            return open_time
            
        except Exception as e:
            self.logger.error(f"Error getting market open time: {e}")
            # Default to 9:30 AM ET using appropriate time source
            if self.use_mock_data and hasattr(self, 'streamer'):
                now = self.streamer.get_current_time()
            else:
                now = datetime.now(self.et_timezone)
            default_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            self.logger.warning(f"Using default open time: {default_open.strftime('%H:%M:%S')} ET")
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
            self.logger.info("\nShutdown signal received. Cleaning up...")
            self.is_running = False
            self.streamer.stop()
            self.logger.info("Stream stopped. Exiting...")

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
                        
                        # Print positions once every 10 minutes
                        if (current_time - self.last_position_print_time).total_seconds() >= 600:
                            self.logger.info("\n" + "="*50)
                            self.logger.info(f"Position Update - {current_time.strftime('%H:%M:%S')} ET")
                            self.logger.info(f"Active Positions: {list(self.active_short_positions.keys())}")
                            self.logger.info(f"Closed Positions: {list(self.closed_positions)}")
                            self.logger.info("="*50 + "\n")
                            self.last_position_print_time = current_time
                        
                        # Process each symbol's data
                        for content in contents:
                            if content.get('key') and content.get('1'):
                                symbol = content.get('key')
                                price = float(content.get('1'))
                                
                                # Update last known price
                                self.last_known_prices[symbol] = price
                                
                                # Check if symbol is eligible for trading
                                if (symbol in self.df['Ticker'].values and 
                                    symbol not in self.symbols_to_remove and
                                    symbol not in self.active_short_positions and
                                    symbol not in self.closed_positions):
                                    
                                    symbol_data = self.df.loc[self.df['Ticker'] == symbol].iloc[0]
                                    
                                    # Check if we're in valid trading hours and prior to buy time threshold
                                    market_hours = (
                                        self.market_open_time.time() <= current_time.time() <= self.strategy_end_time.time() and
                                        current_time.time() < BUY_TIME_THRESHOLD[0]
                                    )
                                    
                                    if market_hours:
                                        self._check_entry_conditions(symbol, price, symbol_data, current_time)
                            
        except Exception as e:
            self.logger.error(f"Error processing message: {str(e)}")
            self.logger.error(f"Message content: {message}")

    def _check_entry_conditions(self, symbol: str, price: float, symbol_data: pd.Series,
                              current_time: datetime) -> None:
        """Check if new short position should be opened"""
        try:
            if price < symbol_data['Target Entry']:
                # logger.info(f"\n{'='*50}")
                # logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                #     f"${price:.2f} | NO SIGNAL - Price did not hit target entry of ${symbol_data['Target Entry']:.2f}")
                # logger.info(f"{'='*50}\n")
                return

            if (price >= symbol_data['Target Entry'] and 
                symbol not in self.active_short_positions and 
                symbol not in self.closed_positions):
                
                # Calculate order details
                limit_price = max(symbol_data['Target Entry'], price)
                stop_price = round(symbol_data['Stop Price'], 2)
                target_price = round(symbol_data['Sell Price'], 2)
                quantity = int(symbol_data['Shares'])
                order_value = limit_price * quantity
                
                # Get available cash
                try:
                    cash_balance = get_cash_balance(self.client) - 1000 #Ensure we have at least $1000 left over
                    if order_value > cash_balance:
                        self.logger.warning(f"\n{'='*50}")
                        self.logger.warning(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                                    f"❌ Insufficient funds for order: ${order_value:.2f} > ${cash_balance:.2f}")
                        self.logger.warning(f"{'='*50}\n")
                        raise InsufficientFundsError("Insufficient funds to continue trading")
                        
                except Exception as e:
                    self.logger.error(f"Error checking cash balance: {str(e)}")
                    return
                    
                self.logger.info(f"\n{'='*50}")
                self.logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
                          f"${price:.2f} | 🔴 SHORT SIGNAL | Target: ${symbol_data['Target Entry']:.2f}")
                self.logger.info(f"Order Details: {quantity} shares @ ${limit_price:.2f} = ${order_value:.2f}")

                order_success = False
                if not self.use_mock_data:
                    try:

                        #REAL STREAM BUT FAKE ORDER 
                        # logger.info(f"✅ JUST TESTING: Order successfully placed and confirmed")
                        # self.active_short_positions[symbol] = {
                        #     'entry_price': limit_price,  # Store entry price
                        #     'trade_time': current_time.strftime('%I:%M%p ET')

                        #PLACE ORDER
                        order_result = place_bracket_order(self.client, symbol, quantity, instruction='SELL_SHORT' , order_type='LIMIT', price=limit_price, stop_price=stop_price, target_price=target_price)                       
                        if order_result != 'REJECTED':
                            self.logger.info(f"✅ Order successfully placed w status: {order_result}")
                            self.active_short_positions[symbol] = {
                                'entry_price': limit_price,  # Store entry price
                                'trade_time': current_time.strftime('%I:%M%p ET')  # Store trade time in desired format
                            }
                            order_success = True
                        else:
                            self.logger.error(f"❌ Order was rejected. Removing symbol from watchlist: {symbol}")
                            self.closed_positions.add(symbol)  
                            #Event Tracking if order is rejected     
                            self.add_trading_event(
                                timestamp=current_time,
                                symbol=symbol,
                                price=limit_price,
                                quantity=quantity,
                                order_value=order_value,
                                event_type='SHORT_REJECTED - REMOVE FROM WATCHLIST',
                                details=f"Order rejected: {order_result}"
                            )
                        # END OF PLACE ORDER

                    except Exception as e:
                        self.logger.error(f"❌ Error during order placement: {str(e)}")
                else:
                    self.logger.info(f"✅ Mock data mode: Order would have been placed")
                    self.active_short_positions[symbol] = {
                        'entry_price': limit_price,  # Store entry price
                        'trade_time': current_time.strftime('%I:%M%p ET')  # Store trade time in desired format
                    }
                    order_success = True

                # Event Tracking if order was successful or using mock data
                if order_success:
                    self.add_trading_event(
                        timestamp=current_time,
                        symbol=symbol,
                        price=limit_price,
                        quantity=quantity,
                        order_value=order_value,
                        event_type='SHORT_SIGNAL',
                        details=f"Price ${limit_price:.2f} crossed above Target Entry ${symbol_data['Target Entry']:.2f} | " +
                                f"Order: {quantity} shares @ ${limit_price:.2f} = ${order_value:.2f}"
                    )
                    
                    self.logger.info(f"{'='*50}\n")                    
                    sleep(0.01)  # Small delay to prevent overwhelming the system
                    
        except Exception as e:
            self.logger.error(f"Error in entry conditions for {symbol}: {e}")
            self.logger.error(f"Full traceback: {traceback.format_exc()}")

    def print_status_update(self) -> None:
        """Print periodic performance statistics"""
        if not self.stream_start_time:
            return
            
        elapsed_time = (datetime.now() - self.stream_start_time).seconds
        if elapsed_time > 0 and elapsed_time % ExecuteStrategyConfig.HEARTBEAT_INTERVAL == 0:
            self.logger.info("\nStatus Update:")
            self.logger.info(f"Running time: {elapsed_time} seconds")
            self.logger.info(f"Messages received: {self.message_count}")
            self.logger.info(f"Messages per second: {self.message_count/elapsed_time:.2f}")

    def execute_vwap_spike_strategy(self, df: pd.DataFrame) -> None:
        """Execute the VWAP spike strategy"""
        try:
            self.logger.info("Starting VWAP spike strategy execution...")
            self.logger.info(f"Strategy will check for entries until: {BUY_TIME_THRESHOLD[0]} ET")
            self.df = df
            
            # Print initial stock list in a clean format
            self.logger.info("\n" + "="*50)
            self.logger.info("Starting Strategy with Stocks:")
            for _, row in df.iterrows():
                self.logger.info(f"{row['Ticker']:<6} | Target Entry: ${row['Target Entry']:.2f}")
            self.logger.info("="*50 + "\n")

            symbols = df['Ticker'].unique().tolist()

            if self.use_mock_data:
                # Generate base prices for mock data
                base_prices = {}
                for symbol in symbols:
                    target_entry = df.loc[df['Ticker'] == symbol, 'Target Entry'].iloc[0]
                    discount = random.uniform(0.001, 0.02)  # 0.1% to 2% discount
                    base_prices[symbol] = target_entry * (1 - discount)
                # Update mock streamer configuration
                self.streamer.symbols = symbols
                self.streamer.base_prices = base_prices
            
            ####################### First track pre-market highs and filter stocks #######################
            # logger.info("Starting pre-market tracking phase...")
            # filtered_df = self.track_premarket_highs(df)
            
            # # Update streamer with filtered symbols
            # symbols = filtered_df['Ticker'].unique().tolist()
            
            ####################### Start the main trading stream #######################
            # Start the main trading stream
            self.logger.info("\n" + "="*50)
            self.logger.info("Starting main trading stream...")
            self.logger.info(f"Tracking {len(symbols)} symbols")
            self.logger.info(f"Market open: {self.market_open_time.strftime('%H:%M:%S')} ET")
            self.logger.info(f"Strategy end: {self.strategy_end_time.strftime('%H:%M:%S')} ET")
            self.logger.info("="*50 + "\n")
        
            # Initialize new stream
            if not self.use_mock_data:
                self.streamer = self.client.stream
            
            # Add retry logic for stream connection
            max_retries = 3
            retry_delay = 2
            
            for attempt in range(max_retries):
                try:
                    self.streamer.start(self.handle_stream_message)
                    self.streamer.send(self.streamer.level_one_equities(
                        ",".join(symbols), 
                        ExecuteStrategyConfig.L1_FIELDS
                    ))
                    self.is_running = True
                    self.logger.info("Stream connection established successfully")
                    break
                except Exception as e:
                    self.logger.error(f"Stream connection attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        self.logger.info(f"Retrying in {retry_delay} seconds...")
                        sleep(retry_delay)
                        # Re-authenticate before retry
                        self.client = get_authenticated_client()
                        self.streamer = self.client.stream
                    else:
                        raise Exception("Failed to establish stream connection after all retries")

            # Ensure all datetime objects are timezone-aware
            last_status_time = datetime.now(self.et_timezone)
            
            # Main trading loop - runs until buy time threshold
            while self.is_running and self.get_current_time().time() < BUY_TIME_THRESHOLD[0]:
                try:
                    if self.use_mock_data:
                        mock_message = self.streamer.generate_mock_message()
                        self.handle_stream_message(mock_message)
                    
                    while self.message_buffer:
                        message = json.loads(self.message_buffer.pop(0))
                        self.process_message(message)
                    
                    # Status update every 10 minutes
                    current_time = datetime.now(self.et_timezone)

                    # Check if it's time for a status update
                    if (current_time - last_status_time).total_seconds() >= 600:
                        self.logger.info("\n" + "="*50)
                        self.logger.info(f"Status Update - {current_time.strftime('%H:%M:%S')} ET")
                        self.logger.info(f"Active Positions: {list(self.active_short_positions.keys())}")
                        self.logger.info(f"Closed Positions: {list(self.closed_positions)}")
                        self.logger.info("="*50 + "\n")
                        last_status_time = current_time
                    
                    sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)
                    
                except InsufficientFundsError as e:
                    self.logger.warning("Stopping trading due to insufficient funds")
                    self.is_running = False
                    break
                except Exception as e:
                    self.logger.error(f"Error in trading loop: {e}")
                    # Reconnection logic
                    if not self.use_mock_data:
                        try:
                            self.logger.info("Attempting to reconnect stream...")
                            self.streamer.stop()
                            sleep(1)
                            self.streamer = self.client.stream
                            self.streamer.start(self.handle_stream_message)
                            self.streamer.send(self.streamer.level_one_equities(
                                ",".join(symbols), 
                                ExecuteStrategyConfig.L1_FIELDS
                            ))
                            self.logger.info("Stream reconnected successfully")
                        except Exception as reconnect_error:
                            self.logger.error(f"Failed to reconnect stream: {reconnect_error}")
                            self.is_running = False
                            break

            self.logger.info("Trading strategy execution completed.")
            
        except Exception as e:
            self.logger.error(f"Strategy execution failed: {e}", exc_info=True)
            raise
        finally:
            self.cleanup()

    def cleanup(self) -> None:
        """Cleanup resources after strategy execution"""
        # Export trading events and cleanup
        if hasattr(self, 'trading_events') and not self.trading_events.empty:
            # Export trading events
            if not os.path.exists('mock_stream'):
                os.makedirs('mock_stream')
                
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # Save main events to CSV
            events_filename = f'logs/trades/trading_events_{timestamp}.csv'
            self.trading_events.to_csv(events_filename, index=False)
            self.logger.info(f"Trading events saved to {events_filename}")
        
        # Cleanup stream
        self.logger.info("Cleaning up strategy execution...")
        self.is_running = False
        if hasattr(self, 'streamer') and self.streamer is not None:
            try:
                self.streamer.stop()
                self.logger.info("Strategy streamer stopped successfully")
                sleep(1)  # Give time for cleanup
            except Exception as e:
                self.logger.error(f"Error stopping strategy streamer: {e}")

######################### PRE-MARKET TRACKING FUNCTIONS ######################### 

    def track_premarket_highs(self, df: pd.DataFrame) -> pd.DataFrame:
        """Track pre-market highs and filter stocks before market open"""
        self.df = df.copy()
        self.message_buffer = []
        self.symbols_to_remove = set()
        
        self.logger.info("\n" + "="*50)
        self.logger.info("Starting pre-market tracking...")
        self.logger.info(f"Initial symbols ({len(self.df)}):")
        for symbol in self.df['Ticker'].unique():
            self.logger.info(f"- {symbol}: Yesterday High ${self.df.loc[self.df['Ticker'] == symbol, 'Yesterday High'].iloc[0]:.2f}")
        self.logger.info(f"Current time: {self.get_current_time().strftime('%H:%M:%S')} ET")
        self.logger.info(f"Market opens at: {self.market_open_time.strftime('%H:%M:%S')} ET")
        self.logger.info("="*50 + "\n")
        
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
                        self.logger.error(f"Error processing pre-market message: {e}")
                
                current_time = self.get_current_time()
                
                # Print status update every hour
                if (current_time - last_status_time.replace(tzinfo=self.et_timezone)).total_seconds() >= 3600:
                    self.print_premarket_status(current_time)
                    last_status_time = current_time
                
                # Check if we've reached market open time and break if we have
                if self.get_current_time() >= self.market_open_time:
                    self.logger.info("Market open time reached. Stopping pre-market tracking...")
                    self.is_running = False
                    break
                    
                sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)
            
            # Final summary before market open
            self.print_premarket_summary()
            
            # Remove filtered symbols and return updated DataFrame
            if self.symbols_to_remove:
                self.df = self.df[~self.df['Ticker'].isin(self.symbols_to_remove)]
            
            return self.df
            
        except Exception as e:
            self.logger.error(f"Error during pre-market tracking: {e}")
            raise
        finally:
            self.is_running = False  # Ensure is_running is set to False
            if hasattr(self, 'streamer') and self.streamer is not None:
                try:
                    self.streamer.stop()
                    self.logger.info("Pre-market streamer stopped successfully")
                except Exception as e:
                    self.logger.error(f"Error stopping pre-market streamer: {e}")

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
                                    
                                    # Check if premarket high breaches yesterday's high
                                    if self.premarket_highs[symbol] > yesterday_high:
                                        details = f"Pre-market high ${self.premarket_highs[symbol]:.2f} breached yesterday's high ${yesterday_high:.2f}"
                                        
                                        # Use the new method instead of concat
                                        self.add_trading_event(
                                            timestamp=simulated_time,
                                            symbol=symbol,
                                            price=current_price,
                                            quantity=0,
                                            order_value=0,
                                            event_type='REMOVED_PREMARKET',
                                            details=details
                                        )
                                        
                                        # Log the removal
                                        self.logger.info("\n" + "-"*70)
                                        self.logger.info(f"\n🚫 REMOVING {symbol}\nCurrent Price: ${current_price:.2f}\nPremarket High: ${self.premarket_highs[symbol]:.2f}\nYesterday High: ${yesterday_high:.2f}\nRemaining Symbols: {len(self.df['Ticker'].unique()) - len(self.symbols_to_remove) - 1}")
                                        self.logger.info("-"*70 + "\n")
                                        
                                        self.symbols_to_remove.add(symbol)

        except Exception as e:
            self.logger.error(f"Error processing pre-market message: {str(e)}")
            self.logger.error(f"Message content: {message}")

    def print_premarket_status(self, simulated_time: datetime) -> None:
        """Print periodic pre-market status update using simulated time"""
        # Calculate hours until market open using simulated time
        hours_to_open = (self.market_open_time - simulated_time).total_seconds() / 3600
        
        self.logger.info("\n" + "="*50)
        self.logger.info(f"Pre-market status - {simulated_time.strftime('%H:%M:%S')} ET")
        self.logger.info(f"Hours until market open: {hours_to_open:.1f}")
        self.logger.info(f"Symbols being tracked: {len(self.df) - len(self.symbols_to_remove)}")
        self.logger.info(f"Symbols removed: {len(self.symbols_to_remove)}")
        self.logger.info("="*50 + "\n")

    def print_premarket_summary(self) -> None:
        """Print final pre-market summary with detailed information"""
        self.logger.info("\n" + "="*70)
        self.logger.info("PREMARKET TRACKING COMPLETED")
        self.logger.info("="*70)
        
        if self.symbols_to_remove:
            self.logger.info("\n🚫 REMOVED SYMBOLS:")
            for symbol in sorted(self.symbols_to_remove):
                yesterday_high = self.df.loc[self.df['Ticker'] == symbol, 'Yesterday High'].iloc[0]
                self.logger.info(f"- {symbol:<6} | Premarket High: ${self.premarket_highs[symbol]:.2f} | Yesterday High: ${yesterday_high:.2f}")
        
        remaining_symbols = set(self.df['Ticker']) - self.symbols_to_remove
        if remaining_symbols:
            self.logger.info("\n✅ REMAINING SYMBOLS:")
            for symbol in sorted(remaining_symbols):
                yesterday_high = self.df.loc[self.df['Ticker'] == symbol, 'Yesterday High'].iloc[0]
                current_high = self.premarket_highs.get(symbol, 0)
                self.logger.info(f"- {symbol:<6} | Current High: ${current_high:.2f} | Yesterday High: ${yesterday_high:.2f}")
        
        self.logger.info("\n" + "="*70)
        self.logger.info(f"Final Count - Removed: {len(self.symbols_to_remove)} | Remaining: {len(remaining_symbols)}")
        self.logger.info("="*70 + "\n")

    def add_trading_event(self, timestamp, symbol, price, quantity, order_value, event_type, details):
        """Helper method to add events to trading_events DataFrame"""
        next_idx = len(self.trading_events)
        self.trading_events.loc[next_idx] = {
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S') if isinstance(timestamp, datetime) else timestamp,
            'symbol': str(symbol),
            'price': float(price),
            'quantity': float(quantity),
            'order_value': float(order_value),
            'event_type': str(event_type),
            'details': str(details)
        }

    # def add_price_history(self, timestamp, symbol, price, simulated_time):
    #     """Helper method to add price updates to price_history DataFrame"""
    #     next_idx = len(self.price_history)
    #     self.price_history.loc[next_idx] = {
    #         'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S') if isinstance(timestamp, datetime) else timestamp,
    #         'symbol': str(symbol),
    #         'price': float(price),
    #         'simulated_time': simulated_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(simulated_time, datetime) else simulated_time
    #     }

        # def _check_exit_conditions(self, symbol: str, price: float, symbol_data: pd.Series, 
    #                          current_time: datetime) -> None:
    #     """Check if position should be closed based on price targets"""
    #     if symbol in self.active_short_positions and symbol not in self.closed_positions:
    #         # First verify the position actually exists
    #         quantity = int(symbol_data['Shares'])
    #         entry_price = self.active_short_positions[symbol]['entry_price'] #REPLACE WITH TRUE TRADE PRICE - If we can get order id, we can grab this at run time
            
    #         # Calculate stop and target prices based on entry price
    #         stop_price = entry_price * (1 + STOP[0])  # Add percentage for stop loss (going up)
    #         target_price = entry_price * (1 - TARGET[0])  # Subtract percentage for profit target (going down)

    #         if price >= stop_price or price <= target_price:
            
    #             logger.info(f"\n{'='*50}")
    #             order_success = False
                
    #             if price >= stop_price: #Stop Loss Hit
    #                 limit_price = max(stop_price, price)
    #                 order_value = limit_price * quantity
                    
    #                 if not self.use_mock_data:
    #                     try:
    #                         logger.info(f"Attempting to cover short position for {symbol}")
    #                         if not check_position_match(self.client, symbol, quantity, short=True) and time_since_trade > 30:
    #                             logger.warning(f"\n{'='*50}")
    #                             logger.warning(f"No matching short position found for {symbol} with quantity {quantity}")
    #                             logger.warning(f"{'='*50}\n")                    
    #                             return
                            
    #                         # PLACE ORDER
    #                         order_result = place_real_order(self.client, symbol, quantity, instruction='BUY_TO_COVER', order_type='LIMIT', price=limit_price)                      
    #                         if order_result != 'REJECTED':
    #                             logger.info(f"${price:.2f} | Order Successfully Placed | 📉 Stop loss hit at ${stop_price:.2f} | Entry: ${entry_price:.2f} | Status: {order_result}")
    #                             order_success = True
    #                         else:
    #                             logger.error(f"❌ Failed to cover short position: {order_result}")
    #                             return
    #                         # END OF PLACE ORDER

    #                     except Exception as e:
    #                         logger.error(f"❌ Error covering short position: {str(e)}")
    #                         return
    #                 else:
    #                     logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
    #                               f"${price:.2f} | 📉 Stop loss hit at ${stop_price:.2f} | Entry: ${entry_price:.2f}")
    #                     order_success = True
    #             else: #Profit Target Hit
    #                 limit_price = max(target_price, price)
    #                 order_value = limit_price * quantity
    #                 logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
    #                           f"${price:.2f} | 📈 Profit target at ${target_price:.2f} | Entry: ${entry_price:.2f}")
    #                 if not self.use_mock_data:
    #                     try:
                            
    #                         logger.info(f"Attempting to cover short position for {symbol}")
    #                         if not check_position_match(self.client, symbol, quantity, short=True) and time_since_trade > 30:
    #                             logger.warning(f"\n{'='*50}")
    #                             logger.warning(f"No matching short position found for {symbol} with quantity {quantity}")
    #                             logger.warning(f"{'='*50}\n")                    
    #                             return
                            
    #                         # PLACE ORDER 
    #                         order_result = place_real_order(self.client, symbol, quantity, instruction='BUY_TO_COVER' , order_type='MARKET') 
    #                         if order_result != 'REJECTED':
    #                             logger.info(f"${price:.2f} | Order Successfully Placed | 📈 Profit target at ${target_price:.2f} | Entry: ${entry_price:.2f} | Status: {order_result}")
    #                             order_success = True
    #                         else:
    #                             logger.error(f"❌ Failed to cover short position: {order_result}")
    #                             return
    #                         # END OF PLACE ORDER

    #                     except Exception as e:
    #                         logger.error(f"❌ Error covering short position: {str(e)}")
    #                         return
    #                 else:
    #                     logger.info(f"{current_time.strftime('%H:%M:%S')} ET | {symbol}: "
    #                               f"${price:.2f} | 📈 Profit target at ${target_price:.2f} | Entry: ${entry_price:.2f}")
    #                     order_success = True
                
    #             logger.info(f"{'='*50}\n")
                
    #             # Only add to trading events if order was successful or using mock data
    #             if order_success:
    #                 self.add_trading_event(
    #                     timestamp=current_time,
    #                     symbol=symbol,
    #                     price=price,
    #                     quantity=-quantity,
    #                     order_value=-order_value,
    #                     event_type='COVER_SHORT',
    #                     details=f"{'Stop loss' if price >= stop_price else 'Profit target'} hit | " +
    #                             f"Entry: ${entry_price:.2f} | Stop: ${stop_price:.2f} | Target: ${target_price:.2f}"
    #                 )
                    
    #                 # Add to closed positions and remove from active positions
    #                 self.closed_positions.add(symbol)
    #                 del self.active_short_positions[symbol]

    # def check_end_of_day_positions(self) -> None:
    #     """Close any remaining positions at strategy end time"""
    #     # Get current time based on mode
    #     if self.use_mock_data and hasattr(self, 'streamer'):
    #         current_time = self.streamer.get_current_time()
    #     else:
    #         current_time = datetime.now(self.et_timezone)
        
    #     seconds_to_close = (self.strategy_end_time - current_time).total_seconds()
    #     # print(f"Seconds to close: {seconds_to_close}")
    #     if seconds_to_close <= 30:
    #         remaining_positions = set(self.active_short_positions.keys()) - self.closed_positions
    #         if remaining_positions:
    #             logger.info(f"\n{'='*50}")
    #             logger.info(f"{current_time.strftime('%H:%M:%S')} ET | END OF DAY CLOSING")
    #             logger.info(f"Closing {len(remaining_positions)} positions")
                
    #             for symbol in remaining_positions:
    #                 current_price = float(self.last_known_prices.get(symbol, 0))
    #                 entry_price = self.active_short_positions[symbol]['entry_price']
    #                 quantity = int(self.df.loc[self.df['Ticker'] == symbol, 'Shares'].iloc[0])
    #                 order_value = current_price * quantity
    #                 order_success = False
    #                 if not self.use_mock_data:
    #                     # Verify position exists before attempting to cover
    #                     if check_position_match(self.client, symbol, quantity, short=True):
    #                         logger.info(f"{symbol}: ${current_price:.2f} | Entry: ${entry_price:.2f} | ⏰ END OF DAY CLOSE")
                            
    #                         # PLACE ORDER
    #                         order_result = place_real_order(self.client, symbol, quantity, instruction='BUY_TO_COVER' , order_type='MARKET')
    #                         if order_result !=  'REJECTED':
    #                             logger.info(f"${symbol} | Order Successfully Placed | ⏰ END OF DAY CLOSE - sold at ${current_price:.2f} | Entry: ${entry_price:.2f} | Status: {order_result}")
    #                             order_success = True
    #                         else:
    #                             logger.error(f"❌ Failed to cover short position: {order_result}")
    #                         # END OF PLACE ORDER
    #                     else:
    #                         logger.warning(f"EOD - No matching short position found for {symbol} with quantity {quantity}")
    #                 else:
    #                     logger.info(f"Order successfully placed for {symbol}: ${current_price:.2f} | Entry: ${entry_price:.2f} | ⏰ END OF DAY CLOSE")
    #                     order_success = True
    #                 # Add to trading events if order was successful or using mock data
    #                 if order_success:
    #                     self.add_trading_event(
    #                         timestamp=current_time,
    #                         symbol=symbol,
    #                         price=current_price,
    #                         quantity=-quantity,
    #                         order_value=-order_value,
    #                         event_type='EOD_CLOSE',
    #                         details=f'End of day position close at ${current_price:.2f}'
    #                     )
                    
    #                     # Add to closed positions
    #                     self.closed_positions.add(symbol)
    #                     del self.active_short_positions[symbol] 
    #             logger.info(f"{'='*50}\n")

