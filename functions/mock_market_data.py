import json
import random
from datetime import datetime, timedelta
import pytz
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)

class MockMarketDataStreamer:
    """Simulates market data streaming for testing with time simulation"""
    
    def __init__(self, symbols: list, base_prices: Dict[str, float], 
                 start_time: datetime = None, time_multiplier: int = 60):
        """
        Initialize mock streamer
        :param symbols: List of stock symbols
        :param base_prices: Initial prices for symbols
        :param start_time: Starting time for simulation (defaults to 12:00 AM ET today)
        :param time_multiplier: How much faster than real-time to run (default 60x)
        """
        self.symbols = symbols
        self.callback = None
        self.is_running = False
        self.base_prices = base_prices or {}
        self.et_timezone = pytz.timezone('US/Eastern')
        
        # Set up simulated time starting at midnight
        if start_time is None:
            today = datetime.now(self.et_timezone).date()
            self.current_time = datetime.combine(today, datetime.strptime("00:00", "%H:%M").time())
            self.current_time = self.et_timezone.localize(self.current_time)
        else:
            self.current_time = start_time
            
        self.time_multiplier = time_multiplier
        self.time_increment = timedelta(minutes=15)  # 15-minute increments
        self.last_update = datetime.now()
        
        # Track session type for price volatility adjustment
        self.session_types = {
            'pre_market': (datetime.strptime("00:00", "%H:%M").time(), 
                         datetime.strptime("09:30", "%H:%M").time()),
            'market': (datetime.strptime("09:30", "%H:%M").time(), 
                      datetime.strptime("16:00", "%H:%M").time()),
            'after_market': (datetime.strptime("16:00", "%H:%M").time(), 
                           datetime.strptime("23:59", "%H:%M").time())
        }
        
        logger.info(f"Initialized mock streamer with {len(symbols)} symbols")
        logger.info(f"Starting time: {self.current_time.strftime('%Y-%m-%d %H:%M:%S')} ET")
        logger.info(f"Time multiplier: {time_multiplier}x")
        
    def get_session_type(self, time: datetime) -> str:
        """Determine the trading session based on time"""
        current_time = time.time()
        
        if self.session_types['pre_market'][0] <= current_time < self.session_types['pre_market'][1]:
            return 'pre_market'
        elif self.session_types['market'][0] <= current_time < self.session_types['market'][1]:
            return 'market'
        else:
            return 'after_market'
        
    def generate_mock_price(self, symbol: str) -> float:
        """Generate a realistic mock price movement based on session"""
        if symbol not in self.base_prices:
            self.base_prices[symbol] = random.uniform(10, 100)
            
        session = self.get_session_type(self.current_time)
        
        # Adjust volatility based on session
        volatility_multiplier = {
            'pre_market': 0.003,    # 0.3% max movement
            'market': 0.005,        # 0.5% max movement
            'after_market': 0.002   # 0.2% max movement
        }[session]
        
        price_change = self.base_prices[symbol] * random.uniform(
            -volatility_multiplier, 
            volatility_multiplier
        )
        new_price = self.base_prices[symbol] + price_change
        self.base_prices[symbol] = new_price
        return round(new_price, 2)
        
    def update_simulated_time(self):
        """Update the simulated time based on elapsed real time and multiplier"""
        now = datetime.now()
        elapsed_seconds = (now - self.last_update).total_seconds()
        simulated_seconds = elapsed_seconds * self.time_multiplier
        self.current_time += timedelta(seconds=simulated_seconds)
        self.last_update = now
        return self.current_time
        
    def generate_mock_message(self) -> str:
        """Generate a mock market data message with simulated time"""
        # Update simulated time
        current_time = self.update_simulated_time()
        session = self.get_session_type(current_time)
        
        symbol = random.choice(self.symbols)
        price = self.generate_mock_price(symbol)
        
        # Adjust bid/ask spread based on session
        spread_multiplier = {
            'pre_market': 0.04,    # Wider spread
            'market': 0.02,        # Normal spread
            'after_market': 0.03   # Moderate spread
        }[session]
        
        message = {
            "data": [{
                "service": "LEVELONE_EQUITY",
                "timestamp": current_time.timestamp(),
                "simulated_time": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                "session": session,
                "content": [{
                    "key": symbol,
                    "1": str(price),  # Last price
                    "2": str(price - random.uniform(0, spread_multiplier)),  # Bid
                    "3": str(price + random.uniform(0, spread_multiplier))   # Ask
                }]
            }]
        }
        return json.dumps(message)

    def get_current_time(self) -> datetime:
        """Get the current simulated time"""
        return self.current_time

    def level_one_equities(self, symbols: str, fields: str) -> Dict:
        """Mock method to match real streamer interface"""
        return {"service": "LEVELONE_EQUITY", "symbols": symbols, "fields": fields}
        
    def send(self, request: Dict):
        """Mock method to match real streamer interface"""
        logger.info(f"Mock subscription request: {request}")
