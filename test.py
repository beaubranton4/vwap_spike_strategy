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
    df = ticker_list
    df = print_borrow_info(df, client)

if __name__ == "__main__":
    main()