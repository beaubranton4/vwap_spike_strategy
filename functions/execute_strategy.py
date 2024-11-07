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
    def __init__(self):
        """Initialize the market data streamer"""
        dotenv.load_dotenv()
        self.client = schwabdev.Client(
            os.getenv('appKey'),
            os.getenv('appSecret'),
            os.getenv('callback_url'),
            tokens_file="auth/tokens.json", 
            timeout=10, 
            update_tokens_auto=True
        )
        self.streamer = self.client.stream
        self.shared_list: List[str] = []
        self.running = False
        self.message_count = 0
        self.start_time: Optional[datetime] = None
        self.shorted_symbols = set()
        self.closed_positions = set()
        self.et_timezone = pytz.timezone('US/Eastern')
        
        # Get market hours
        self.market_open_time = self.get_market_open_time()
        self.strategy_end_time = self.get_strategy_end_time()
    
    def get_strategy_end_time(self) -> datetime:
        """Get today's strategy end time (earlier of market close or SELL_TIME_THRESHOLD)"""
        try:
            # Get NYSE calendar
            nyse = mcal.get_calendar('NYSE')
            today = datetime.now().date()
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
                
            # Get market close time and convert to ET
            market_close = schedule.iloc[0]['market_close'].tz_convert('US/Eastern')
            
            # Get configured sell time threshold
            now = datetime.now(self.et_timezone)
            strategy_cutoff = now.replace(
                hour=SELL_TIME_THRESHOLD.hour,
                minute=SELL_TIME_THRESHOLD.minute,
                second=0,
                microsecond=0
            )
            
            # Use the earlier of market close or sell time threshold
            strategy_end = min(market_close, strategy_cutoff)
            
            logger.info(f"Market closes at: {market_close.strftime('%H:%M:%S')} ET")
            logger.info(f"Strategy ends at: {strategy_end.strftime('%H:%M:%S')} ET")
            return strategy_end
            
        except Exception as e:
            logger.error(f"Error getting strategy end time: {e}")
            # Default to market close
            now = datetime.now(self.et_timezone)
            default_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            logger.warning(f"Using default strategy end time: {default_close.strftime('%H:%M:%S')} ET")
            return default_close

    def get_market_open_time(self) -> datetime:
        """Get today's market open time"""
        try:
            # Get NYSE calendar
            nyse = mcal.get_calendar('NYSE')
            today = datetime.now().date()
            schedule = pd.DataFrame(nyse.schedule(start_date=today, end_date=today))
            
            if len(schedule) == 0:
                raise ValueError("No market schedule found for today")
                
            # Get open time and convert to ET
            open_time = schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
            
            logger.info(f"Market opens at: {open_time.strftime('%H:%M:%S')} ET")
            return open_time
            
        except Exception as e:
            logger.error(f"Error getting market hours: {e}")
            # Default to 9:30 AM ET if we can't get market hours
            now = datetime.now(self.et_timezone)
            default_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            logger.warning(f"Using default market open time: {default_open.strftime('%H:%M:%S')} ET")
            return default_open

    def is_strategy_active(self) -> bool:
        """Check if the strategy should continue running"""
        current_time = datetime.now(self.et_timezone)
        return (current_time > self.market_open_time) and (current_time < self.strategy_end_time)

    def response_handler(self, message: str) -> None:
        """Handle incoming stream messages"""
        self.shared_list.append(message)

    def setup_signal_handlers(self) -> None:
        """Set up handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info("\nShutdown signal received. Cleaning up...")
            self.running = False
            self.streamer.stop()
            logger.info("Stream stopped. Exiting...")

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def process_message(self, message: Dict[str, Any]) -> None:
        """Process individual messages from the stream"""
        for rtype, services in message.items():
            if rtype == "data":
                self._handle_data_message(services)
            elif rtype == "response":
                logger.info(f"Response received: {services}")
            elif rtype == "notify":
                logger.debug(f"Heartbeat received: {services}")
            else:
                logger.warning(f"Unknown message type: {message}")

    def _handle_data_message(self, services: List[Dict[str, Any]]) -> None:
        """Handle data-type messages"""
        for service in services:
            contents = service.get("content", [])
            
            for content in contents:
                if content.get('key') and content.get('1'):
                    symbol = content.get('key')
                    price = content.get('1')
                    
                    eastern_time = datetime.now(pytz.timezone('US/Eastern'))
                    
                    try:
                        if symbol in self.df['Ticker'].values:
                            current_price = float(price)
                            # Store last known price
                            self.last_prices[symbol] = current_price
                            
                            target_entry = self.df.loc[self.df['Ticker'] == symbol, 'Target Entry'].iloc[0]
                            stop_price = self.df.loc[self.df['Ticker'] == symbol, 'Stop Price'].iloc[0]
                            profit_target = self.df.loc[self.df['Ticker'] == symbol, 'Sell Price'].iloc[0]
                            buy_time_threshold = self.df.loc[self.df['Ticker'] == symbol, 'Buy Time Threshold'].iloc[0]
                            
                            # Convert market open and close times to time objects
                            market_open_time = self.market_open_time.time()
                            market_close_time = self.strategy_end_time.time()
                            
                            # Check if symbol has already been shorted but not closed
                            if symbol in self.shorted_symbols and symbol not in self.closed_positions:
                                # Check stop loss or profit target
                                if current_price >= stop_price or current_price <= profit_target:
                                    print(f"\n{'='*50}")
                                    if current_price >= stop_price:
                                        print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} |  📉 Stop loss hit at ${stop_price:.4f}")
                                    else:
                                        print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} |  📈 Profit target reached at ${profit_target:.4f}")
                                    print(f"{'='*50}\n")
                                    
                                    # Add to closed positions
                                    self.closed_positions.add(symbol)
                                else:
                                    print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} | NO SIGNAL - Stock already shorted")
                                continue
                            
                            # Trading signal logic for new shorts
                            if (current_price > target_entry and 
                                symbol not in self.closed_positions and 
                                # eastern_time.time() <= buy_time_threshold and (TURN THIS BACK ON!!!)
                                market_open_time <= eastern_time.time() <= market_close_time):
                                print(f"\n{'='*50}")
                                print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} | 🔴 TRADING SIGNAL - SHORT STOCK | Target Entry: ${target_entry:.4f}")
                                print(f"{'='*50}\n")
                                
                                self.shorted_symbols.add(symbol)
                            else:
                                print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} | NO SIGNAL - Below Target Price of ${target_entry:.4f}")
                            
                    except Exception as e:
                        logger.error(f"Error processing message for {symbol}: {e}")

    def print_status_update(self) -> None:
        """Print periodic status updates"""
        if not self.start_time:
            return
            
        elapsed_time = (datetime.now() - self.start_time).seconds
        if elapsed_time > 0 and elapsed_time % ExecuteStrategyConfig.HEARTBEAT_INTERVAL == 0:
            logger.info("\nStatus Update:")
            logger.info(f"Running for: {elapsed_time} seconds")
            logger.info(f"Messages received: {self.message_count}")
            logger.info(f"Average messages per second: {self.message_count/elapsed_time:.2f}")

    def check_strategy_end_positions(self) -> None:
        """Check if we need to close positions due to strategy end time"""
        eastern_time = datetime.now(self.et_timezone)
        time_to_close = (self.strategy_end_time - eastern_time).total_seconds()
        
        # If we're within 30 seconds of strategy end, cover at market price
        if time_to_close <= 30:
            # Check all shorted positions that haven't been closed
            for symbol in self.shorted_symbols - self.closed_positions:
                current_price = float(self.last_prices.get(symbol, 0))
                
                print(f"\n{'='*50}")
                print(f"{eastern_time.strftime('%H:%M:%S.%f')[:-3]} ET | {symbol}: ${current_price:.4f} | ❓ TRADING SIGNAL - COVERED SHORT (Sell Time Threshold Reached)")
                print(f"{'='*50}\n")
                
                self.closed_positions.add(symbol)

    def execute_vwap_spike_strategy(self, df) -> None:
        """Main method to stream real-time market data"""
        try:
            self.df = df
            self.setup_signal_handlers()
            self.streamer.start(self.response_handler)
            
            symbols = df['Ticker'].unique().tolist()
            start_time = datetime.now(self.et_timezone)
            logger.info(f"Starting strategy at {start_time.strftime('%H:%M:%S')} ET")
            logger.info(f"Will run until {self.strategy_end_time.strftime('%H:%M:%S')} ET")
            
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.L1_FIELDS
            ))

            self.running = True
            self.start_time = datetime.now()
            self.last_prices = {}  # Track last known prices

            # Main processing loop - run until strategy end time
            while self.running and self.is_strategy_active():
                # Check for strategy end positions first
                self.check_strategy_end_positions()
                
                while self.shared_list:
                    try:
                        oldest_response = json.loads(self.shared_list.pop(0))
                        self.message_count += 1
                        self.process_message(oldest_response)
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                
                sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)

        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            # One final check for any remaining positions
            self.check_strategy_end_positions()
            end_time = datetime.now(self.et_timezone)
            logger.info(f"\nScript completed at {end_time.strftime('%H:%M:%S')} ET")
            self.streamer.stop()
