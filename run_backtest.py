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


def main():

    
    client = get_authenticated_client()
    # get_todays_trades(client)
    account_balance = get_account_balance(client)
    print(account_balance)
    eastern_tz = pytz.timezone('US/Eastern')
    end_backtest_date = datetime.now(eastern_tz)
    start_backtest_date = end_backtest_date - timedelta(days=365)
    start_backtest_time = str(int(start_backtest_date.timestamp())*1000)
    end_backtest_time = str(int(end_backtest_date.timestamp())*1000)

    # PERCENT_ALLOCATION = [0.1]  # FIXED
    # STOP_LOSS_PERCENT = [0.1, .05, .15]  # FIXED # Removed .05
    # PROFIT_TARGET_PERCENT = [0.05, .1, .15]  # FIXED

    # VOLUME_SPIKE_SIGNAL = [5, 10]  # Abnormally high volume that stands out on a chart
    # PRICE_SPIKE_SIGNAL = [0.05, .1]  # Must move the price x%
    # SPIKE_TIME_LIMIT = [time(hour=12, minute=30, second=0)]
    # ENTRY_TIME_LIMIT = [time(hour=10, minute=30, second=0), time(hour =11, minute=30, second = 0)]
    # EXIT_TIME_LIMIT = [time(hour=15, minute=30, second=0)]

    PERCENT_ALLOCATION = [0.1]  # FIXED
    STOP_LOSS_PERCENT = [0.1]  # FIXED # Removed .05
    PROFIT_TARGET_PERCENT = [0.05]  # FIXED

    VOLUME_SPIKE_SIGNAL = [5]  # Abnormally high volume that stands out on a chart
    PRICE_SPIKE_SIGNAL = [0.05]  # Must move the price x%
    SPIKE_TIME_LIMIT = [time(hour=12, minute=30, second=0)]
    ENTRY_TIME_LIMIT = [time(hour=10, minute=30, second=0)]
    EXIT_TIME_LIMIT = [time(hour=15, minute=30, second=0)]

    ####################################### CREATE VARIABLES FOR INPUT STRATEGY TO TEST ##########################
    bet_size_index = 0
    stop_index = 1
    target_index = 2
    vol_spike_thresh_index = 3
    price_spike_thresh_index = 4
    time_sig_thresh_index = 5
    buy_time_threshold_index = 6
    sell_time_threshold_index = 7

    variables = [PERCENT_ALLOCATION, STOP_LOSS_PERCENT, PROFIT_TARGET_PERCENT, VOLUME_SPIKE_SIGNAL, PRICE_SPIKE_SIGNAL, SPIKE_TIME_LIMIT, ENTRY_TIME_LIMIT, EXIT_TIME_LIMIT]
    strategy_variations = list(itertools.product(*variables))   

    strategy_note_input = 'final'
    
    run_vwap_spike_screener_backtest(client, ticker_list, strategy_variations, 
                            period_type, period, frequency_type, frequency,
                            start_backtest_time, end_backtest_time, need_extended_hours_data,
                            need_previous_close, rolling_lookback,
                            price_spike_thresh_index, time_sig_thresh_index, buy_time_threshold_index,
                            vol_spike_thresh_index, sell_time_threshold_index,
                            stop_index, target_index, strategy_note_input)
    

if __name__ == "__main__":
    main()