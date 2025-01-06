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

# import symbol
logger = logging.getLogger('main')

# def print_borrow_info(df: pd.DataFrame, client) -> pd.DataFrame:
#     """Print borrow info for all tickers and add data to dataframe"""
#     print("\nBorrow Information:")
#     print("-" * 50)
    
#     # Initialize new columns
#     df['isHardToBorrow'] = None
#     df['isShortable'] = None 
#     df['htbRate'] = None
    
#     for idx, symbol in enumerate(df['Ticker']):
#         try:
#             response = client.quote(symbol, 'all')
#             if response.status_code == 200:
#                 ref_data = response.json()[symbol]['reference']
                
#                 # Print info
#                 print(f"{symbol:<6} | HTB: {ref_data['isHardToBorrow']}, "
#                       f"Shortable: {ref_data['isShortable']}, "
#                       f"HTB Rate: {ref_data['htbRate']}%")
                
#                 # Add to dataframe
#                 df.loc[idx, 'isHardToBorrow'] = ref_data['isHardToBorrow']
#                 df.loc[idx, 'isShortable'] = ref_data['isShortable']
#                 df.loc[idx, 'htbRate'] = ref_data['htbRate']
                
#             time_lib.sleep(0.1)  # Rate limiting
#         except Exception as e:
#             print(f"{symbol:<6} | Error: {str(e)}")
    
#     # Save to Excel
#     df.to_excel('data/tickers_w_htb_data.xlsx', index=False)
#     print(f"\nData saved to data/tickers_w_htb_data.xlsx")
    
#     return df


#Takes in json returned from client.account_orders_all() and converts to a dataframe

# def parse_orders(orders):
#     parsed_orders = []
    
#     for order in orders:
#         # Get the symbol from the first leg
#         symbol = order['orderLegCollection'][0]['instrument']['symbol']
        
#         # Parse timestamps
#         entered_time = datetime.strptime(order['enteredTime'], '%Y-%m-%dT%H:%M:%S%z')
#         close_time = datetime.strptime(order.get('closeTime', order['enteredTime']), '%Y-%m-%dT%H:%M:%S%z')
        
#         # Get execution price if available
#         exec_price = None
#         if 'orderActivityCollection' in order:
#             for activity in order['orderActivityCollection']:
#                 if activity['activityType'] == 'EXECUTION' and activity['executionType'] == 'FILL':
#                     exec_price = activity['executionLegs'][0]['price']
#                     break
        
#         parsed_order = {
#             'Symbol': symbol,
#             'OrderId': order['orderId'],
#             'Type': order['orderType'],
#             'Status': order['status'],
#             'Quantity': order['quantity'],
#             'Price': order.get('price', exec_price),
#             'Filled': order['filledQuantity'],
#             'Entered': entered_time.strftime('%Y-%m-%d %H:%M:%S'),
#             'Closed': close_time.strftime('%Y-%m-%d %H:%M:%S'),
#             'Duration': order['duration'],
#             'Instruction': order['orderLegCollection'][0]['instruction']
#         }
#         parsed_orders.append(parsed_order)
        
#     # Create DataFrame
#     df = pd.DataFrame(parsed_orders)
    
#     # Reorder columns
#     cols = ['Symbol', 'OrderId', 'Type', 'Status', 'Instruction', 'Quantity', 
#             'Filled', 'Price', 'Duration', 'Entered', 'Closed']
#     df = df[cols]
#     # Filter for only WORKING orders
#     df = df[df['Status'] == 'WORKING']
    
#     return df

def main():

    
    client = get_authenticated_client()
    linked_accounts_response = client.account_linked()
    account_hash = linked_accounts_response.json()[0].get('hashValue')
    
    # Set time range to last 24 hours
    to_time = datetime.now()
    from_time = to_time - timedelta(days=10)
    
    # Close all open SELL_SHORT orders
    close_all_open_orders(client, account_hash, from_time, to_time, 'SELL_SHORT')
    # get_todays_trades(client)
    # account_balance = get_account_balance(client)
    # get_todays_trades(client)
    # last_market_day = last_trading_day(datetime.now(pytz.timezone('US/Eastern')))
    # print(last_market_day)
    # stock_data = get_price_history_with_schwabdev(
    #                 client=client,
    #                 ticker='AAPL',
    #                 period_type=period_type,
    #                 period=period,
    #                 frequency_type=frequency_type,
    #                 frequency=frequency,
    #                 start_time=start_time,
    #                 end_time=end_time,
    #                 need_extended_hours_data=need_extended_hours_data,
    #                 need_previous_close=need_previous_close,
    #                 max_retries=3,
    #                 retry_delay=1
    #             )
    # stahks = pd.DataFrame(stock_data['candles'])
    # stahks['datetime'] = pd.to_datetime(stahks['datetime'], unit='ms').dt.tz_localize('UTC').dt.tz_convert('US/Eastern').dt.tz_localize(None)
    # stahks.to_csv('tester.csv', index=False)
    
    # Initialize client and get account hash
    # linked_accounts_response = client.account_linked()
    # account_hash = linked_accounts_response.json()[0].get('hashValue')
    
    # # Set time range to last 24 hours
    # to_time = datetime.now()
    # from_time = to_time - timedelta(days=1)
    
    # # Close all open SELL_SHORT orders
    # close_all_open_orders(client, account_hash, from_time, to_time, 'SELL_SHORT')
    
    # if linked_accounts_response.status_code != 200:
    #     logger.error(f"Failed to place order for {symbol}")
        
    # account_hash = linked_accounts_response.json()[0].get('hashValue')


    # print(account_hash)
    # # Retrieve order details for a specific order ID
    # order_id = 1002403722091
    # # account_hash = 'your_account_hash_here'  # Replace with the actual account hash
    # order_response = client.order_details(account_hash, order_id)
    
    # if order_response.status_code == 200:
    #     order_details = order_response.json()
    #     df = parse_orders(order_details)
    # #         # Export DataFrame to CSV
    # #         output_file_path = 'orders.csv'
    # #         df.to_csv(output_file_path, index=False)
    # #         logger.info(f"Exported orders to {output_file_path}")
    #     print(df)
    #     # print("Order Details:", order_details)
    # else:
    #     logger.error(f"Error retrieving order details: {order_response.status_code}")


    # Get orders from last 24 hours
    # from_time = datetime.now() - timedelta(days=3)
    # to_time = datetime.now()

    # close_all_open_orders(client, account_hash, from_time, to_time, 'SELL_SHORT')
    
    # try:
    #     # Query orders
    #     response = client.account_orders_all(fromEnteredTime=from_time, toEnteredTime=to_time)
        
    #     if response.status_code == 200:
    #         orders = response.json()
    #         df = parse_orders(orders)
    #         # Export DataFrame to CSV
    #         output_file_path = 'orders.csv'
    #         df.to_csv(output_file_path, index=False)
    #         logger.info(f"Exported orders to {output_file_path}")
    #         print(df)
    #     else:
    #         logger.error(f"Error getting orders: {response.status_code}")
            
    # except Exception as e:
    #     logger.error(f"Error querying orders: {str(e)}")


    # print(f"Account balance: {account_balance}")
    # df = pd.read_csv(f'screener/premarket_screener_signals/2024-12-05.csv')
    # close_matched_positions(client, df)


    # end_backtest_date = datetime.now() 
    # start_backtest_date = end_backtest_date - timedelta(days=365)
    # start_backtest_time = str(int(start_backtest_date.timestamp())*1000)
    # end_backtest_time = str(int(end_backtest_date.timestamp())*1000)
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
    # run_vwap_spike_screener_backtest(client, ticker_list, combinations, 
    #                         period_type, period, frequency_type, frequency,
    #                         start_backtest_time, end_backtest_time, need_extended_hours_data,
    #                         need_previous_close, rolling_lookback,
    #                         price_spike_thresh_index, time_sig_thresh_index, buy_time_threshold_index,
    #                         vol_spike_thresh_index, sell_time_threshold_index,
    #                         stop_index, target_index)
    
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