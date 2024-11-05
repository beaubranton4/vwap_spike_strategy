import numpy as np
from datetime import timedelta
import pandas as pd

############################################## ALL FUNCTIONS ########################################################

def next_business_day(today):
    next_day = today + timedelta(days=1)
    while next_day.weekday() in [5,6] or next_day.weekday() not in valid_trading_days:
        next_day += timedelta(days=1)
    return next_day

######################################## GET BUY/SELL SIGNAL FUNCTION ##################################################


#MUST MAKE SURE THAT THE SIGNALS RETURNED MATCH UP WITH THE BUY AND SELL FUNCTION COMMANDS
#Generates the type of buy or sell signals used in the buying and selling functions by taking in a row of stock data
def buy_sell_signal(signal,
                    ok_to_buy,
                    time,
                    high_price,
                    low_price,
                    after_hours,
                    day_close,
                    date,
                    stop,
                    target,
                    sell_time_thresh,
                    buy_time_thresh,
                    yesterday_high,
                    premarket_high,
                    target_entry_price):
    
    #SHORT STRATEGIES
    if(signal == 'Short'): 
        
        #BUY (check that all signals triggered, positioning is neutral, not after hours and we didn't buy it today yet)
        if ((ok_to_buy == 'True') 
            & (time <= buy_time_thresh) 
            & (buy_time_thresh <= sell_time_thresh)
            & (high_price>=target_entry_price) 
            & (POSITION == 'Neutral') 
            & (after_hours==False) 
            & (BOUGHT_TODAY != date) 
            & (yesterday_high >= premarket_high)):
            #IF 
            #print('short',date)
            return 'Short (Target Price Cross)'
        #SELL (check that the position)
        elif (ENTRY_PRICE+(ENTRY_PRICE*stop) <= high_price) & ((POSITION == 'Short') | (POSITION == 'Long')): 
            #print('sell',date)
            return 'Sell (Stop Loss)'
        elif (ENTRY_PRICE-(ENTRY_PRICE*target) >= low_price) & ((POSITION == 'Short') | (POSITION == 'Long')):
            #print('sell',date)
            return 'Sell (Target Hit)'
        elif (((sell_time_thresh == time) | (day_close == True)) & (POSITION == 'Short') | (POSITION == 'Long')): 
            #print('sell',date)
            return 'Sell (At Time Threshold)'
        else:
            return 'none'
    if(signal == 'Long'):
        return 'none' #input long strategy signal conditions
    else:
        return 'none'
    
####################################### CALCULATE TRADE STATS ########################################################

#Returns details for results table based on the type of sell signal (profit,exit,win/loss,type of sale)
#might need entry_price passed in
def calculate_sell_results(sell_signal,row_close,position_size,stop,target):
    
    if (signal == 'Sell (Stop Loss)'):
        profit = (position_size - (position_size*(1+stop)))
        exit = ENTRY_PRICE +(ENTRY_PRICE*stop)
        win_loss = 'Loss'
        sell_type = 'Sell (Stop Loss)'
        return [profit,exit,win_loss,sell_type]

    if (signal == 'Sell (Target Hit)'):
        profit = ((1+target)*(position_size))-(position_size)
        exit = ENTRY_PRICE - (ENTRY_PRICE*target)
        win_loss = 'Win'
        sell_type = 'Sell (Target Hit)'
        return [profit,exit,win_loss,sell_type]

    if (signal == 'Sell (At Time Threshold)'):
        profit = (((ENTRY_PRICE-row_close)/ENTRY_PRICE)*position_size)
        exit = row_close
        win_loss = np.where(((ENTRY_PRICE-row['Close'])/ENTRY_PRICE)>0,'Win','Loss')
        sell_type = 'Sell (At Time Threshold)'
        return [profit,exit,win_loss,sell_type]

    
######################################### BUY AND SELL FUNCTIONS ########################################################
#Function that ultimately buys and sells stock based on signals output by the buy_sell_signal function
def buy_sell(signal,
             date,
             ticker,
             open_price,
             close_price,
             time,
             volume,
             previous_day_close,
             volume_spike,
             price_spike,
             target_entry_price,
             position_size,
             stop,
             target):
   
    global ENTRY_PRICE
    global POSITION
    global ENTRY_TIME
    global ACCOUNT_SIZE
    global BUYS
    global RESULT_INDEXER
    global BOUGHT_TODAY

    #BUY - Currently the only buy signal, but could create function for the different buy types
    if (signal == 'Short (Target Price Cross)'):

        POSITION = 'Short'
        ENTRY_TIME = time
        ENTRY_PRICE = np.where(open_price>target_entry_price,open_price,target_entry_price)
        BUYS += 1

    #SELL - Will calculate sell stats based on the signal using the calculate_sell_results function 
    elif ((signal == 'Sell (Target Hit)')
         |(signal == 'Sell (Stop Loss)')
         |(signal == 'Sell (At Time Threshold)')):
        POSITION = 'Neutral'
        sell_outputs = calculate_sell_results(signal,close_price,position_size,stop,target)
        profit = sell_outputs[0]
        exit = sell_outputs[1]
        win_loss = sell_outputs[2]
        sell_type = sell_outputs[3]
        results.at[RESULT_INDEXER,'Profit'] = profit
        results.at[RESULT_INDEXER,'Profit %'] = profit/position_size
        results.at[RESULT_INDEXER,'Bet Size'] = position_size
        ACCOUNT_SIZE += profit
        results.at[RESULT_INDEXER,'Date'] = date
        results.at[RESULT_INDEXER,'Ticker'] = ticker
        results.at[RESULT_INDEXER,'Account Size'] = ACCOUNT_SIZE
        results.at[RESULT_INDEXER,'Win/Loss'] = win_loss
        results.at[RESULT_INDEXER,'Target Entry'] = float(target_entry_price)
        results.at[RESULT_INDEXER,'Entry'] = ENTRY_PRICE  
        results.at[RESULT_INDEXER,'Exit'] = exit    
        results.at[RESULT_INDEXER,'Entry Time'] = ENTRY_TIME
        results.at[RESULT_INDEXER,'Exit Time'] = time
        results.at[RESULT_INDEXER,'Volume'] = volume
        results.at[RESULT_INDEXER,'Type'] = sell_type
        results.at[RESULT_INDEXER,'Volume Spike'] = volume_spike
        results.at[RESULT_INDEXER,'Price Spike'] = price_spike
        results.at[RESULT_INDEXER,'Previous Day Close'] = previous_day_close
        #results.at[RESULT_INDEXER,'Premarket Volume'] = 
        #results.at[RESULT_INDEXER,'Premarket Change'] = 
        BOUGHT_TODAY = date
        RESULT_INDEXER += 1