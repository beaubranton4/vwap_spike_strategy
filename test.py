# Standard library imports
import os
import sys
import json
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

# Third-party imports
import pytz
import pandas as pd
import pandas_market_calendars as mcal
import requests
import psutil
import schedule as scheduler
from schwabdev import Client

# Local imports
from config import *
from functions import *
from functions.manage_authentication import get_authenticated_client
from functions.schwab_functions import get_price_history_with_schwabdev
from functions.backtest_functions import run_vwap_spike_screener_backtest

# Logging setup
import logging
logger = logging.getLogger('main')

def print_borrow_info(df: pd.DataFrame, client) -> pd.DataFrame:
    """Print borrow info for all tickers and add data to dataframe"""
    print("\nBorrow Information:")
    print("-" * 50)
    
    # Initialize new columns
    df['isHardToBorrow'] = None
    df['isShortable'] = None 
    df['htbRate'] = None
    
    for idx, symbol in enumerate(df['Ticker']):
        try:
            response = client.quote(symbol, 'all')
            if response.status_code == 200:
                ref_data = response.json()[symbol]['reference']
                
                # Print info
                print(f"{symbol:<6} | HTB: {ref_data['isHardToBorrow']}, "
                      f"Shortable: {ref_data['isShortable']}, "
                      f"HTB Rate: {ref_data['htbRate']}%")
                
                # Add to dataframe
                df.loc[idx, 'isHardToBorrow'] = ref_data['isHardToBorrow']
                df.loc[idx, 'isShortable'] = ref_data['isShortable']
                df.loc[idx, 'htbRate'] = ref_data['htbRate']
                
            time_lib.sleep(0.1)  # Rate limiting
        except Exception as e:
            print(f"{symbol:<6} | Error: {str(e)}")
    
    # Save to Excel
    df.to_excel('data/tickers_w_htb_data.xlsx', index=False)
    print(f"\nData saved to data/tickers_w_htb_data.xlsx")
    
    return df




def main():

    
    client = get_authenticated_client()
    # get_todays_trades(client)
    account_balance = get_account_balance(client)
    print(f"Account balance: {account_balance}")


    end_backtest_date = datetime.now() - timedelta(days=1)
    start_backtest_date = end_backtest_date - timedelta(days=30)
    start_backtest_time = str(int(start_backtest_date.timestamp())*1000)
    end_backtest_time = str(int(end_backtest_date.timestamp())*1000)
    # print(combinations[sell_time_threshold_index])
    # print("Backtest Parameters:")
    # print("-" * 50)
    # print(f"Start Backtest Time: {start_backtest_time}")
    # print(f"End Backtest Time: {end_backtest_time}")
    # print(f"Period Type: {period_type}")
    # print(f"Period: {period}")
    # print(f"Frequency Type: {frequency_type}")
    # print(f"Frequency: {frequency}")
    # print(f"Need Extended Hours Data: {need_extended_hours_data}")
    # print(f"Need Previous Close: {need_previous_close}")
    # print(f"Rolling Lookback: {rolling_lookback}")
    # print(f"Price Spike Threshold Index: {price_spike_thresh_index}")
    # print(f"Time Signal Threshold Index: {time_sig_thresh_index}")
    # print(f"Buy Time Threshold Index: {buy_time_threshold_index}")
    # print(f"Volume Spike Threshold Index: {vol_spike_thresh_index}")
    # print(f"Sell Time Threshold Index: {sell_time_threshold_index}")
    # print(f"Stop Index: {stop_index}")
    # print(f"Target Index: {target_index}")
    run_vwap_spike_screener_backtest(client, ticker_list, combinations, 
                            period_type, period, frequency_type, frequency,
                            start_backtest_time, end_backtest_time, need_extended_hours_data,
                            need_previous_close, rolling_lookback,
                            price_spike_thresh_index, time_sig_thresh_index, buy_time_threshold_index,
                            vol_spike_thresh_index, sell_time_threshold_index,
                            stop_index, target_index)
    
    # print(len(schedule))
    # next_biz_date = next_business_day(datetime.now(pytz.timezone('US/Eastern')) - timedelta(days=1))
    # print(next_biz_date)
    
    # print(is_market_date(schedule, datetime.now(pytz.timezone('US/Eastern')) - timedelta(days=4)))
    # Initialize client
    # client = get_authenticated_client()
    # df = pd.read_csv(f'screener/daily_screener_signals/2024-12-02.csv')
    # new_df = calculate_shares(client, df, ALLOCATION)
    # new_df.to_csv('test_add.csv', index=False)
    # print(new_df)

    # check_position_match(client, 'OPEN', 618, False)
    # date = last_trading_day(datetime.now(pytz.timezone('US/Eastern'))+timedelta(days=2))
    # date is already a date object from last_trading_day(), no need to call .date()
    # print(date)
    # selected_date = '2024-11-27'
    # df = pd.read_csv(f'screener/premarket_screener_signals/{selected_date}.csv')
    # close_matched_positions(client, df)
    # # Order parameters
    # symbol = 'CRL'
    # quantity = 2
    # limit_price = 195.90
    # stop_price = 199.00
    # target_price = 100.00

    # # Set cancel time as string in HH:MM format
    # # cancel_time_et = '00:05'  # Will cancel at 10:04 PM ET

    # try:
    #     order_status = place_bracket_order(
    #         client=client, 
    #         symbol=symbol, 
    #         quantity=quantity, 
    #         instruction='SELL_SHORT', 
    #         order_type='LIMIT', 
    #         price=limit_price, 
    #         stop_price=stop_price, 
    #         target_price=target_price
    #     )
    #     logger.info(f"Order status: {order_status}")
    # except Exception as e:
    #     logger.error(f"❌ Error during order placement: {str(e)}")
    #     logger.error(f"Traceback: {traceback.format_exc()}")

    # print(f"Order status: {order_status}")

if __name__ == "__main__":
    main()