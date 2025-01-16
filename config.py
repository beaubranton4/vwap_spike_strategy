import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, time, date
import pandas as pd
import glob
import pandas_market_calendars as mcal
import schwabdev
import itertools
import pytz
######################################## LOADING SCHWAB API VARIABLES #########################################

load_dotenv()  # Load environment variables from .env file

appKey = os.getenv('appKey')
appSecret = os.getenv('appSecret')

######################################## DEFINING ALL VARIABLES FOR SCREENER #########################################


######################################## STRATEGY NOTE TO REMIND ON OUTPUT ########################################
strategy_note = '50M+Float'
run = strategy_note
day_of_backtest = datetime.now()

########################################  IMPORT LIST OF ALL TICKERS FOR BACKTEST/STRATEGY   #################################
ticker_list = pd.concat(map(pd.read_excel, glob.glob("data/by_float/*.xlsx")))

float_threshold = 50000000
ticker_list = ticker_list[ticker_list['Float'] > float_threshold]

####################################### SETTING CANDLE TIME FRAME FOR STRATEGY ########################################
# Define variables for stock time frame for strategy
period_type = 'day'  # Current value
period = 10          # Current value
frequency_type = 'minute'  # Current value
frequency = 30      # Current value
need_extended_hours_data = 'true'  # Current value
need_previous_close = 'true'  # Current value

######################################## TESTING COMBINATION OF INPUTS FOR STRATEGY  ########################################
ACCOUNT_SIZE = 1  # Using get_account_balance function to retrieve account balance
ALLOCATION = 0.1

BET_SIZE = [ALLOCATION]  # FIXED
STOP = [0.1]  # FIXED # Removed .05
TARGET = [0.1]  # FIXED

VOL_SPIKE_THRESHOLD = [5]  # Abnormally high volume that stands out on a chart
PRICE_SPIKE_THRESHOLD = [0.05]  # Must move the price x%
TIME_SIG_THRESHOLD = [time(hour=12, minute=30, second=0)]

#BUY AND SELL RESULTS BASED ON 5m Candles so we can add 5 minutes to these times to determine real times
BUY_TIME_THRESHOLD = [time(hour=9, minute=30, second=0)]
SELL_TIME_THRESHOLD = [time(hour=9, minute=40, second=0)]

####################################### CREATE VARIABLES FOR INPUT STRATEGY TO TEST ##########################
bet_size_index = 0
stop_index = 1
target_index = 2
vol_spike_thresh_index = 3
price_spike_thresh_index = 4
time_sig_thresh_index = 5
buy_time_threshold_index = 6
sell_time_threshold_index = 7

variables = [BET_SIZE,STOP,TARGET,VOL_SPIKE_THRESHOLD,PRICE_SPIKE_THRESHOLD,TIME_SIG_THRESHOLD,BUY_TIME_THRESHOLD, SELL_TIME_THRESHOLD]
combinations = list(itertools.product(*variables))   

######################################## STRATEGY OUTPUT TABLE ########################################
# FINAL OUTPUT TO EVALUATE DIFFERENT STRATEGY COMBINATIONS
inputs = pd.DataFrame(columns=['Account Size',
                               'Bet_Size',
                               'Stop',
                               'Target',
                               'Vol Spike Thresh',
                               'Price Spike Thresh',
                               'Signal Time Threshold',
                               'Buy Time Threshold',
                               'Sell_Time',
                               'Signals',
                               'Buys',
                               'Win %',
                               'Average Win',
                               'Strategy Note'])

########################################  TIME FRAME  ########################################
# Set date parameters and calculations regarding dates such as 10 day rolling average volume

en = datetime.now()  # SCREENER WILL RUN AS OF THIS DAY
st = en - timedelta(days=20)

start_time = str(int(st.timestamp()) * 1000)
end_time = str(int(en.timestamp()) * 1000)

today = date.today()

time_interval = 30
time_interval_string = str(time_interval) + 'm'
rolling_window_days = 10
tickers_per_day = 60 / time_interval * 6.5
rolling_lookback = rolling_window_days * tickers_per_day

# Find Next Business Day
# Import the New York Stock Exchange Calendar
 # Convert timestamps to ET datetime
eastern = pytz.timezone('US/Eastern')
start_of_backtest = datetime.fromtimestamp(int(start_time) / 1000).astimezone(eastern)
end_of_backtest = datetime.fromtimestamp(int(end_time) / 1000).astimezone(eastern)

# Get NYSE calendar schedule
nyse = mcal.get_calendar('NYSE')
open_close_schedule = pd.DataFrame(nyse.schedule(start_date=start_of_backtest, end_date=end_of_backtest))

open_close_schedule.index.names = ['Date']
open_close_schedule.reset_index(inplace=True)

# Convert market times to ET
open_close_schedule['market_open'] = open_close_schedule['market_open'].dt.tz_convert('US/Eastern')
open_close_schedule['market_close'] = open_close_schedule['market_close'].dt.tz_convert('US/Eastern')

# Extract date and time components
open_close_schedule['Date'] = open_close_schedule['market_open'].dt.date
open_close_schedule['market_open'] = open_close_schedule['market_open'].dt.time
open_close_schedule['market_close'] = (open_close_schedule['market_close'] - timedelta(minutes=30)).dt.time


# nyse = mcal.get_calendar('NYSE')
# open_close_schedule = pd.DataFrame(nyse.schedule(start_date=st, end_date=en))
# open_close_schedule.index.names = ['Date']
# open_close_schedule.reset_index(inplace=True)
# open_close_schedule['Date'] = open_close_schedule['Date'].dt.date
# open_close_schedule['market_open'] = open_close_schedule['market_open'] - timedelta(hours=4)
# open_close_schedule['market_close'] = open_close_schedule['market_close'] - timedelta(hours=4, minutes=time_interval)
# open_close_schedule['market_open'] = open_close_schedule['market_open'].dt.time
# open_close_schedule['market_close'] = open_close_schedule['market_close'].dt.time

nyse_days = nyse.valid_days(start_date=st, end_date=en)
valid_trading_days = pd.Series(nyse_days).dt.date

en_extended = en + timedelta(days=10)
schedule = pd.DataFrame(nyse.schedule(start_date=st, end_date=en_extended))
# Remove January 9, 2025 from schedule
schedule = schedule[schedule.index != pd.Timestamp('2025-01-09')]

# Count unique trading days between st and en inclusive
days = len(schedule[(schedule.index >= pd.Timestamp(st)) & (schedule.index <= pd.Timestamp(en))].index)

