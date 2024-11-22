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
                         stop_price: float = None, target_price: float = None,
                         exit_time: str = None) -> Dict:
    """
    Place an order with bracket stop and target
    
    Args:
        client: Schwab API client
        symbol: Stock symbol
        quantity: Number of shares
        instruction: 'SELL_SHORT' or 'BUY_TO_COVER' or 'BUY' or 'SELL'
        order_type: 'MARKET' or 'LIMIT' (default: 'LIMIT')
        price: Entry price for limit orders
        stop_price: Stop loss price
        target_price: Take profit price
        exit_time: Time to exit position (format: "HH:MM" in 24hr format)
    """
    try:
        # Get account hash
        linked_accounts_response = client.account_linked()
        if linked_accounts_response.status_code != 200:
            logger.error(f"Failed to place order for {symbol}")
            return 'ERROR_WITH_API_CALL'
            
        account_hash = linked_accounts_response.json()[0].get('hashValue')
        
        # Determine exit instruction based on entry
        if instruction == 'SELL_SHORT':
            exit_instruction = 'BUY_TO_COVER'
        elif instruction == 'BUY':
            exit_instruction = 'SELL'
        else:
            logger.error(f"Invalid instruction: {instruction}")
            return 'UNKNOWN_EXIT_INSTRUCTION'
        
        # If exit_time provided, convert to full datetime
        if exit_time:
            now = datetime.now(pytz.timezone('America/New_York'))
            hour, minute = map(int, exit_time.split(':'))
            exit_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            
            # If the time has already passed today, set for tomorrow
            if exit_datetime <= now:
                exit_datetime += timedelta(days=1)
        logger.info(f"Exit time: {exit_datetime}")

        # Create the main order with bracket strategy
        order = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "TRIGGER",
            "releaseTime": exit_datetime.isoformat(),
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
                    "orderStrategyType": "OCO",  # One-Cancels-Other order for all three exits
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
                        # ,
                        # {
                        #     # Timed Exit Order - Not Working (maybe not possible?)
                        #     "orderType": "MARKET",
                        #     "session": "NORMAL",
                        #     "duration": "DAY",
                        #     "orderStrategyType": "SINGLE",
                        #     "releaseTime": exit_datetime.isoformat(),
                        #     "orderLegCollection": [
                        #         {
                        #             "instruction": exit_instruction,
                        #             "quantity": int(quantity),
                        #             "instrument": {
                        #                 "symbol": symbol.upper(),
                        #                 "assetType": "EQUITY"
                        #             }
                        #         }
                        #     ]
                        # }
                    ]
                }
            ]
        }
        
        # Add price for limit orders
        if order_type == 'LIMIT':
            order["price"] = str(price)
        
        # Place the order
        order_response = client.order_place(account_hash, order)
        
        # Extract order ID and check status
        order_url = order_response.headers.get('Location', '')
        order_id = order_url.split('/')[-1]
        logger.info(f"Order ID: {order_id}")
        order_status = check_order_status(client, account_hash, order_id)
        logger.info(f"Order status: {order_status}")    
        return order_status
            
    except Exception as e:
        logger.error(f"❌ Error placing order for {symbol}: {str(e)}")
        return {'status': 'ERROR'}


def main():
    # Initialize client
    client = get_authenticated_client()
    
    # Order parameters
    symbol = 'LCID'
    quantity = 1
    limit_price = 2.09
    stop_price = 2.60
    target_price = 1.50
    exit_time = '15:30'

    try:
        order_status = place_bracket_order(client, symbol, quantity, instruction='SELL_SHORT', order_type='LIMIT', price=limit_price, stop_price=stop_price, target_price=target_price, exit_time=exit_time)
        logger.info(f"Order status: {order_status}")
    except Exception as e:
        logger.error(f"❌ Error during order placement: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    main()