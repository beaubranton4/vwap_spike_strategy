#!/usr/bin/env python
# coding: utf-8

from functions import *
from config import *
from functions.execute_strategy import ExecuteStrategy

def main():
    account_balance = get_account_balance()
    print(f"Account balance: {account_balance}")

    # May need to seperate screener and executor (will run at different times)
    # screener_results = run_vwap_spike_screener(
    #     ticker_list=ticker_list,
    #     combinations=combinations,
    #     day_of_backtest=datetime.now(),
    #     period_type=period_type,
    #     period=period,
    #     frequency_type=frequency_type,
    #     frequency=frequency,
    #     start_time=start_time,
    #     end_time=end_time,
    #     need_extended_hours_data=need_extended_hours_data,
    #     need_previous_close=need_previous_close,
    #     rolling_lookback=rolling_lookback,
    #     ALLOCATION=ALLOCATION,
    #     price_spike_thresh_index=price_spike_thresh_index,
    #     time_sig_thresh_index=time_sig_thresh_index,
    #     buy_time_threshold_index=buy_time_threshold_index,
    #     vol_spike_thresh_index=vol_spike_thresh_index,
    #     sell_time_threshold_index=sell_time_threshold_index,
    #     stop_index=stop_index,
    #     target_index=target_index
    # )
    # print(f"Found {len(screener_results)} potential trades")

    #Test an already established screener file
    # tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    screener_results = pd.read_excel(f'../screener/daily_screener_signals/{today}.xlsx')
    # print(screener_results.head())
    
    # DOUBLE CHECK STRATEGY TO SEE IF WE CAN BUY PRE-MARKET
    strategy = ExecuteStrategy()
    strategy.execute_vwap_spike_strategy(screener_results)

    ##NEED TO FIX THE MARKETDATASTREAMER FROM EXECUTE STRATEGY FILE
    
    

if __name__ == "__main__":
    main()

