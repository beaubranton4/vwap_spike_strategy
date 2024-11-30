#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import numpy as np
import random
import itertools
import json
import pprint
import datetime
from datetime import date, time, timedelta, datetime
import requests
import os
import pandas_market_calendars as mcal
import base64
from datetime import datetime, timedelta, date
import traceback
import glob
import sys
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))
from functions import *
from config import *
from datetime import datetime, time
import logging
import pytz

def run_vwap_spike_screener(client, ticker_list, combinations, day_of_backtest, 
                           period_type, period, frequency_type, frequency,
                           start_time, end_time, need_extended_hours_data, 
                           need_previous_close, rolling_lookback, 
                           price_spike_thresh_index, time_sig_thresh_index, buy_time_threshold_index,
                           vol_spike_thresh_index, sell_time_threshold_index,
                           stop_index, target_index):
    """
    Run the VWAP spike strategy screener to identify trading opportunities
    
    Args:
        client (schwabdev.Client): Authenticated Schwab client
        ticker_list (pd.DataFrame): DataFrame containing ticker symbols to screen
        combinations (list): List of strategy parameter combinations to test
        day_of_backtest (datetime): Date to run backtest for
        period_type (str): Time period type for historical data
        period (int): Number of periods for historical data
        frequency_type (str): Frequency type for historical data
        frequency (int): Frequency for historical data
        start_time (str): Start time for historical data
        end_time (str): End time for historical data
        need_extended_hours_data (bool): Whether to include extended hours data
        need_previous_close (bool): Whether to include previous close data
        rolling_lookback (int): Rolling window for volume average calculation
        price_spike_thresh_index (int): Index for price spike threshold in strategy
        time_sig_thresh_index (int): Index for time signal threshold in strategy
        buy_time_threshold_index (int): Index for buy time threshold in strategy
        vol_spike_thresh_index (int): Index for volume spike threshold in strategy
        sell_time_threshold_index (int): Index for sell time threshold in strategy
        stop_index (int): Index for stop loss in strategy
        target_index (int): Index for profit target in strategy
        
    Returns:
        pd.DataFrame: DataFrame containing screener results
    """
    
    start_clock = datetime.now()  # calculate run time
    
    # Get tickers list
    if 'Ticker' not in ticker_list.columns:
        print("Column 'Ticker' not found in the DataFrame.")
        return pd.DataFrame()

    
    
    tickers_df = ticker_list[['Ticker']].dropna()
    all_tickers = tickers_df['Ticker'].unique().tolist()

    #FOR TESTING
    # all_tickers = ['PLUG']

    # Initialize results DataFrame
    stocks_to_trade = pd.DataFrame(columns=['Ticker','Target Entry','Volume Spike','Price Spike', 'Shares'
                                          'Previous Day Close','Signal Time', 'Stop Price', 'Sell Price'])
    
    # Process tickers in chunks of 100
    CHUNK_SIZE = 100
    for chunk_start in range(0, len(all_tickers), CHUNK_SIZE):
        chunk_end = min(chunk_start + CHUNK_SIZE, len(all_tickers))
        current_tickers = all_tickers[chunk_start:chunk_end]
        
        print(f"\nProcessing chunk {chunk_start//CHUNK_SIZE + 1} of {(len(all_tickers) + CHUNK_SIZE - 1)//CHUNK_SIZE}")
        print(f"Tickers {chunk_start + 1} to {chunk_end} of {len(all_tickers)}")
        
        # Initialize chunk stockies
        stockies = {}  # Create dataframes of stock data for iteration
        
        # Process current chunk of tickers
        for ticker in current_tickers:
            try:
                # Get stock price history using schwabdev
                stock_data = get_price_history_with_schwabdev(
                    client=client,
                    ticker=ticker,
                    period_type=period_type,
                    period=period,
                    frequency_type=frequency_type,
                    frequency=frequency,
                    start_time=start_time,
                    end_time=end_time,
                    need_extended_hours_data=need_extended_hours_data,
                    need_previous_close=need_previous_close,
                    max_retries=3,
                    retry_delay=1
                )
                
                if not stock_data or 'candles' not in stock_data:
                    print(f"No data available for {ticker}")
                    continue
                
                # Convert to DataFrame
                stahks = pd.DataFrame(stock_data['candles'])
                
                # Ensure all required fields are present
                required_fields = ['datetime', 'open', 'high', 'low', 'close', 'volume']
                if not all(field in stahks.columns for field in required_fields):
                    print(f"Missing required fields for {ticker}. Available columns: {stahks.columns}")
                    continue
                
                # Rename columns to match the required format
                stahks.rename(columns={
                    'datetime': 'Datetime',
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                }, inplace=True)
                
                # Convert Datetime to EST
                stahks['Datetime'] = pd.to_datetime(stahks['Datetime'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('US/Eastern').dt.tz_localize(None)

                #Skip stock if there is insufficient amount of data
                end_check = stahks['Datetime'].max()
                start_check = stahks['Datetime'].min()
                daydiff = end_check.weekday() - start_check.weekday()
                days = ((end_check-start_check).days - daydiff) / 7 * 5 + min(daydiff,5) - (max(end_check.weekday() - 4, 0) % 5)
                
                stahks['Ticker'] = ticker
                stahks['Date'] = stahks['Datetime'].dt.date
                stahks = stahks.merge(open_close_schedule,how = 'left', on = 'Date')

                # Calculate average volume
                rolling_lookback_int = int(rolling_lookback)
                stahks['10_Day_Avg_Vol'] = stahks.Volume.rolling(rolling_lookback_int, min_periods=rolling_lookback_int).mean()
                stahks['10_Day_Avg_Vol'] = stahks['10_Day_Avg_Vol'].fillna(float('inf'))
                stahks['Time'] = stahks['Datetime'].dt.time
                
                stahks.drop_duplicates(['Ticker','Date','Time'],inplace = True,ignore_index=True)
                
                if len(stahks.index) < (days * tickers_per_day):
                    continue
                    
                # Calculate additional metrics
                cond = (stahks['Time'] == stahks['market_open'])
                stahks['Day_Open_Low'] = stahks[cond].groupby('Date', as_index=True)['Low'].transform('min').ffill()

                stahks['After Hours'] = (stahks['Time'] > stahks['market_close']) | (stahks['Time'] < stahks['market_open'])

                cond_2 = (stahks['After Hours'] == True)
                stahks['Pre-Market High'] = stahks[cond_2].groupby('Date', as_index=True)['High'].transform('max')
                
                stahks = stahks.ffill(axis=0)
                stahks = stahks.bfill(axis=0)

                # Calculate VWAP metrics
                stahks['VWAP_Row'] = stahks['Volume']*((stahks['High']+stahks['Low']+stahks['Close'])/3)
                stahks['VWAP'] = stahks.groupby('Date')['VWAP_Row'].transform('cumsum')/stahks.groupby('Date')['Volume'].transform('cumsum')
                # stahks['VWAP_STD_1'] = stahks['VWAP'] - stahks.groupby('Date')['VWAP'].transform('std')
                # stahks['Color_Bar'] = np.where(stahks['Open']<=stahks['Close'], 'Green', 'Red')
                stahks['Day_Close'] = (stahks['Time'] == stahks['market_close'])

                stockies[ticker] = pd.DataFrame(stahks, columns=stahks.keys())
                # print(f"{ticker} processed successfully.")
                
            except Exception as e:
                print(f"Error processing {ticker}: {str(e)}")
                continue
        
        # Process strategies for current chunk
        RESULT_INDEXER = len(stocks_to_trade)  # Start from current length of results
        COMBO_INDEXER = 0
        
        for strategy in combinations:
            print(strategy,(datetime.now() - start_clock))
            chunk_tickers = list(stockies.keys())
            for ticker in chunk_tickers:

                # Calculate signals
                high_vol_sig = np.where(stockies[ticker]['Volume'] == stockies[ticker].groupby('Date')['Volume'].transform('max'),'True','False')
                stockies[ticker]['high_vol_sig'] = high_vol_sig
                
                price_sig = np.where((stockies[ticker]['High']-stockies[ticker]['Day_Open_Low'])/stockies[ticker]['Day_Open_Low'] >= strategy[price_spike_thresh_index],'True','False')
                stockies[ticker]['price_sig'] = price_sig
                
                before_time = np.where(stockies[ticker]['Time'] <= strategy[time_sig_thresh_index], 'True','False')
                stockies[ticker]['before_time'] = before_time 
                
                # green_bar = np.where(stockies[ticker]['Color_Bar'] == 'Green', 'True','False')
                # stockies[ticker]['green_bar'] = green_bar
                
                vol_spike_sig = np.where(stockies[ticker]['Volume'] > strategy[vol_spike_thresh_index] * stockies[ticker]['10_Day_Avg_Vol'],'True','False')
                stockies[ticker]['vol_spike_sig'] = vol_spike_sig
                
                high_price_sig = np.where(stockies[ticker]['High'] >= stockies[ticker].groupby('Date')['Close'].transform('max'),'True','False')
                stockies[ticker]['high_price_sig'] = high_price_sig
                
                stockies[ticker]['sell_time'] = np.where(stockies[ticker]['Time'] == strategy[sell_time_threshold_index],'True','False')
                
                stockies[ticker]['high_of_day'] = stockies[ticker].groupby('Date')['High'].transform('max')

                stockies[ticker]['Grab_Price_Signal'] = np.where((high_vol_sig == 'True') 
                                                                 & (vol_spike_sig == 'True') 
                                                                 & (price_sig == 'True') 
                                                                 & (high_price_sig == 'True') 
                                                                 & (before_time == 'True'),
                                                                 'True','False')

                stockies[ticker]['Close_Condition'] = 'False'

                TEMP_SIGNAL_DAY = stockies[ticker]['Date'][0] - timedelta(days=10)
                TARGET_ENTRY_PRICE = 0 
                TARGET_ENTRY_PRICE_2 = 0
                TEMP_SIGNAL_TIME = time(hour = 19, minute = 30, second = 0)
                VOLUME_SPIKE = 0
                PRICE_SPIKE = 0

                for index, row in stockies[ticker].iterrows(): 
                    
                    if (row['Grab_Price_Signal'] == 'True') & (row['Date'] == day_of_backtest):
                        TEMP_SIGNAL_DAY = row['Date']
                        TARGET_ENTRY_PRICE = row['VWAP']
                        TEMP_SIGNAL_TIME = row['Time']
                        VOLUME_SPIKE = row['Volume']/row['10_Day_Avg_Vol']
                        PRICE_SPIKE = (row['High']-row['Day_Open_Low'])/row['Day_Open_Low']
                        YESTERDAY_HIGH = row['high_of_day']

                    if (row['Close']<=TARGET_ENTRY_PRICE) & (row['Day_Close'] == True) & (row['Date'] == TEMP_SIGNAL_DAY):
                        print('Got in thur')
                        stocks_to_trade.at[RESULT_INDEXER,'Previous Day Close'] = row['Close']
                        stocks_to_trade.at[RESULT_INDEXER,'Ticker'] = row['Ticker']
                        stocks_to_trade.at[RESULT_INDEXER,'Target Entry'] = TARGET_ENTRY_PRICE
                        stocks_to_trade.at[RESULT_INDEXER,'Signal Time'] = TEMP_SIGNAL_TIME
                        stocks_to_trade.at[RESULT_INDEXER,'Volume Spike'] = VOLUME_SPIKE
                        stocks_to_trade.at[RESULT_INDEXER,'Price Spike'] = PRICE_SPIKE
                        stocks_to_trade.at[RESULT_INDEXER,'Shares'] = int(500/TARGET_ENTRY_PRICE)
                        stocks_to_trade.at[RESULT_INDEXER,'Yesterday High'] = YESTERDAY_HIGH
                        stocks_to_trade.at[RESULT_INDEXER,'Time Threshold'] = strategy[time_sig_thresh_index]
                        stocks_to_trade.at[RESULT_INDEXER,'Buy Time Threshold'] = strategy[buy_time_threshold_index]
                        stocks_to_trade.at[RESULT_INDEXER,'Sell_Time'] = strategy[sell_time_threshold_index]                 
                        stop_price = TARGET_ENTRY_PRICE + (TARGET_ENTRY_PRICE * strategy[stop_index])
                        sell_price = TARGET_ENTRY_PRICE - (TARGET_ENTRY_PRICE * strategy[target_index])
                        stocks_to_trade.at[RESULT_INDEXER,'Stop Price'] = stop_price
                        stocks_to_trade.at[RESULT_INDEXER,'Sell Price'] = sell_price

                        RESULT_INDEXER +=1                
            COMBO_INDEXER +=1 
        
        # Clear chunk data to free memory
        del stockies
        print(f"Completed chunk {chunk_start//CHUNK_SIZE + 1}. Current results: {len(stocks_to_trade)} stocks")
    
    # Save final results
    output_date = next_business_day(day_of_backtest)
    output_file_path = 'screener/daily_screener_signals/' + str(output_date) + '.csv'
    stocks_to_trade.to_csv(output_file_path, index=True, header=True)

    print(datetime.now() - start_clock)
    print('Completed Screener Successfully')
    
    return stocks_to_trade

def run_premarket_screener(client, symbols_df):
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
    today_start = int(pd.Timestamp(today - timedelta(days=1)).replace(hour=0, minute=0, second=0).timestamp() * 1000)
    today_end = int(pd.Timestamp(today).replace(hour=23, minute=59, second=59).timestamp() * 1000)

    # Get market open time
    market_schedule = pd.DataFrame(mcal.get_calendar('NYSE').schedule(start_date=today, end_date=today))
    market_open = market_schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
    
    # Keep track of symbols to remove
    symbols_to_remove = []

    # Prepare symbols to check
    symbols_to_check = filtered_df[['Ticker', 'Yesterday High']].dropna().values.tolist()

    for symbol, yesterday_high in symbols_to_check:
        try:
            response = get_price_history_with_schwabdev(
                client=client,
                ticker=symbol,
                period_type='day',
                period=2,
                frequency_type='minute',
                frequency=5,
                need_extended_hours_data=True,
                need_previous_close=True,
                start_time=today_start,
                end_time=today_end
            )

            if response is None or not response.get('candles'):
                symbols_to_remove.append(symbol)
                continue
            
            # Filter for premarket candles only
            premarket_highs = []
            print(f"Premarket prices for {symbol}:")
            for candle in response['candles']:
                candle_time = pd.to_datetime(candle['datetime'], unit='ms').tz_localize('UTC').tz_convert('US/Eastern')
                
                # Check if it's before market open on the current day
                if candle_time < market_open and candle_time.date() == today:
                    premarket_highs.append(candle['high'])
                    print(f"Time: {candle_time}, High: {candle['high']}")
            
            if not premarket_highs:
                print(f"No premarket data found for {symbol}")
                symbols_to_remove.append(symbol)
                continue
                
            # Calculate premarket high
            premarket_high = max(premarket_highs)  # Get the maximum high value
            print(f"{symbol} - Premarket high: {premarket_high}, Yesterday high: {yesterday_high}")
            
            # Remove symbols where premarket high exceeds yesterday's high
            if premarket_high > yesterday_high:
                print(f"Removing {symbol}: premarket high ({premarket_high}) > yesterday high ({yesterday_high})")
                symbols_to_remove.append(symbol)
            
        except Exception as e:
            logger.error(f"Error processing {symbol}: {str(e)}")
            symbols_to_remove.append(symbol)
            continue
    
    # Remove the identified symbols from the DataFrame
    filtered_df = filtered_df[~filtered_df['Ticker'].isin(symbols_to_remove)]
    # Save the filtered DataFrame to a CSV file
    filtered_df.to_csv('screener/premarket_screener_signals/' + str(datetime.now().date()) + '.csv', index=False)
    # Print removed and remaining symbols
    print("Removed symbols:", symbols_to_remove)
    print("Remaining symbols:", filtered_df['Ticker'].tolist())
    return filtered_df