import schedule as scheduler
import time as time_lib
from datetime import datetime, timedelta
import pytz
import logging
from pathlib import Path
import pandas as pd
import pandas_market_calendars as mcal
from functions import *
from config import *
import threading
import os
import subprocess
import psutil
import sys

def main():
    client = get_authenticated_client()
    
    # Get today's date and market open time in Eastern Time
    eastern_tz = pytz.timezone('US/Eastern')
    today = datetime.now(eastern_tz).date()
    start_date = datetime.combine(today, datetime.min.time())  # Start of today
    end_date = datetime.combine(today, datetime.max.time())    # End of today
    
    try:
        response = client.price_history(
            symbol='AAPL',
            periodType='day',
            period=1,
            frequencyType='minute',
            frequency=10,
            startDate=start_date,
            endDate=end_date,
            needExtendedHoursData=True,
            needPreviousClose=True
        )
        
        # Check if request was successful
        response.raise_for_status()
        
        # Parse the JSON response
        data = response.json()
        
        print(f"\nPrice history for AAPL:")
        print("=" * 50)
        
        for candle in data.get('candles', []):
            candle_time = pd.to_datetime(candle['datetime'], unit='ms').tz_localize('UTC').tz_convert('US/Eastern')
            high_price = candle['high']
            print(f"Time: {candle_time.strftime('%Y-%m-%d %H:%M:%S')} ET, High: ${high_price:.2f}")
            
    except Exception as e:
        print(f"Error getting price history: {str(e)}")
        if hasattr(response, 'text'):
            print(f"Response text: {response.text}")

if __name__ == "__main__":
    main()