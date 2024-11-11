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
        self.time_increment = timedelta(minutes=30)  # 30-minute increments
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
        
        # Increased volatility for more dramatic price movements
        volatility_multiplier = {
            'pre_market': 0.015,    # 1.5% max movement
            'market': 0.025,        # 2.5% max movement
            'after_market': 0.01    # 1.0% max movement
        }[session]
        
        # Add directional bias for more trending movements
        trend_bias = random.choice([-1, 1])  # Randomly choose upward or downward trend
        base_movement = random.uniform(0.005, volatility_multiplier)  # Minimum 0.5% movement
        price_change = self.base_prices[symbol] * (base_movement * trend_bias)
        
        # Occasionally generate larger moves (20% chance)
        if random.random() < 0.2:
            price_change *= random.uniform(2, 3)  # 2-3x larger movement
        
        new_price = self.base_prices[symbol] + price_change
        self.base_prices[symbol] = new_price
        return round(new_price, 2)
        
    def update_simulated_time(self):
        """Update the simulated time based on fixed 30-minute increments"""
        self.current_time += self.time_increment
        return self.current_time
        
    def generate_mock_message(self) -> str:
        """Generate a mock market data message with simulated time"""
        # Update simulated time
        current_time = self.update_simulated_time()
        session = self.get_session_type(current_time)
        
        # Create content list for all symbols
        contents = []
        for symbol in self.symbols:
            price = self.generate_mock_price(symbol)
            contents.append({
                "key": symbol,
                "1": str(price),  # Last price
            })
        
        message = {
            "data": [{
                "service": "LEVELONE_EQUITY",
                "timestamp": current_time.timestamp(),
                "simulated_time": current_time.strftime('%Y-%m-%d %H:%M:%S'),
                "session": session,
                "content": contents  # Now includes all symbols
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

    def start(self, callback: Callable):
        """Start the mock streamer"""
        self.callback = callback
        self.is_running = True
        logger.info("Mock streamer started")

    def stop(self):
        """Stop the mock streamer"""
        self.is_running = False
        self.callback = None
        logger.info("Mock streamer stopped")
