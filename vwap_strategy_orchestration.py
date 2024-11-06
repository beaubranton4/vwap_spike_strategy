#!/usr/bin/env python
# coding: utf-8

from functions import *
from config import *

def main():
    account_balance = get_account_balance()
    print(f"Account balance: {account_balance}")
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
    #     vol_spike_thresh_index=vol_spike_thresh_index,
    #     sell_time_threshold_index=sell_time_threshold_index,
    #     stop_index=stop_index,
    #     target_index=target_index
    # )
    
    # print(f"Found {len(screener_results)} potential trades")

if __name__ == "__main__":
    main()

