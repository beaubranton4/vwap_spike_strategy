#!/usr/bin/env python
# coding: utf-8

from datetime import datetime, time
from functions import *
from config import *
import logging
from functools import lru_cache
import pandas as pd
import pandas_market_calendars as mcal
import pytz

##For some reason, day of i only get data starting at 7am ET, but can receive data starting at 4am ET for previous days.
##May be due to some data delay from Schwab.

def check_premarket_highs(client, symbols_df):
    """
    Check if premarket highs exceed yesterday's high for a list of symbols.
    Returns the original DataFrame with rows removed where premarket high exceeded yesterday's high.
    """
    logger = logging.getLogger(__name__)
    
    # Create a copy of the original DataFrame to avoid modifying the input
    filtered_df = symbols_df.copy()
    
    # Get today's date and market open time in Eastern Time
    eastern_tz = pytz.timezone('US/Eastern')
    today = datetime.now(eastern_tz).date()
    
    # Convert today's date to timestamp for API
    today_start = int(pd.Timestamp(today).timestamp() * 1000)
    today_end = int((pd.Timestamp(today) + pd.Timedelta(days=1)).timestamp() * 1000)
    
    # Get market open time
    market_schedule = pd.DataFrame(mcal.get_calendar('NYSE').schedule(start_date=today, end_date=today))
    market_open = market_schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
    
    # Keep track of symbols to remove
    symbols_to_remove = []

    # Prepare symbols to check
    symbols_to_check = filtered_df[['Ticker', 'Yesterday High']].dropna().values.tolist()

    # Get price history for all symbols
    responses = {
        symbol: get_price_history_with_schwabdev(
            client=client,
            ticker=symbol,
            period_type='day',
            period=1,
            frequency_type='minute',
            frequency=5,
            need_extended_hours_data=True,
            need_previous_close=True,
            start_time=today_start,
            end_time=today_end
        ) for symbol, _ in symbols_to_check
    }

    for symbol, yesterday_high in symbols_to_check:
        try:
            response = responses[symbol]

            if response is None or not response.get('candles'):
                symbols_to_remove.append(symbol)
                continue
            
            # Filter for premarket candles only
            premarket_highs = [
                candle['high'] for candle in response['candles']
                if (pd.to_datetime(candle['datetime'], unit='ms').tz_localize('UTC').tz_convert('US/Eastern').date() == today and
                    pd.to_datetime(candle['datetime'], unit='ms').tz_localize('UTC').tz_convert('US/Eastern') < market_open)
            ]
            
            if not premarket_highs:
                symbols_to_remove.append(symbol)
                continue
                
            # Calculate premarket high
            premarket_high = max(premarket_highs)
            
            # Remove symbols where premarket high exceeds yesterday's high
            if premarket_high > yesterday_high:
                symbols_to_remove.append(symbol)
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
            symbols_to_remove.append(symbol)
            continue
    
    # Remove the identified symbols from the DataFrame
    filtered_df = filtered_df[~filtered_df['Ticker'].isin(symbols_to_remove)]
    
    # Print removed and remaining symbols
    print("Removed symbols:", symbols_to_remove)
    print("Remaining symbols:", filtered_df['Ticker'].tolist())
    
    return filtered_df

# Usage example:
if __name__ == "__main__":
    client = get_authenticated_client()
    
    selected_date = '2024-11-14'
    screener_results = pd.read_excel(f'screener/daily_screener_signals/{selected_date}.xlsx')
    print("\nStarting symbols from screener:")
    print(screener_results['Ticker'].tolist())
    
    filtered_screener_results = check_premarket_highs(client, screener_results)
    print("\nFinal screener results:")
    print(filtered_screener_results)