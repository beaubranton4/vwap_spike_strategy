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
import traceback
import gc
from logging.handlers import TimedRotatingFileHandler

# At the top of your file, after imports
logger = None  # Initialize global logger variable

# Setup logging
def setup_logging():
    """Setup logging with ET date-based log file that rotates at midnight ET"""
    global logger
    
    # Create logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create log directory if it doesn't exist
    log_dir = "logs/main"
    os.makedirs(log_dir, exist_ok=True)
    
    # Get current ET date for log file name
    et_tz = pytz.timezone('US/Eastern')
    current_et_date = datetime.now(et_tz).strftime("%Y%m%d")
    log_file = f"{log_dir}/{current_et_date}.log"
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Create TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=7,  # Keep 7 days of logs
        encoding='utf-8',
        utc=True  # Use UTC internally (we'll adjust for ET)
    )
    
    # Calculate ET midnight in UTC for rotation
    et_midnight = datetime.now(et_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    et_midnight_utc = et_midnight.astimezone(pytz.UTC)
    file_handler.rolloverAt = int(et_midnight_utc.timestamp()) + 24*60*60  # Next midnight ET
    
    # Custom namer function to use ET date
    def namer(default_name):
        # Extract the date part from default_name
        dt = datetime.now(et_tz)
        return f"{log_dir}/{dt.strftime('%Y%m%d')}.log"
    
    file_handler.namer = namer
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Add handlers
    logger.addHandler(file_handler)
    
    # Add console handler for terminal output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    logger.info(f"Logging initialized for ET date: {current_et_date}")
    
    return logger

# Now create the logger
logger = setup_logging()

# Create a lock instance
job_lock = threading.Lock()

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

# def print_resource_usage():
#     cpu_percent = psutil.cpu_percent()
#     memory_percent = psutil.virtual_memory().percent
#     logger.info(f"Resource usage - CPU: {cpu_percent}%, Memory: {memory_percent}%")

def is_market_date(schedule_input: pd.DataFrame, check_date: datetime = None) -> bool:
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
        schedule_dates = schedule_input.index.date
        
        # Check if date exists in schedule
        is_trading_day = check_date in schedule_dates
        
        logger.info(f"Date check for {check_date}: {'Trading day' if is_trading_day else 'Non-trading day'}")
        return is_trading_day
        
    except Exception as e:
        logger.error(f"Error checking market date: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def run_daily_screener():
    """Run at 12:01 ET """
    try:
        # Check yesterday's date
        last_market_day = last_trading_day(datetime.now(pytz.timezone('US/Eastern')))

        client = get_authenticated_client()
        logger.info("Starting daily screener...")
        results = run_vwap_spike_screener(
            client=client,
            ticker_list=ticker_list,
            combinations=combinations,
            day_of_backtest=last_market_day,
            period_type=period_type,
            period=period,
            frequency_type=frequency_type,
            frequency=frequency,
            start_time=start_time,
            end_time=end_time,
            need_extended_hours_data=need_extended_hours_data,
            need_previous_close=need_previous_close,
            rolling_lookback=rolling_lookback,
            price_spike_thresh_index=price_spike_thresh_index,
            time_sig_thresh_index=time_sig_thresh_index,
            buy_time_threshold_index=buy_time_threshold_index,
            vol_spike_thresh_index=vol_spike_thresh_index,
            sell_time_threshold_index=sell_time_threshold_index,
            stop_index=stop_index,
            target_index=target_index
    )
        
        # Save results
        # save_dir = Path('screener/daily_screener_signals')
        # save_dir.mkdir(parents=True, exist_ok=True)
        
        # date_to_trade = next_business_day(yesterday)
        # results.to_csv(f'{save_dir}/{date_to_trade}.csv', index=False)
        
        logger.info(f"Daily screener completed. Found {len(results)} signals.")
        
    except Exception as e:
        logger.error(f"Daily screener failed: {str(e)}", exc_info=True)

def schedule_premarket_screener():
    """Run 1 minute before market open"""
    try:
            
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
        # premarket_save_dir = Path('screener/premarket_screener_signals')
        # premarket_save_dir.mkdir(parents=True, exist_ok=True)
        # filtered_results.to_csv(f'{premarket_save_dir}/{today}.csv', index=False)
        
        logger.info(f"Pre-market screener completed. {len(filtered_results)} symbols remaining.")
        
    except Exception as e:
        logger.error(f"Pre-market screener failed: {str(e)}", exc_info=True)

def run_trading_strategy():
    """Run at market open"""
    try:
            
        logger.info("Starting trading strategy...")
        
        # Load today's filtered results
        save_dir = Path('screener/premarket_screener_signals')
        today = datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d')
        
        filtered_file = f'{save_dir}/{today}.csv'
        if not Path(filtered_file).exists():
            logger.error(f"No filtered results found for {today}")
            return
            
        filtered_results = pd.read_csv(filtered_file)
        
        # Execute strategy
        strategy = ExecuteStrategy(use_mock_data=False)
        strategy.execute_vwap_spike_strategy(filtered_results)
        
    except Exception as e:
        logger.error(f"Trading strategy failed: {str(e)}", exc_info=True)

def refresh_market_schedule():
    """Refresh the market schedule at midnight ET"""
    try:
        global market_schedule
        et_tz = pytz.timezone('US/Eastern')
        today = datetime.now(et_tz).date()
        start_date = today - timedelta(days=7)  # One week ago
        end_date = today + timedelta(days=7)    # One week ahead
        
        nyse = mcal.get_calendar('NYSE')
        market_schedule = pd.DataFrame(nyse.schedule(start_date=start_date, end_date=end_date))
        logger.info(f"Updated market schedule from {start_date} to {end_date}")
        
    except Exception as e:
        logger.error(f"Error refreshing market schedule: {str(e)}")
        logger.error(traceback.format_exc())

def close_end_of_day_positions():
    """Close all positions at market close"""
    try:
        today = datetime.now(pytz.timezone('US/Eastern'))
            
        logger.info("Starting end-of-day position closing...")
        
        # Load today's filtered results
        premarket_screener_df = Path('screener/premarket_screener_signals') / f"{today.strftime('%Y-%m-%d')}.csv"            
        positions_to_close = pd.read_csv(premarket_screener_df)
        
        # Initialize client and close positions
        client = get_authenticated_client()
        close_matched_positions(client, positions_to_close)
        
        logger.info("End-of-day position closing completed.")
        
    except Exception as e:
        logger.error(f"End-of-day position closing failed: {str(e)}")
        logger.error(traceback.format_exc())

def log_resource_usage():
    cpu_percent = psutil.cpu_percent(interval=1)
    memory_percent = psutil.virtual_memory().percent
    logger.info(f"Resource usage - CPU: {cpu_percent}%, Memory: {memory_percent}%")

def calculate_sleep_time(current_time, jobs):
    """Calculate the appropriate sleep time based on the next scheduled job"""
    if not jobs:
        logger.info("No jobs scheduled, using default sleep time of 1.0s")
        return 1.0
    
    # Get all next run times
    next_run_times = []
    et_tz = pytz.timezone('US/Eastern')
    
    # Log current time
    logger.info(f"Current time (ET): {current_time}")
    
    for job in jobs:
        try:
            # Get the job's target time
            target_time = getattr(job.job_func, 'target_time', None)
            if target_time:
                logger.info(f"Job {job.job_func.__name__} target time: {target_time}")
                
                # Convert target_time to datetime
                target_datetime = datetime.strptime(target_time, "%H:%M:%S")
                today_et = current_time.date()
                target_datetime = et_tz.localize(
                    datetime.combine(today_et, target_datetime.time())
                )
                
                # If target time is already passed for today, skip it
                if target_datetime < current_time:
                    continue
                    
                next_run_times.append(target_datetime)
                logger.info(f"Next run for {job.job_func.__name__}: {target_datetime} ET")
                
        except Exception as e:
            logger.error(f"Error getting next run time for job: {e}")
            continue
    
    if not next_run_times:
        logger.info("No valid next run times found")
        return 1.0
    
    # Constants
    MAX_SLEEP = 60  # Maximum sleep time of 60 seconds
    BUFFER_TIME = 2  # Wake up 2 seconds before job
    MIN_SLEEP = 0.1  # Minimum sleep time
    
    # Find earliest next run time
    next_run = min(next_run_times)
    
    # Ensure current_time is timezone aware
    if current_time.tzinfo is None:
        current_time = et_tz.localize(current_time)
    
    # Log times in ET for debugging
    # logger.info(f"Next run (ET): {next_run.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    # logger.info(f"Current time (ET): {current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    time_until_next_job = (next_run - current_time).total_seconds()
    
    if time_until_next_job > BUFFER_TIME:
        sleep_time = min(time_until_next_job - BUFFER_TIME, MAX_SLEEP)
    else:
        sleep_time = MIN_SLEEP
    
    logger.info(f"Time until next job: {time_until_next_job:.1f}s")
    logger.info(f"Sleeping for: {sleep_time:.1f}s")
    
    return sleep_time

def main():
    global logger  # Add this line to access global logger
    et_tz = pytz.timezone('US/Eastern')
    current_log_date = datetime.now(et_tz).strftime("%Y%m%d")
    
    # Initialize logger if not already done
    if logger is None:
        logger = setup_logging()
    
    if sys.platform == 'darwin':
        setup_power_management()
    
    def schedule_in_et(job_time, job_func):
        """Schedule a job using Eastern Time with second precision"""
        et_tz = pytz.timezone('US/Eastern')
        
        def job_wrapper():
            try:
                # Get current time in ET
                current_et = datetime.now(et_tz)
                current_et_time = current_et.strftime("%H:%M:%S")
                
                # Convert job_time to today's date in ET
                job_datetime = datetime.strptime(job_time, "%H:%M:%S")
                today_et = current_et.date()
                job_datetime = et_tz.localize(
                    datetime.combine(today_et, job_datetime.time())
                )
                
                # Calculate time difference
                time_diff = abs((current_et - job_datetime).total_seconds())
                
                if time_diff <= 5:  # + or - 5 second window
                    logger.info(f"Attempting to execute {job_func.__name__} at {current_et_time} ET")
                    with job_lock:
                        logger.info(f"Executing {job_func.__name__} at {current_et_time} ET")
                        result = job_func()
                        logger.info(f"Completed {job_func.__name__}")
                    
            except Exception as e:
                logger.error(f"Error in job {job_func.__name__}: {str(e)}")
                logger.error(traceback.format_exc())

        # Store the target time for logging
        job_wrapper.target_time = job_time
        
        # Schedule the job with the scheduler
        return scheduler.every(1).seconds.do(job_wrapper)
    
    # Initialize market_schedule with retry
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            global market_schedule
            market_schedule = pd.DataFrame()
            refresh_market_schedule()
            if len(market_schedule) > 0:
                break
            retry_count += 1
            time_lib.sleep(5)
        except Exception as e:
            logger.error(f"Market schedule initialization attempt {retry_count} failed: {str(e)}")
            retry_count += 1
            time_lib.sleep(5)
    
    # Check if today is a market date
    today = datetime.now(et_tz)
    logger.info(f"is_market_date: {is_market_date(market_schedule, today)}")
    
    if not is_market_date(market_schedule, today):
        logger.info(f"Today ({today.strftime('%Y-%m-%d')}) is not a trading day. No jobs will be scheduled.")
        while True:     
            # Optionally log that the bot is still running
            if datetime.now().minute == 0:  # Log once per hour
                logger.info("Bot is running - Waiting for next trading day")
            time_lib.sleep(60)  # Sleep for 1 minute
        return

    # If it is a market day, schedule all jobs
    screener_time = "00:10:00"

    #FOR TESTING
    # if today.date() == datetime(2024, 11, 30).date():
    #     screener_time = "15:25:30"
    #     premarket_time = "09:29:00"
    #     market_open_time = "09:29:40"  # 20 seconds before 9:30
    #     market_close_time = "15:59:40"  # 20 seconds before 16:00

    if len(market_schedule) > 0:
        # Check if the DataFrame is empty
        if market_schedule.empty:
            logger.error("Market schedule is empty. Cannot proceed.")
            return

        # Use the index to filter for today's schedule
        today_schedule = market_schedule[market_schedule.index.date == today.date()]

        # Check if today_schedule is empty
        if today_schedule.empty:
            logger.warning(f"No market schedule found for today ({today.date()}).")
        else:
            market_open = today_schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
            market_close = today_schedule.iloc[0]['market_close'].tz_convert('US/Eastern')
        
        # Calculate times 20 seconds before market events
        premarket_time = (market_open - timedelta(minutes=1)).strftime("%H:%M:%S")
        market_open_time = (market_open - timedelta(seconds=20)).strftime("%H:%M:%S")
        market_close_time = (market_close - timedelta(seconds=20)).strftime("%H:%M:%S")
    else:
        logger.warning("Using default market times due to schedule initialization failure")
        premarket_time = "09:29:00"
        market_open_time = "09:29:40"  # 20 seconds before 9:30
        market_close_time = "15:59:40"  # 20 seconds before 16:00
        
    
    # Schedule all jobs with second precision
    schedule_in_et("00:05:00", refresh_market_schedule)
    schedule_in_et(screener_time, run_daily_screener)
    schedule_in_et(premarket_time, schedule_premarket_screener)
    schedule_in_et(market_open_time, run_trading_strategy)
    schedule_in_et(market_close_time, close_end_of_day_positions)
    
    logger.info("Trading bot initialized and scheduled (all times ET):")
    logger.info(f"- Schedule Refresh: 00:05:00 ET")
    logger.info(f"- Daily Screener: {screener_time} ET")
    logger.info(f"- Pre-market Screener: {premarket_time} ET")
    logger.info(f"- Trading Strategy: {market_open_time} ET")
    logger.info(f"- Position Closing: {market_close_time} ET")
    logger.info(f"Current ET time: {datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Main loop with adaptive sleep
    last_resource_log = time_lib.time()
    resource_log_interval = 300  # Log resources every 5 minutes
    
    while True:
        try:
            # Ensure current_time is timezone aware
            current_time = datetime.now(et_tz)
            
            # Get all scheduled jobs
            jobs = scheduler.get_jobs()
            
            # Calculate and execute sleep
            sleep_time = calculate_sleep_time(current_time, jobs)
            time_lib.sleep(sleep_time)
            
            # Run pending jobs
            scheduler.run_pending()
            
            # Log resource usage periodically
            current_time = time_lib.time()
            if current_time - last_resource_log >= resource_log_interval:
                log_resource_usage()
                last_resource_log = current_time
                gc.collect()  # Periodic garbage collection
            
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            logger.error(traceback.format_exc())
            time_lib.sleep(5)  # Wait before retrying

if __name__ == "__main__":
    main() 