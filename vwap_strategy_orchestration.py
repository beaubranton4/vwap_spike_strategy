#!/usr/bin/env python
# coding: utf-8

from functions import *
from config import *
from functions.execute_strategy import ExecuteStrategy
from functions.manage_authentication import get_authenticated_client
import logging

def main():
    ############STEP 0: SETUP and Initialization####################
    
    # Get authenticated client with auto token management
    client = get_authenticated_client()
    
    # Rest of your code using the client
    account_balance = get_account_balance(client)
    print(f"Account balance: {account_balance}")
    cash_balance = get_cash_balance(client)
    print(f"Cash balance: {cash_balance}")
    print(datetime.now())
    ############STEP 1: RUN DAILY SCREENER (5pm PT)####################

    # May need to seperate screener and executor (will run at different times)
    screener_results = run_vwap_spike_screener(
        client=client,
        ticker_list=ticker_list,
        combinations=combinations,
        day_of_backtest=datetime.now() - timedelta(days=2),
        period_type=period_type,
        period=period,
        frequency_type=frequency_type,
        frequency=frequency,
        start_time=start_time,
        end_time=end_time,
        need_extended_hours_data=need_extended_hours_data,
        need_previous_close=need_previous_close,
        rolling_lookback=rolling_lookback,
        ALLOCATION=ALLOCATION,
        price_spike_thresh_index=price_spike_thresh_index,
        time_sig_thresh_index=time_sig_thresh_index,
        buy_time_threshold_index=buy_time_threshold_index,
        vol_spike_thresh_index=vol_spike_thresh_index,
        sell_time_threshold_index=sell_time_threshold_index,
        stop_index=stop_index,
        target_index=target_index
    )
    print(f"Found {len(screener_results)} potential trades")
    
    ###########STEP 1.5: READ IN DAILY SCREENER RESULTS####################
    # Allow for custom date selection
    # tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    # today = datetime.now().strftime('%Y-%m-%d')
    
    selected_date = '2024-11-21'  # Can be modified to any date in YYYY-MM-DD format
    
    
    # screener_results = pd.read_csv(f'screener/daily_screener_signals/{selected_date}.csv')
    # print(f"Found {len(screener_results)} potential trades after daily screener")

    ############STEP 2: RUN PREMARKET SCREENER (9:29am PT)####################
    # premarket_screener_results = run_premarket_screener(client, screener_results)
    # print(f"Found {len(premarket_screener_results)} potential trades after premarket screener")

    ############STEP 3: EXECUTE STRATEGY - STREAMER (9:30am PT)####################
    premarket_screener_results = pd.read_csv(f'screener/premarket_screener_signals/{selected_date}.csv')
    strategy = ExecuteStrategy(use_mock_data=True)
    strategy.execute_vwap_spike_strategy(premarket_screener_results)
    
    
if __name__ == "__main__":
    main()

