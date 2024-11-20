import schedule as scheduler  # Changed from: import schedule
import time as time_lib  # Rename time module to avoid conflict
from datetime import datetime, timedelta
import pytz
import logging
from pathlib import Path
import pandas as pd
import pandas_market_calendars as mcal
from functions import *  # Import your existing functions
from config import *
import threading  # Add this import
import os
import subprocess
import psutil
import sys

# Setup logging
def setup_logging():
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Create log filename with timestamp
    log_file = log_dir / f'trading_bot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    # Create a formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Add our handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Capture stdout and stderr
    class StreamToLogger:
        def __init__(self, logger, level):
            self.logger = logger
            self.level = level
            self.linebuf = ''

        def write(self, buf):
            for line in buf.rstrip().splitlines():
                if line:  # Only log non-empty lines
                    self.logger.log(self.level, line.rstrip())
        
        def flush(self):
            pass

    # Replace stdout and stderr with logging
    sys.stdout = StreamToLogger(root_logger, logging.INFO)
    sys.stderr = StreamToLogger(root_logger, logging.ERROR)
    
    # Test the logging
    root_logger.info("Logging system initialized")
    
    return root_logger

logger = setup_logging()

# Create a lock instance
job_lock = threading.Lock()

def is_market_open_today():
    """Check if market is open today"""
    nyse = mcal.get_calendar('NYSE')
    today = datetime.now(pytz.timezone('US/Eastern')).date()
    schedule = nyse.schedule(start_date=today, end_date=today)
    return not schedule.empty

def run_daily_screener():
    """Run at 8 PM ET after market close"""
    try:
        if not is_market_open_today():
            logger.info("Market was closed today. Skipping daily screener.")
            return

        client = get_authenticated_client()  # Your existing function    
        logger.info("Starting daily screener...")
        results = run_vwap_spike_screener(
            client=client,
            ticker_list=ticker_list,
            combinations=combinations,
            day_of_backtest=datetime.now(),
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
        print(f"Found {len(results)} potential trades")
        
        # Save results
        save_dir = Path('screener/daily_screener_signals')
        save_dir.mkdir(parents=True, exist_ok=True)
        
        date_to_trade = next_business_day(datetime.now())
        results.to_csv(f'{save_dir}/{date_to_trade}.csv', index=False)
        
        logger.info(f"Daily screener completed. Found {len(results)} signals.")
        
    except Exception as e:
        logger.error(f"Daily screener failed: {str(e)}", exc_info=True)

def schedule_premarket_screener():
    """Run 1 minute before market open"""
    try:
        if not is_market_open_today():
            logger.info("Market closed today. Skipping pre-market screener.")
            return
            
        logger.info("Starting pre-market screener...")
        
        # Get yesterday's results
        save_dir = Path('screener/daily_screener_signals')
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
        
        # Load screener results
        screener_file = f'{save_dir}/{today}.csv'
        if not Path(screener_file).exists():
            logger.error(f"No screener results found for {today}")
            return
            
        screener_results = pd.read_csv(screener_file)
        
        # Run pre-market checks
        client = get_authenticated_client()  # Your existing function
        filtered_results = run_premarket_screener(client, screener_results)
        
        # Save filtered results
        premarket_save_dir = Path('screener/premarket_screener_signals')
        premarket_save_dir.mkdir(parents=True, exist_ok=True)
        filtered_results.to_csv(f'{premarket_save_dir}/{today}.csv', index=False)
        logger.info(f"Pre-market screener completed. {len(filtered_results)} symbols remaining.")
        
    except Exception as e:
        logger.error(f"Pre-market screener failed: {str(e)}", exc_info=True)

def run_trading_strategy():
    """Run at market open"""
    try:
        if not is_market_open_today():
            logger.info("Market closed today. Skipping trading strategy.")
            return
            
        logger.info("Starting trading strategy...")
        
        # Load today's filtered results
        save_dir = Path('screener/daily_screener_signals')
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
        
        filtered_file = f'{save_dir}/{today}.csv'
        if not Path(filtered_file).exists():
            logger.error(f"No filtered results found for {today}")
            return
            
        filtered_results = pd.read_csv(filtered_file)
        
        # Execute strategy
        strategy = ExecuteStrategy()
        strategy.execute_vwap_spike_strategy(filtered_results)
        
    except Exception as e:
        logger.error(f"Trading strategy failed: {str(e)}", exc_info=True)

def print_test_message():
    logger.info("Test message: Bot is still running!")

def setup_power_management():
    """Configure power management settings for Mac"""
    try:
        # Instead of using pmset directly, create a caffeinate process
        subprocess.Popen(['caffeinate', '-i'])  # Prevent idle sleep
        
        logger.info("Power management settings configured using caffeinate")
    except Exception as e:
        logger.error(f"Failed to configure power settings: {e}")

def reduce_brightness():
    try:
        subprocess.run(['brightness', '0.3'])  # Set to 30%
    except Exception:
        pass  # Brightness control might not be available

def print_resource_usage():
    cpu_percent = psutil.cpu_percent()
    memory_percent = psutil.virtual_memory().percent
    logger.info(f"Resource usage - CPU: {cpu_percent}%, Memory: {memory_percent}%")

def main():
    et_tz = pytz.timezone('US/Eastern')
    
    # Setup power management only if on Mac
    if sys.platform == 'darwin':  # More specific check for Mac
        setup_power_management()
    
    def schedule_in_et(job_time, job_func):
        """Schedule a job using Eastern Time"""
        def job_wrapper():
            # Check if it's the right time in ET before executing
            current_et_time = datetime.now(et_tz).strftime("%H:%M")
            current_et_seconds = datetime.now(et_tz).second
            
            # Only execute if time matches AND we're in the first 5 seconds of the minute
            if current_et_time == job_time and current_et_seconds < 5:
                logger.info(f"Attempting to execute {job_func.__name__} at {current_et_time} ET")
                with job_lock:  # Acquire the lock before executing the job
                    logger.info(f"Executing {job_func.__name__} at {current_et_time} ET")
                    result = job_func()
                    logger.info(f"Completed {job_func.__name__}")
                # Lock is released automatically when exiting the with block

        # Check every 5 seconds
        return scheduler.every(5).seconds.do(job_wrapper)
    
    # Schedule jobs using ET
    # nyse = mcal.get_calendar('NYSE')
    # schedule = pd.DataFrame(nyse.schedule(start_date=datetime.now().date(), end_date=datetime.now().date()))
    # if len(schedule) > 0:
    #     market_open = schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
    #     premarket_time = (market_open - timedelta(minutes=1)).strftime("%H:%M")
    #     market_open_time = market_open.strftime("%H:%M")
    # else:
    #     # Default to 9:30 AM ET if no schedule found
    #     premarket_time = "09:29"
    #     market_open_time = "09:30"
    
    screener_time = "20:00"

    #FOR TESTING
    premarket_time = "09:49"
    market_open_time = "04:00"
    
    print(f'Current ET time: {datetime.now(et_tz).strftime("%H:%M")}')
    print(f'Scheduling jobs (all times ET):')
    print(f'- Daily Screener: {screener_time}')
    # print(f'- Pre-market Screener: {premarket_time}')
    print(f'- Trading Strategy: {market_open_time}')
    
    schedule_in_et(screener_time, run_daily_screener)
    # schedule_in_et(premarket_time, schedule_premarket_screener)
    schedule_in_et(market_open_time, run_trading_strategy)
    
    logger.info("Trading bot initialized and scheduled (all times ET):")
    logger.info("- Daily Screener: 20:00 ET")
    # logger.info(f"- Pre-market Screener: {premarket_time} ET")
    logger.info(f"- Trading Strategy: {market_open_time} ET")
    logger.info(f"Current ET time: {datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("Bot is running and waiting for scheduled tasks...")
    while True:
        scheduler.run_pending()
        if datetime.now().minute == 0:  # Log every hour
            print_resource_usage()
        sys.stdout.flush()  # Force flush the output
        time_lib.sleep(0.1)

if __name__ == "__main__":
    main() 