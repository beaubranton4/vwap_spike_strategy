# Standard library imports
import glob
import json
import os
import pprint
import random
import sys
import traceback
from datetime import date, datetime, time, timedelta
import logging

# Third party imports
import base64
from venv import logger
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import pytz
import requests

# Local imports
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), '..')))
from config import *
from functions.schwab_functions import get_price_history_with_schwabdev  # Explicit import
from functions.manage_authentication import get_authenticated_client

# If you still need other functions:
from functions import *



############################################## ALL FUNCTIONS ########################################################

def next_business_day(current_date):
    """
    Find the next business day in NYSE calendar after the given date.
    
    Args:
        current_date: datetime object or date
    Returns:
        date: Next business day
    """
    # Convert to date if datetime
    if isinstance(current_date, datetime):
        current_date = current_date.date()
    
    # Get NYSE calendar for a reasonable date range
    nyse = mcal.get_calendar('NYSE')
    nyse_days = nyse.valid_days(
        start_date=current_date - timedelta(days=5),
        end_date=current_date + timedelta(days=5)
    )
    
    # Convert to list of dates
    valid_trading_days = pd.Series(nyse_days).dt.date
    
    # Find the next valid trading day
    for trading_day in valid_trading_days:
        if trading_day > current_date:
            return trading_day
            
    return None  # Return None if no next trading day found in range

def last_trading_day(current_date):
    """
    Find the last business day in NYSE calendar before the given date.
    
    Args:
        current_date: datetime object or date
    Returns:
        datetime: Last business day in Eastern timezone
    """
    # Convert to date if datetime
    if isinstance(current_date, datetime):
        current_date = current_date.date()
    
    # Get NYSE calendar for a reasonable date range
    nyse = mcal.get_calendar('NYSE')
    nyse_days = nyse.valid_days(
        start_date=current_date - timedelta(days=5),
        end_date=current_date + timedelta(days=5)
    )
    
    # Convert to list of dates
    valid_trading_days = pd.Series(nyse_days).dt.date
    
    # Find the last valid trading day
    last_day = None
    for trading_day in valid_trading_days:
        if trading_day >= current_date:
            break
        last_day = trading_day
            
    if last_day is None:
        return None
        
    return last_day


######################################## GET BUY/SELL SIGNAL FUNCTION ##################################################


#MUST MAKE SURE THAT THE SIGNALS RETURNED MATCH UP WITH THE BUY AND SELL FUNCTION COMMANDS
#Generates the type of buy or sell signals used in the buying and selling functions by taking in a row of stock data
def buy_sell_signal(signal,
                    ok_to_buy,
                    time,
                    high_price,
                    low_price,
                    after_hours,
                    day_close,
                    date,
                    stop,
                    target,
                    sell_time_thresh,
                    buy_time_thresh,
                    yesterday_high,
                    premarket_high,
                    target_entry_price):
    
    #SHORT STRATEGIES
    if(signal == 'Short'): 
        
        #BUY (check that all signals triggered, positioning is neutral, not after hours and we didn't buy it today yet)
        if ((ok_to_buy == True) 
            & (time <= buy_time_thresh) 
            & (buy_time_thresh <= sell_time_thresh)
            & (high_price>=target_entry_price) 
            & (POSITION == 'Neutral') 
            & (after_hours==False) 
            & (BOUGHT_TODAY != date) 
            & (yesterday_high >= premarket_high)):
            return 'Short (Target Price Cross)'
        #SELL (check that the position)
        elif (ENTRY_PRICE+(ENTRY_PRICE*stop) <= high_price) & ((POSITION == 'Short') | (POSITION == 'Long')): 
            #print('sell',date)
            return 'Sell (Stop Loss)'
        elif (ENTRY_PRICE-(ENTRY_PRICE*target) >= low_price) & ((POSITION == 'Short') | (POSITION == 'Long')):
            #print('sell',date)
            return 'Sell (Target Hit)'
        elif (((sell_time_thresh == time) | (day_close == True)) & (POSITION == 'Short') | (POSITION == 'Long')): 
            #print('sell',date)
            return 'Sell (At Time Threshold)'
        else:
            return 'none'
    if(signal == 'Long'):
        return 'none' #input long strategy signal conditions
    else:
        return 'none'
    
####################################### CALCULATE TRADE STATS ########################################################

#Returns details for results table based on the type of sell signal (profit,exit,win/loss,type of sale)
#might need entry_price passed in
def calculate_sell_results(signal, row_close,position_size,stop,target):
    
    if (signal == 'Sell (Stop Loss)'):
        profit = (position_size - (position_size*(1+stop)))
        exit = ENTRY_PRICE +(ENTRY_PRICE*stop)
        win_loss = 'Loss'
        sell_type = 'Sell (Stop Loss)'
        return [profit,exit,win_loss,sell_type]

    if (signal == 'Sell (Target Hit)'):
        profit = ((1+target)*(position_size))-(position_size)
        exit = ENTRY_PRICE - (ENTRY_PRICE*target)
        win_loss = 'Win'
        sell_type = 'Sell (Target Hit)'
        return [profit,exit,win_loss,sell_type]

    if (signal == 'Sell (At Time Threshold)'):
        profit = (((ENTRY_PRICE-row_close)/ENTRY_PRICE)*position_size)
        exit = row_close
        win_loss = np.where(((ENTRY_PRICE-row_close)/ENTRY_PRICE)>0,'Win','Loss')
        sell_type = 'Sell (At Time Threshold)'
        return [profit,exit,win_loss,sell_type]

    
######################################### BUY AND SELL FUNCTIONS ########################################################
#Function that ultimately buys and sells stock based on signals output by the buy_sell_signal function
def buy_sell(signal,
             date,
             ticker,
             open_price,
             close_price,
             time,
             volume,
             previous_day_close,
             volume_spike,
             price_spike,
             target_entry_price,
             position_size,
             stop,
             target):

    global POSITION, ENTRY_PRICE, ENTRY_TIME, BUYS, BOUGHT_TODAY
    global RESULT_INDEXER, ACCOUNT_SIZE
    global results  # Add these globals
    
    #BUY - Currently the only buy signal, but could create function for the different buy types
    if (signal == 'Short (Target Price Cross)'):
        POSITION = 'Short'
        ENTRY_TIME = time
        ENTRY_PRICE = np.where(open_price>target_entry_price,open_price,target_entry_price)
        BUYS += 1
        logger.info(f"Buy signal found for {ticker} on {date}")

    #SELL - Will calculate sell stats based on the signal using the calculate_sell_results function 
    elif ((signal == 'Sell (Target Hit)')
         |(signal == 'Sell (Stop Loss)')
         |(signal == 'Sell (At Time Threshold)')):
        POSITION = 'Neutral'
        sell_outputs = calculate_sell_results(signal,close_price,position_size,stop,target)
        profit = sell_outputs[0]
        exit = sell_outputs[1]
        win_loss = sell_outputs[2]
        sell_type = sell_outputs[3]
        results.at[RESULT_INDEXER,'Profit'] = profit
        results.at[RESULT_INDEXER,'Profit %'] = profit/position_size
        results.at[RESULT_INDEXER,'Bet Size'] = position_size
        ACCOUNT_SIZE += profit
        results.at[RESULT_INDEXER,'Date'] = date
        results.at[RESULT_INDEXER,'Ticker'] = ticker
        results.at[RESULT_INDEXER,'Account Size'] = ACCOUNT_SIZE
        results.at[RESULT_INDEXER,'Win/Loss'] = win_loss
        results.at[RESULT_INDEXER,'Target Entry'] = float(target_entry_price)
        results.at[RESULT_INDEXER,'Entry'] = ENTRY_PRICE  
        results.at[RESULT_INDEXER,'Exit'] = exit    
        results.at[RESULT_INDEXER,'Entry Time'] = ENTRY_TIME
        results.at[RESULT_INDEXER,'Exit Time'] = time
        results.at[RESULT_INDEXER,'Volume'] = volume
        results.at[RESULT_INDEXER,'Type'] = sell_type
        results.at[RESULT_INDEXER,'Volume Spike'] = volume_spike
        results.at[RESULT_INDEXER,'Price Spike'] = price_spike
        results.at[RESULT_INDEXER,'Previous Day Close'] = previous_day_close
        #results.at[RESULT_INDEXER,'Premarket Volume'] = 
        #results.at[RESULT_INDEXER,'Premarket Change'] = 
        BOUGHT_TODAY = date
        RESULT_INDEXER += 1
        logger.info(f"Sell for {ticker} on {date}, Result #{RESULT_INDEXER}")

def run_vwap_spike_screener_backtest(client, ticker_list, combinations, 
                           period_type, period, frequency_type, frequency,
                           start_time, end_time, need_extended_hours_data, 
                           need_previous_close, rolling_lookback, 
                           price_spike_thresh_index, time_sig_thresh_index, buy_time_threshold_index,
                           vol_spike_thresh_index, sell_time_threshold_index,
                           stop_index, target_index, strategy_note_input):
    """
    Run the VWAP spike strategy screener to identify trading opportunities
    
    Args:
        client (schwabdev.Client): Authenticated Schwab client
        ticker_list (pd.DataFrame): DataFrame containing ticker symbols to screen
        combinations (list): List of strategy parameter combinations to test
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
    
    logger = logging.getLogger('main')
    start_clock = datetime.now()
    
    global ENTRY_PRICE, POSITION, ENTRY_TIME, ACCOUNT_SIZE, BUYS, RESULT_INDEXER, BOUGHT_TODAY
    global TEMP_SIGNAL_DAY, OK_TO_BUY_DAY, TARGET_ENTRY_PRICE, SIGNAL_TIME
    global VOLUME_SPIKE, PRICE_SPIKE, OPTIMAL_ENTRY_TIME, OPTIMAL_EXIT_TIME
    global PREVIOUS_VOLUME_SPIKE, PREVIOUS_PRICE_SPIKE, PREVIOUS_TARGET_ENTRY_PRICE, PREVIOUS_SIGNAL_TIME
    global PREVIOUS_DAY_CLOSE, RESULT_INDEXER
    global ACCOUNT_SIZE
    global results, inputs, signal
    global input_indexer

    # Initialize variables
    input_indexer = 0  # Add this line

    # Convert timestamps to ET datetime
    eastern = pytz.timezone('US/Eastern')
    start_of_backtest = datetime.fromtimestamp(int(start_time) / 1000).astimezone(eastern)
    end_of_backtest = datetime.fromtimestamp(int(end_time) / 1000).astimezone(eastern)

    # Get NYSE calendar schedule
    nyse = mcal.get_calendar('NYSE')
    open_close_schedule = pd.DataFrame(nyse.schedule(start_date=start_of_backtest, end_date=end_of_backtest))
    
    open_close_schedule.index.names = ['Date']
    open_close_schedule.reset_index(inplace=True)

    # Convert market times to ET
    open_close_schedule['market_open'] = open_close_schedule['market_open'].dt.tz_convert('US/Eastern')
    open_close_schedule['market_close'] = open_close_schedule['market_close'].dt.tz_convert('US/Eastern')

    # Extract date and time components
    open_close_schedule['Date'] = open_close_schedule['market_open'].dt.date
    open_close_schedule['market_open'] = open_close_schedule['market_open'].dt.time
    open_close_schedule['market_close'] = (open_close_schedule['market_close'] - pd.Timedelta(minutes=30)).dt.time
    
    # print(open_close_schedule)

    strategy_note = strategy_note_input  # Add this if needed
    
    logger.info(f"Starting VWAP spike screener backtest with {len(ticker_list)} tickers")
    
    # Get tickers list
    if 'Ticker' not in ticker_list.columns:
        print("Column 'Ticker' not found in the DataFrame.")
        return pd.DataFrame()

    
    
    tickers_df = ticker_list[['Ticker']].dropna()
    all_tickers = tickers_df['Ticker'].unique().tolist()

    all_tickers = ['MVIS']

    # Initialize chunk stockies
    stockies = {}  # Create dataframes of stock data for iteration
    
    inputs = pd.DataFrame(columns=['Account Size',
                               'Bet_Size',
                               'Stop',
                               'Target',
                               'Vol Spike Thresh',
                               'Price Spike Thresh',
                               'Signal Time Threshold',
                               'Buy Time Threshold',
                               'Sell_Time',
                               'Signals',
                               'Buys',
                               'Win %',
                               'Average Win',
                               'Strategy Note'])
    
    # Process current chunk of tickers
    for ticker in all_tickers:
        try:
            logger.info(f"Processing {ticker}")
            
            stahks = process_stock_data(
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
                rolling_lookback=rolling_lookback,
                open_close_schedule=open_close_schedule,
                tickers_per_day=tickers_per_day
            )
            
            if stahks is not None:
                stockies[ticker] = pd.DataFrame(stahks, columns=stahks.keys())
                # print(f"{ticker} processed successfully.")
            else:
                logger.error(f"Error processing {ticker} line 376")
                continue
            
        except Exception as e:
            logger.error(f"1 - Error processing {ticker}: {str(e)}")
            logger.error(traceback.format_exc())
            continue

    # Process strategies for current chunk
    # RESULT_INDEXER = len(stocks_to_trade)  # Start from current length of results
    # COMBO_INDEXER = 0
    
    for strategy in combinations:

        ACCOUNT_SIZE = 100000  # Add initial account size
        SIGNALS = 0
        BUYS = 0
        RESULT_INDEXER = 0

        results = pd.DataFrame(columns=['Ticker',
                                    'Date',
                                    'Volume Spike',
                                    'Price Spike',
                                    'Previous Day Close',
                                    'Signal Time',
                                    'Target Entry',
                                    'Entry Time',
                                    'Exit Time',
                                    'Account Size',
                                    'Bet Size',
                                    'Win/Loss', 
                                    'Profit',
                                    'Profit %',
                                    'Entry',
                                    'Exit',
                                    'Type',
                                    'Volume',
                                    'Premarket Volume',
                                    'Premarket Change'])
        
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

            stockies[ticker]['Grab_Price_Signal'] = np.where((high_vol_sig == 'True') 
                                                                & (vol_spike_sig == 'True') 
                                                                & (price_sig == 'True') 
                                                                & (high_price_sig == 'True') 
                                                                & (before_time == 'True'),
                                                                'True','False')

            stockies[ticker]['Close_Condition'] = 'False'

            #Checks that all criteria was checked (X days ago) and that we are just waiting for buy signal (price crosses above VWAP)
            stockies[ticker]['Ok_To_Buy'] = False
            #Creates the Buy and Sell Signal Column for iteration
            stockies[ticker]['Buy_Sell_Signal'] = 'None'
            #Create target entry price column
            stockies[ticker]['Target_Entry_Price'] = 100000.0

            # Create Last_Trading_Day column by applying last_trading_day function to each Date
         
            
            # Save stockies to see its structure 
            stockies[ticker].to_csv('backtest_results/debugging/stockies_structure.csv', index=True, header=True)

            ####CREATE BUY AND SELL SIGNALS IN DATA FRAME BASED ON STRATEGY PARAMETERS

            # Create a dataframe of rows where Grab_Price_Signal is True
            signal_rows = stockies[ticker][stockies[ticker]['Grab_Price_Signal'] == 'True'].copy()
            # For each date, keep only the row with the latest time
            signal_rows = signal_rows.sort_values('Time').groupby('Date').last().reset_index()
            # Get distinct dates from signal_rows
            signal_dates = signal_rows['Date'].unique()
            
            # Create dataframe of closing prices on signal days
            valid_signals = stockies[ticker][
                (stockies[ticker]['Date'].isin(signal_dates)) & 
                (stockies[ticker]['Day_Close'] == True)
            ].copy()

            # Join signal_rows with valid_signals on Date
            signal_rows = signal_rows.merge(valid_signals[['Date', 'Close']], 
                                         on='Date', 
                                         how='inner',
                                         suffixes=('', '_eod'))
            
            # Filter for rows where closing price is below VWAP
            signal_rows = signal_rows[signal_rows['Close_eod'] < signal_rows['VWAP']]
           
            signal_rows.to_csv('backtest_results/debugging/signals_rows.csv', index=True, header=True)

            # Ok to buy if signal is found on prior day and close is below VWAP spike. 
            # Also remove after hours data
            # COULD Also remove rows where pre-market high surpasses yesterday's high
            stockies[ticker]['Ok_To_Buy'] = stockies[ticker]['Last_Trading_Day'].isin(signal_rows['Date']) & (stockies[ticker]['After Hours'] == False)

            # Create mapping dictionaries from signal_rows for each value we want to map
            target_entry_map = signal_rows.set_index('Date')['VWAP'].to_dict()
            signal_time_map = signal_rows.set_index('Date')['Time'].to_dict()
            
            # Calculate Volume Spike and Price Spike in signal_rows
            signal_rows['Volume_Spike'] = signal_rows['Volume'] / signal_rows['10_Day_Avg_Vol']
            signal_rows['Price_Spike_From_Open'] = (signal_rows['High'] - signal_rows['Day_Open_Low']) / signal_rows['Day_Open_Low']
            
            volume_spike_map = signal_rows.set_index('Date')['Volume_Spike'].to_dict()
            price_spike_map = signal_rows.set_index('Date')['Price_Spike_From_Open'].to_dict()
            previous_close = signal_rows.set_index('Date')['Close'].to_dict()

            # Map values to main dataframe
            stockies[ticker]['Target_Entry_Price'] = stockies[ticker]['Last_Trading_Day'].map(target_entry_map)
            stockies[ticker]['Signal_Time'] = stockies[ticker]['Last_Trading_Day'].map(signal_time_map)
            stockies[ticker]['Volume_Spike'] = stockies[ticker]['Last_Trading_Day'].map(volume_spike_map)
            stockies[ticker]['Price_Spike_From_Open'] = stockies[ticker]['Last_Trading_Day'].map(price_spike_map)
            stockies[ticker]['Previous_Day_Close'] = stockies[ticker]['Last_Trading_Day'].map(previous_close)
            
            #Consolidate tables to only days where we might buy and sell
            stonks = stockies[ticker][(stockies[ticker]['Ok_To_Buy'] == True)]
            stonks.to_csv(f'./backtest_results/debugging/BACKTEST_STONKS_{ticker}.csv', index=True, header=True)

            #If there are no signals - skip to next stock.
            if len(stonks) == 0:
                logger.info(f"No signals found for {ticker}. Skipping 5 buy and sell signal simulation")
                continue      

            #########################################  Use 5m DATA TO CALCULATE BACKTEST RESULTS ##################################################
            
            stonks_5m = pd.DataFrame()

            unique_tickers_dates = stonks[['Ticker', 'Date']].drop_duplicates()

            for _, row in unique_tickers_dates.iterrows():
                ticker = row['Ticker']
                date = row['Date']

                # Retrieve 5m stock data for the entire day
                five_min_data = process_stock_data(
                    client=client,
                    ticker=ticker,
                    period_type=period_type,
                    period=period,
                    frequency_type=frequency_type,
                    frequency=5,
                    start_time=str(int((pd.Timestamp(date) - pd.Timedelta(days=15)).timestamp())*1000),
                    end_time=str(int((pd.Timestamp(date) + pd.Timedelta(days=1)).timestamp())*1000),
                    need_extended_hours_data=need_extended_hours_data,
                    need_previous_close=need_previous_close,
                    rolling_lookback=rolling_lookback,
                    open_close_schedule=open_close_schedule,
                    tickers_per_day=tickers_per_day
                )

                # Join the 5m data with stonks on Ticker and Date
                five_min_data = five_min_data[five_min_data['Date'] == date]

                # Save five_min_data for debugging
                # five_min_data.to_csv(f'./backtest_results/debugging/5MIN_DATA_before_join_{ticker}_{date.strftime("%Y-%m-%d")}.csv', index=True, header=True)
                daily_values = stonks[[
                    'Ticker', 'Date', 
                    'Target_Entry_Price', 'Previous_Day_Close', 
                    'Volume_Spike', 'Price_Spike_From_Open', 'Signal_Time'
                ]].drop_duplicates()
                # Save daily values to CSV for debugging
                daily_values.to_csv(f'./backtest_results/debugging/BACKTEST_DAILY_VALUES_{ticker}.csv', index=True, header=True)
                
                merged_data = five_min_data.merge(daily_values, on=['Ticker', 'Date'], how='left')
                stonks_5m = pd.concat([stonks_5m, merged_data], ignore_index=True)
                stonks_5m['Ok_To_Buy'] = True

            # Save stonks_5m to a CSV file
            stonks_5m.to_csv('./backtest_results/debugging/5m_test.csv', index=False, header=True)
            # THIS IS WHERE I CAN BRING IN 5m bars, join to stonks and use it to calculate results

        #########################################  BACKTEST IMPLEMENTATION AND SIMULATION OF BUY AND SELL SIGNALS  ##################################################
            
            POSITION = 'Neutral'
            BOUGHT_TODAY = stockies[ticker]['Date'][0] - timedelta(days=1)
            ENTRY_PRICE = 0.0 
            ENTRY_TIME = stockies[ticker]['Time'][0]
            
            #USING IN-HOUSE FUNCTION SIMULATE (ITERATING THROUGH DAYS, BUYING AND SELLING BASED ON SIGNALS)
            #Iterate over rows to fill in results table with buy and sell actions
            for index, row in stonks_5m.iterrows():    
                signal = buy_sell_signal('Short',
                                        row['Ok_To_Buy'],
                                        row['Time'],
                                        row['High'],
                                        row['Low'],
                                        row['After Hours'],
                                        row['Day_Close'],
                                        row['Date'],
                                        strategy[stop_index],
                                        strategy[target_index],
                                        strategy[sell_time_threshold_index],
                                        strategy[buy_time_threshold_index],
                                        row['Yesterday High'],
                                        row['Pre-Market High'],
                                        row['Target_Entry_Price'])
                if signal == 'none':
                    continue
                position_size = ACCOUNT_SIZE * strategy[bet_size_index]    
                logger.info(f"1st signal: {signal} for {row['Date']}")
                buy_sell(signal,
                        row['Date'],
                        row['Ticker'],
                        row['Open'],
                        row['Close'],
                        row['Time'],
                        row['Volume'],
                        row['Previous_Day_Close'],
                        row['Volume_Spike'],
                        row['Price_Spike_From_Open'],
                        row['Target_Entry_Price'],
                        position_size,
                        strategy[stop_index],
                        strategy[target_index])
                
                signal = buy_sell_signal('Short',
                                        row['Ok_To_Buy'],
                                        row['Time'],
                                        row['High'],
                                        row['Low'],
                                        row['After Hours'],
                                        row['Day_Close'],
                                        row['Date'],
                                        strategy[stop_index],
                                        strategy[target_index],
                                        strategy[sell_time_threshold_index],
                                        strategy[buy_time_threshold_index],
                                        row['Yesterday High'],
                                        row['Pre-Market High'],
                                        row['Target_Entry_Price'])
                if signal == 'none':
                    continue
                logger.info(f"2nd signal: {signal} for {row['Date']}")
                position_size = ACCOUNT_SIZE * strategy[bet_size_index]    
                buy_sell(signal,
                        row['Date'],
                        row['Ticker'],
                        row['Open'],
                        row['Close'],
                        row['Time'],
                        row['Volume'],
                        row['Previous_Day_Close'],
                        row['Volume_Spike'],
                        row['Price_Spike_From_Open'],
                        row['Target_Entry_Price'],
                        position_size,
                        strategy[stop_index],
                        strategy[target_index])
                
            #HOW DO I CHECK FOR BUY AND SELL IN THE SAME STRATEGY (JUST COPY PASTE IT AND DO IT TWICE)
            #results['Optimal Entry'] = stockies[results['Date']==stockies['Date']].groupby('Date')['High'].transform('max')
            #results['Optimal Exit'] = stockies[results['Date']==stockies['Date']].groupby('Date')['Low'].transform('min')
            #results['Optimal Entry Time'] =stockies[results['Date']==stockies['Date']].groupby('Date')['High'].transform('max')
            #results['Optimal Exit Time'] =
            #results['Left On Table'] = ((results['Optimal Entry']*results['Bet Size'])-(results['Optimal Exit']*results['Bet Size']))-((results['Bet Size'])-(STOP*results['Bet Size']))
            
            logger.info(f"Ticker: {ticker}, Buys: {BUYS}, Result Indexer: {RESULT_INDEXER}")
        inputs.at[input_indexer,'Account Size'] = ACCOUNT_SIZE
        inputs.at[input_indexer,'Bet_Size'] = strategy[bet_size_index]
        inputs.at[input_indexer,'Stop'] = strategy[stop_index]
        inputs.at[input_indexer,'Target'] = strategy[target_index]
        inputs.at[input_indexer,'Vol Spike Thresh'] = strategy[vol_spike_thresh_index]
        inputs.at[input_indexer,'Price Spike Thresh'] = strategy[price_spike_thresh_index]
        inputs.at[input_indexer,'Signal Time Threshold'] = strategy[time_sig_thresh_index]
        inputs.at[input_indexer,'Buy Time Threshold'] = strategy[buy_time_threshold_index]
        inputs.at[input_indexer,'Signals'] = SIGNALS
        inputs.at[input_indexer,'Buys'] = BUYS
        inputs.at[input_indexer,'Average Win'] = results['Profit %'].mean()
        inputs.at[input_indexer,'#Hit Target'] = len(results[results['Type'] == 'Sell (Target Hit)'])
        inputs.at[input_indexer,'#Hit Stop'] = len(results[results['Type'] == 'Sell (Stop Loss)'])
        inputs.at[input_indexer,'#Sold at Time']= len(results[results['Type'] == 'Sell (At Time Threshold)'])
        inputs.at[input_indexer,'Sell_Time']= strategy[sell_time_threshold_index]
        inputs.at[input_indexer,'Strategy Note']= strategy_note
        try:
            inputs.at[input_indexer,'Win %'] = (len(results[results['Win/Loss']=='Win'])/len(results['Win/Loss']))
        except:
            pass
        # tick_list = tickers
        # Write each dataframe to a different worksheet.
        # results = pd.merge(results,tick_list[['Ticker','Market Capitalization','Sector','Shares Float']],on = 'Ticker', how = 'left')
        current_date = datetime.now().strftime("%Y-%m-%d")
        results.to_csv(f'backtest_results/detailed_results/{strategy_note_input}_backtest_strategy_{input_indexer}_on_{current_date}.csv', index=False, header=True)
        input_indexer += 1

    ################################################### CLEAN OUTPUTS ####################################################

        print ("Ending Account Size: ", ACCOUNT_SIZE)
        print ("Signals: ", SIGNALS)
        print ("Buys:", BUYS)

        try:
            print ("Win %: ", len(results[results['Win/Loss']=='Win'])/len(results['Win/Loss'])*100,"%")
            print("Avg. Win: ", results['Profit %'].mean()*100,"%")

        except:
            pass

    # plot = px.line(results, x = results.index.values, y = 'Account Size', title = 'Equity Curve')
    # plot.show()
    current_date = datetime.now().strftime("%Y-%m-%d")
    inputs.to_csv(f'backtest_results/{strategy_note_input}_backtest_summary_{current_date}.csv', index=True, header=True)
    print(datetime.now() - start_clock)

    # Final summary
    runtime = datetime.now() - start_clock
    logger.info(f"VWAP spike screener completed in {runtime}")
    logger.info(f"Total signals found: {SIGNALS}")
    logger.info(f"Total buys executed: {BUYS}")
    try:
        win_rate = len(results[results['Win/Loss']=='Win'])/len(results['Win/Loss'])*100
        avg_win = results['Profit %'].mean()*100
        logger.info(f"Win rate: {win_rate:.1f}%, Average win: {avg_win:.1f}%")
    except:
        logger.info("No trades executed")
    
    return results

#Function that calculates various metrics for a stock given candle information such as high, low, close, volume, etc.
def process_stock_data(client, ticker, period_type, period, frequency_type, frequency, 
                      start_time, end_time, need_extended_hours_data, need_previous_close, 
                      rolling_lookback, open_close_schedule, tickers_per_day):
    """
    Process stock price history data and return formatted DataFrame
    """
    # Use 'main' logger instead of creating a new one
    logger = logging.getLogger('main')
    
    try:
        # Get stock price history
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

        # Save open_close_schedule to CSV for debugging
        open_close_schedule.to_csv('backtest_results/debugging/open_close_schedule.csv', index=True, header=True)
        
        if not stock_data or 'candles' not in stock_data:
            logger.info(f"No data available for {ticker}")
            return None
            
        # Convert to DataFrame and validate
        stahks = pd.DataFrame(stock_data['candles'])
        required_fields = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        if not all(field in stahks.columns for field in required_fields):
            logger.info(f"Missing required fields for {ticker}")
            return None
            
        logger.info(f"Processing data for {ticker}")
        # Format DataFrame
        stahks.rename(columns={
            'datetime': 'Datetime',
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        }, inplace=True)
        
        # Process datetime
        stahks['Datetime'] = pd.to_datetime(stahks['Datetime'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('US/Eastern').dt.tz_localize(None)
        
        # Check data sufficiency
        end_check = stahks['Datetime'].max()
        start_check = stahks['Datetime'].min()
        daydiff = end_check.weekday() - start_check.weekday()
        days = ((end_check-start_check).days - daydiff) / 7 * 5 + min(daydiff,5) - (max(end_check.weekday() - 4, 0) % 5)
        
        # Add basic fields
        stahks['Ticker'] = ticker
        stahks['Date'] = stahks['Datetime'].dt.date
        stahks = stahks.merge(open_close_schedule, how='left', on='Date')

        # Update market_close based on candle length if using 5m bars
        if frequency == 5:
            stahks['market_close'] = pd.to_datetime(stahks['Date'].astype(str) + ' ' + stahks['market_close'].astype(str)) + pd.Timedelta(minutes=25)
            stahks['market_close'] = stahks['market_close'].dt.time
        
        
        # Calculate volume metrics
        stahks['10_Day_Avg_Vol'] = stahks.Volume.rolling(int(rolling_lookback), min_periods=int(rolling_lookback)).mean()
        stahks['10_Day_Avg_Vol'] = stahks['10_Day_Avg_Vol'].fillna(float('inf'))
        stahks['Time'] = stahks['Datetime'].dt.time
        
        # Remove duplicates
        stahks.drop_duplicates(['Ticker','Date','Time'], inplace=True, ignore_index=True)
        
        if len(stahks.index) < (days * tickers_per_day):
            logger.info(f"Not enough data for {ticker} - skipping...")
            return None
            
        # Calculate additional metrics
        stahks['Day_Open_Low'] = stahks[stahks['Time'] == stahks['market_open']].groupby('Date', as_index=True)['Low'].transform('min').ffill()
        stahks['After Hours'] = (stahks['Time'] > stahks['market_close']) | (stahks['Time'] < stahks['market_open'])
        stahks['Pre-Market High'] = stahks[stahks['Time'] < stahks['market_open']].groupby('Date', as_index=True)['High'].transform('max')
        stahks['high_of_day'] = stahks.groupby(['Date', 'Ticker'])['High'].transform('max')
        
        # Get daily highs and shift by one trading day
        daily_highs = stahks.groupby('Date')['high_of_day'].max()
        yesterday_highs = daily_highs.shift(1)
        all_dates = stahks.groupby('Date')['Date'].max()
        last_trading_day = all_dates.shift(1)   
        
        # Map back to original DataFrame
        stahks['Yesterday High'] = stahks['Date'].map(yesterday_highs)
        stahks['Last_Trading_Day'] = stahks['Date'].map(last_trading_day)
        
        # Fill missing values with explicit downcasting handling
        # pd.set_option('future.no_silent_downcasting', True)  # Optional: opt-in to future behavior
        # stahks = stahks.ffill(axis=0)
        # stahks = stahks.bfill(axis=0)
        stahks = stahks.ffill(axis=0).bfill(axis=0)
        
        # Calculate VWAP
        stahks['VWAP_Row'] = stahks['Volume'] * ((stahks['High'] + stahks['Low'] + stahks['Close'])/3)
        stahks['VWAP'] = stahks.groupby('Date')['VWAP_Row'].transform('cumsum') / stahks.groupby('Date')['Volume'].transform('cumsum')
        stahks['Day_Close'] = (stahks['Time'] == stahks['market_close'])
        
        logger.info(f"Successfully processed {ticker} data")
        return stahks
        
    except Exception as e:
        logger.error(f"Error processing {ticker}: {str(e)}")
        logger.error(traceback.format_exc())
        return None