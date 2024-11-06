from datetime import datetime
import schwabdev
import logging
import dotenv
import time
import json
import os
import signal
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from functions import *

dotenv.load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

@dataclass
class ExecuteStrategyConfig:
    """Configuration settings for the market data stream"""
    MAX_RUNTIME: int = 120  # seconds
    HEARTBEAT_INTERVAL: int = 10  # seconds
    SLEEP_INTERVAL: float = 0.5  # seconds
    FIELDS: str = "0,1,2,3,4,5,6,7,8"

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
            service_type = service.get("service")
            timestamp = service.get("timestamp", 0)
            contents = service.get("content", [])
            
            for content in contents:
                symbol = content.pop("key", "NO KEY")
                fields = content
                message_time = datetime.fromtimestamp(timestamp//1000)
                logger.info(f"[{service_type} - {symbol}]({message_time}): {fields}")

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

    def execute_vwap_spike_strategy(self, df) -> None:
        """
        Main method to stream real-time market data
        
        Args:
            df: DataFrame containing symbols to stream data for
        """
        try:
            # Setup and initialization
            self.setup_signal_handlers()
            self.streamer.start(self.response_handler)
            print(df.head())
            symbols = df['Ticker'].unique().tolist()
            self.streamer.send(self.streamer.level_one_equities(
                ",".join(symbols), 
                ExecuteStrategyConfig.FIELDS
            ))

            # Start streaming
            self.running = True
            self.start_time = datetime.now()

            # Main processing loop
            while self.running and (datetime.now() - self.start_time).seconds < ExecuteStrategyConfig.MAX_RUNTIME:
                while self.shared_list:
                    try:
                        oldest_response = json.loads(self.shared_list.pop(0))
                        self.message_count += 1
                        self.print_status_update()
                        self.process_message(oldest_response)
                    except json.JSONDecodeError as e:
                        logger.error(f"Error decoding message: {e}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                
                time.sleep(ExecuteStrategyConfig.SLEEP_INTERVAL)

        except Exception as e:
            logger.error(f"Stream error: {e}")
        finally:
            logger.info(f"\nScript completed after {ExecuteStrategyConfig.MAX_RUNTIME} seconds")
            self.streamer.stop()
