
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
    stocks_to_trade = pd.DataFrame(columns=['Ticker','Target Entry','Volume Spike','Price Spike',
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



############################NEW CODE



#Checks that all criteria was checked (X days ago) and that we are just waiting for buy signal (price crosses above VWAP)
        stockies[ticker]['Ok_To_Buy'] = 'False'
        #Creates the Buy and Sell Signal Column for iteration
        stockies[ticker]['Buy_Sell_Signal'] = 'None'
        #Create target entry price column
        stockies[ticker]['Target_Entry_Price'] = 100000.0

        #Temp Variables for backtest (row by row iteration)
        #Create temporary signal day variable that signaled whether or not the price_to_buy_signal was triggered during that day
        TEMP_SIGNAL_DAY = stockies[ticker]['Date'][0] - timedelta(days=1)
        #Create temporary ok to buy day variable that will trigger if the close condition for the day was satisfied (which only triggers if grab_price_signal is triggered)
        OK_TO_BUY_DAY = stockies[ticker]['Date'][0] - timedelta(days=2)
        #Initially set not to trigger and gets set on price_buy_signal
        TARGET_ENTRY_PRICE = 0.0 
        ENTRY_PRICE = 0.0 
        ENTRY_TIME = stockies[ticker]['Time'][0]
        BOUGHT_TODAY = stockies[ticker]['Date'][0] - timedelta(days=1)
        PREVIOUS_DAY_CLOSE = 0.0
        SIGNAL_TIME = stockies[ticker]['Time'][0]
        OPTIMAL_ENTRY = 0.0
        OPTIMAL_EXIT = 0.0
        VOLUME_SPIKE = 0.0
        PRICE_SPIKE_TEMP = 0.0
        YESTERDAY_HIGH = 0.0

        OPTIMAL_ENTRY_TIME = 0.0
        OPTIMAL_EXIT_TIME = 0.0

        POSITION = 'Neutral'

        # Save stockies to see its structure
        # stockies[ticker].to_excel('./test/stockies_structure.xlsx', index=True, header=True)

        # test = f'./test/backtest.xlsx'
        # stockies[ticker].to_excel(test, index=False, header=True)

        #Iterate over rows to see which rows meet the close condition and the all clear to buy signal (pending final signal: price cross)
        #Unique to this strategy's backtest. Could be a part of inserting variables and signals before BACKTEST SECTION

        for index, row in stockies[ticker].iterrows():

            if row['Grab_Price_Signal'] == 'True':
                # print(f"Found signal: {row['Date']}")
                TEMP_SIGNAL_DAY = row['Date']
                TARGET_ENTRY_PRICE = row['VWAP']
                SIGNAL_TIME = row['Time']
                VOLUME_SPIKE = row['Volume']/row['10_Day_Avg_Vol']
                PRICE_SPIKE = (row['High']-row['Day_Open_Low'])/row['Day_Open_Low']
                YESTERDAY_HIGH = row['high_of_day']

            if (row['Close']<=TARGET_ENTRY_PRICE) & (row['Day_Close'] == True) & (row['Date'] == TEMP_SIGNAL_DAY):
                # print(f"Setting Close_Condition: Close={row['Close']}, TARGET={TARGET_ENTRY_PRICE}, Date={row['Date']}")
                stockies[ticker].at[index,'Close_Condition'] = 'True'
                OK_TO_BUY_DAY = next_business_day(row['Date'])
                SIGNALS += 1
                PREVIOUS_DAY_CLOSE = row['Close']
            
            if (OK_TO_BUY_DAY == row['Date']):
                # print(f"Setting Ok_To_Buy for date: {row['Date']}")
                stockies[ticker].at[index,'Ok_To_Buy'] = 'True' 
                stockies[ticker].at[index,'Previous_Day_Close'] = PREVIOUS_DAY_CLOSE
                stockies[ticker].at[index,'Signal Time'] = SIGNAL_TIME
                stockies[ticker].at[index,'Volume Spike'] = VOLUME_SPIKE
                stockies[ticker].at[index,'Price_Spike_From_Open'] = PRICE_SPIKE
                stockies[ticker].at[index,'Yesterday High'] = YESTERDAY_HIGH
                stockies[ticker].at[index,'Target_Entry_Price'] = TARGET_ENTRY_PRICE

        # test = f'./test/backtest.xlsx'
        # stockies[ticker].to_excel(test, index=False, header=True)
        
        #Consolidate tables to only days where we might buy and sell
        stonks = stockies[ticker][(stockies[ticker]['Ok_To_Buy'] == 'True')]
        # stonks.to_excel(f'./test/BACKTEST_STONKS_{ticker}_{input_indexer}.xlsx', index=True, header=True)

            
        #Check that pre-market high wasn't higher than yesterday's high bar (in backtest)
        #Use variable for yesterday's high that switches on signal to equal high price of signal
        #Compare to yesterday's high bar       
        #Check that pre-market high wasn't higher than yesterday's high bar (in backtest)
        #Use variable for yesterday's high that switches on signal to equal high price of signal
        #Compare to yesterday's high bar

        #If there are no signals - skip to next stock.
        if len(stockies[ticker][stockies[ticker]['Ok_To_Buy']== 'True']) == 0:
            continue      
            
        # After the loop
        # if stockies[ticker]['Ok_To_Buy'].any():
        #     print(f"Found Ok_To_Buy signals for dates:")
        #     print(stockies[ticker][stockies[ticker]['Ok_To_Buy'] == 'True'][['Date', 'Grab_Price_Signal', 'Close_Condition']])
    #########################################  BACKTEST IMPLEMENTATION AND SIMULATION OF BUY AND SELL SIGNALS  ##################################################
        
        POSITION = 'Neutral'
        
        #USING IN-HOUSE FUNCTION SIMULATE (ITERATING THROUGH DAYS, BUYING AND SELLING BASED ON SIGNALS)
        #Iterate over rows to fill in results table with buy and sell actions
        for index, row in stonks.iterrows():    
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
            buy_sell(signal,
                     row['Date'],
                     row['Ticker'],
                     row['Open'],
                     row['Close'],
                     row['Time'],
                     row['Volume'],
                     row['Previous_Day_Close'],
                     row['Volume Spike'],
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
            position_size = ACCOUNT_SIZE * strategy[bet_size_index]    
            buy_sell(signal,
                     row['Date'],
                     row['Ticker'],
                     row['Open'],
                     row['Close'],
                     row['Time'],
                     row['Volume'],
                     row['Previous_Day_Close'],
                     row['Volume Spike'],
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
    tick_list = tickers
    # Write each dataframe to a different worksheet.
    # results = pd.merge(results,tick_list[['Ticker','Market Capitalization','Sector','Shares Float']],on = 'Ticker', how = 'left')
    results.to_excel(f'./backtest_results/detailed_results/run_{run}_strategy_{input_indexer}.xlsx', index=False, header=True)
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
inputs.to_excel(f'./backtest_results/run_{run}_on_{current_date}.xlsx', index=True, header=True)
print(datetime.now() - start_clock)
