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
import logging
import traceback
import json
import requests
from schwabdev import Client
from typing import Dict

logger = logging.getLogger(__name__)

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

def place_bracket_order(client: Client, symbol: str, quantity: int, instruction: str, 
                       order_type: str = 'LIMIT', price: float = None, 
                       stop_price: float = None, target_price: float = None) -> Dict:
    """
    Place an order with bracket stop and target orders
    
    Args:
        client: Authenticated Schwab client
        symbol: Stock symbol
        quantity: Number of shares
        instruction: Order instruction (e.g., 'SELL_SHORT', 'BUY')
        order_type: Type of order ('LIMIT' or 'MARKET')
        price: Limit price for the entry order
        stop_price: Stop loss price
        target_price: Target profit price
    
    Returns:
        str
    """
    try:
        logger.info(f"Starting bracket order placement for {symbol}")
        logger.info(f"Parameters: quantity={quantity}, instruction={instruction}, "
                   f"order_type={order_type}, price={price}, stop={stop_price}, "
                   f"target={target_price}")
        
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to get account hash. Status: {linked_accounts_response.status_code}")
            logger.error(f"Response: {linked_accounts_response.text}")
            return 'ERROR_WITH_API_CALL'
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        logger.info(f"Got account hash: {account_hash[:8]}...")
        
        # Determine exit instruction
        if instruction == 'SELL_SHORT':
            exit_instruction = 'BUY_TO_COVER'
        elif instruction == 'BUY':
            exit_instruction = 'SELL'
        else:
            logger.error(f"Invalid instruction: {instruction}")
            return 'UNKNOWN_EXIT_INSTRUCTION'

        # Create the order
        order = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "specialInstruction": "ALL_OR_NONE",
            "orderStrategyType": "TRIGGER",
            "orderLegCollection": [
                {
                    "instruction": instruction,
                    "quantity": int(quantity),
                    "instrument": {
                        "symbol": symbol.upper(),
                        "assetType": "EQUITY"
                    }
                }
            ],
            "childOrderStrategies": [
                {
                    "orderStrategyType": "OCO",  # One-Cancels-Other for stop and target
                    "childOrderStrategies": [
                        {
                            # Stop Loss Order
                            "orderType": "STOP",
                            "session": "NORMAL",
                            "duration": "DAY",
                            "stopPrice": stop_price,
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [
                                {
                                    "instruction": exit_instruction,
                                    "quantity": int(quantity),
                                    "instrument": {
                                        "symbol": symbol.upper(),
                                        "assetType": "EQUITY"
                                    }
                                }
                            ]
                        },
                        {
                            # Take Profit Order
                            "orderType": "LIMIT",
                            "session": "NORMAL",
                            "duration": "DAY",
                            "price": target_price,
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [
                                {
                                    "instruction": exit_instruction,
                                    "quantity": int(quantity),
                                    "instrument": {
                                        "symbol": symbol.upper(),
                                        "assetType": "EQUITY"
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        
        # Add price for limit orders
        if order_type == 'LIMIT':
            order["price"] = str(price)
            logger.info(f"Added limit price: {price}")
        
        logger.info("Placing order with structure:")
        logger.info(json.dumps(order, indent=2))
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        logger.info(f"Order placement response status: {order_response.status_code}")
        
        # Log the full response for debugging
        try:
            response_json = order_response.json()
            logger.error(f"Full API Response: {json.dumps(response_json, indent=2)}")
        except:
            logger.error(f"Raw Response Text: {order_response.text}")
        
        if order_response.status_code != 201:  # 201 is success for order creation
            logger.error(f"Order placement failed. Response: {order_response.text}")
            return 'ERROR_WITH_API_CALL'
        
        # Extract order ID and check status
        order_url = order_response.headers.get('Location', '')
        order_id = order_url.split('/')[-1]
        logger.info(f"Order ID: {order_id}")
        
        order_status = check_order_status(client, account_hash, order_id)
        logger.info(f"Initial order status: {order_status}")    
        return order_status
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return 'ERROR_WITH_API_CALL'

def is_market_date(schedule: pd.DataFrame, check_date: datetime = None) -> bool:
    """
    Check if a given date is in the market schedule
    
    Args:
        schedule: DataFrame with market schedule
        check_date: datetime object in ET to check (defaults to current ET time)
        
    Returns:
        bool: True if date is in schedule, False otherwise
    """
    try:
        # If no date provided, use current ET time
        if check_date is None:
            et_tz = pytz.timezone('US/Eastern')
            check_date = datetime.now(et_tz)
            
        # Convert check_date to date only for comparison
        check_date = check_date.date()
        
        # Convert schedule index to date for comparison
        schedule_dates = schedule.index.date
        
        # Check if date exists in schedule
        is_trading_day = check_date in schedule_dates
        
        logger.info(f"Date check for {check_date}: {'Trading day' if is_trading_day else 'Non-trading day'}")
        return is_trading_day
        
    except Exception as e:
        logger.error(f"Error checking market date: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def main():
    print(len(schedule))
    print(is_market_date(schedule, datetime.now(pytz.timezone('US/Eastern')) - timedelta(days=4)))
    # Initialize client
    # client = get_authenticated_client()
    # check_position_match(client, 'OPEN', 618, False)
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