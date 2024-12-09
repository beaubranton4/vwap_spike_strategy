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
    global logger  # Make sure we're modifying the global logger
    
    # Create or get logger
    logger = logging.getLogger(__name__)
    logger.handlers.clear()  # Clear existing handlers
    
    logger.propagate = False
    logger.setLevel(logging.INFO)
    
    # Create log directory if it doesn't exist
    log_dir = "logs/main"
    os.makedirs(log_dir, exist_ok=True)
    
    # Get current ET date for log file name
    et_tz = pytz.timezone('US/Eastern')
    current_et = datetime.now(et_tz)
    current_et_date = current_et.strftime("%Y%m%d")
    log_file = f"{log_dir}/{current_et_date}.log"
    
    class ETFormatter(logging.Formatter):
        def converter(self, timestamp):
            dt = datetime.fromtimestamp(timestamp)
            et_tz = pytz.timezone('US/Eastern')
            return dt.astimezone(et_tz)
        
        def formatTime(self, record, datefmt=None):
            dt = self.converter(record.created)
            if datefmt:
                return dt.strftime(datefmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S %Z")
    
    formatter = ETFormatter('%(asctime)s - %(levelname)s - %(message)s')
    
    class ETTimedRotatingFileHandler(TimedRotatingFileHandler):
        def __init__(self, *args, **kwargs):
            self.et_tz = pytz.timezone('US/Eastern')
            super().__init__(*args, **kwargs)
            
        def computeRollover(self, currentTime):
            """Override to use ET for rollover calculations"""
            current_et = datetime.fromtimestamp(currentTime).astimezone(self.et_tz)
            next_midnight_et = (current_et.replace(hour=0, minute=0, second=0, microsecond=0) 
                              + timedelta(days=1))
            return int(next_midnight_et.timestamp())
            
        def doRollover(self):
            """Override to use ET date for new file name"""
            if self.stream:
                self.stream.close()
                self.stream = None
            
            # Get current ET time for new file name
            current_et = datetime.now(self.et_tz)
            new_file = f"{log_dir}/{current_et.strftime('%Y%m%d')}.log"
            
            # Create new file for current day
            self.baseFilename = new_file
            if not self.delay:
                self.stream = self._open()
            
            # Set next rollover time using time_lib instead of time
            self.rolloverAt = self.computeRollover(time_lib.time())
            
            logger.info(f"Log file rolled over to: {new_file}")
    
    # Create and configure the file handler
    file_handler = ETTimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8',
        utc=False
    )
    
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    # Add handlers
    logger.addHandler(file_handler)
    
    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    # Force immediate rollover if needed
    current_et = datetime.now(et_tz)
    if os.path.exists(log_file) and current_et.strftime("%Y%m%d") != current_et_date:
        file_handler.doRollover()
    
    logger.info(f"Logging initialized for ET date: {current_et_date}")
    
    return logger

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
        
        # logger.info(f"Date check for {check_date}: {'Trading day' if is_trading_day else 'Non-trading day'}")
        return is_trading_day
        
    except Exception as e:
        logger.error(f"Error checking market date: {str(e)}")
        logger.error(traceback.format_exc())
        return False

def run_daily_screener():
    """Run at 12:01 ET """
    global logger
    
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

    global logger
    
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

    global logger
    
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

    global logger
    
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

    global logger

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

def run_trade_analysis():
    """Run trade analysis for today's trades"""
    
    global logger
    
    try:
        client = get_authenticated_client()
        get_todays_trades(client)
        logger.info("Successfully ran trade analysis for today")
        
    except Exception as e:
        logger.error(f"Trade analysis failed: {str(e)}")
        logger.error(traceback.format_exc())

# def log_resource_usage():
#     cpu_percent = psutil.cpu_percent(interval=1)
#     memory_percent = psutil.virtual_memory().percent
#     logger.info(f"Resource usage - CPU: {cpu_percent}%, Memory: {memory_percent}%")

def calculate_sleep_time(current_time, jobs):
    """Calculate the appropriate sleep time based on the next scheduled job"""

    global logger

    et_tz = pytz.timezone('US/Eastern')
    
    # If no jobs, check if we should wait for next trading day
    if not jobs:
        try:
            # Get next trading day
            next_trading_day = None
            check_date = current_time
            
            # Look up to 7 days ahead for the next trading day
            for _ in range(7):
                check_date = check_date + timedelta(days=1)
                if is_market_date(market_schedule, check_date):
                    next_trading_day = check_date
                    break
            
            if next_trading_day:
                # Calculate time until midnight of next trading day
                next_midnight = next_trading_day.replace(hour=0, minute=0, second=0, microsecond=0)
                seconds_until_midnight = (next_midnight - current_time).total_seconds()
                
                # Log once per hour that we're waiting for next trading day
                if current_time.minute == 0:
                    logger.info(f"Waiting for next trading day: {next_trading_day.strftime('%Y-%m-%d')}")
                    logger.info(f"Time until midnight: {seconds_until_midnight/3600:.1f} hours")
                
                # Sleep for up to 60 seconds at a time
                return min(60, max(0.1, seconds_until_midnight))
            else:
                logger.warning("No trading days found in the next week")
                return 60
                
        except Exception as e:
            logger.error(f"Error calculating next trading day: {e}")
            return 60
    
    # Rest of the existing function for handling active jobs
    next_run_times = []
    
    for job in jobs:
        try:
            target_time = getattr(job.job_func, 'target_time', None)
            if target_time:
                target_datetime = datetime.strptime(target_time, "%H:%M:%S")
                today_et = current_time.date()
                target_datetime = et_tz.localize(
                    datetime.combine(today_et, target_datetime.time())
                )
                
                # If target time is already passed for today, skip it
                if target_datetime < current_time:
                    continue
                    
                next_run_times.append(target_datetime)
                
        except Exception as e:
            logger.error(f"Error getting next run time for job: {e}")
            continue
    
    # Constants
    MAX_SLEEP = 60  # Maximum sleep time of 60 seconds
    BUFFER_TIME = 2  # Wake up 2 seconds before job
    MIN_SLEEP = 0.1  # Minimum sleep time
    
    if next_run_times:
        # Find earliest next run time
        next_run = min(next_run_times)
        
        # Ensure current_time is timezone aware
        if current_time.tzinfo is None:
            current_time = et_tz.localize(current_time)
        
        time_until_next_job = (next_run - current_time).total_seconds()
        
        if time_until_next_job > BUFFER_TIME:
            sleep_time = min(time_until_next_job - BUFFER_TIME, MAX_SLEEP)
        else:
            sleep_time = MIN_SLEEP
            
        return sleep_time
    
    # If we get here, today's jobs are done
    return 60  # Sleep for 60 seconds before checking next day

def initialize_market_schedule(max_retries=3):
    """Initialize market schedule with retry logic"""
    global market_schedule
    market_schedule = pd.DataFrame()
    
    for retry_count in range(max_retries):
        try:
            refresh_market_schedule()
            if len(market_schedule) > 0:
                return True
            logger.warning(f"Retry {retry_count + 1}: Market schedule empty")
        except Exception as e:
            logger.error(f"Market schedule initialization attempt {retry_count + 1} failed: {e}")
        time_lib.sleep(5)
    return False

def get_market_times(market_schedule, today):
    """Calculate market-related times for scheduling"""
    times = {
        'schedule_refresh': "00:05:00",
        'screener': "00:10:00",
        'premarket': "09:29:30",
        'market_open': "09:30:00",
        'market_close': "15:59:00",
        'trade_analysis': "18:00:00"
    }
    
    if not market_schedule.empty:
        today_schedule = market_schedule[market_schedule.index.date == today.date()]
        if not today_schedule.empty:
            market_open = today_schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
            market_close = today_schedule.iloc[0]['market_close'].tz_convert('US/Eastern')
            
            times.update({
                'premarket': (market_open - timedelta(seconds=30)).strftime("%H:%M:%S"),
                'market_open': market_open.strftime("%H:%M:%S"),
                'market_close': (market_close - timedelta(minutes=1)).strftime("%H:%M:%S")
            })
    return times

def schedule_daily_jobs(times):
    """Schedule all daily jobs"""
    jobs = [
        (times['schedule_refresh'], refresh_market_schedule),
        (times['screener'], run_daily_screener),
        (times['premarket'], schedule_premarket_screener),
        (times['market_open'], run_trading_strategy),
        (times['market_close'], close_end_of_day_positions),
        (times['trade_analysis'], run_trade_analysis)
    ]
    
    for time, func in jobs:
        schedule_in_et(time, func)
    
    logger.info("Trading bot initialized and scheduled (all times ET):")
    for (time, func) in jobs:
        logger.info(f"- {func.__name__}: {time} ET")

def log_bot_status(current_time, jobs):
    """Log bot status and next scheduled job"""
    # Only log status updates at the top of each hour
    if current_time.minute == 0:
        et_tz = pytz.timezone('US/Eastern')
        logger.info("Bot is running - Active Trading Day")
        
        # Log next scheduled job (hourly)
        if jobs:
            next_jobs = []
            for job in jobs:
                target_time = getattr(job.job_func, 'target_time', None)
                if target_time:
                    # Parse target time
                    job_time = datetime.strptime(target_time, "%H:%M:%S").time()
                    
                    # Combine with today's date
                    job_datetime = datetime.combine(current_time.date(), job_time)
                    job_datetime = et_tz.localize(job_datetime)
                    
                    # If this job time has passed today, schedule it for tomorrow
                    if job_datetime <= current_time:
                        job_datetime += timedelta(days=1)
                    
                    next_jobs.append((job_datetime, job.job_func.__name__))
            
            if next_jobs:
                # Get the next job (earliest future job)
                next_time, next_job = min(next_jobs, key=lambda x: x[0])
                time_until = next_time - current_time
                logger.info(
                    f"Next scheduled job: {next_job} at {next_time.strftime('%Y-%m-%d %H:%M:%S')} ET "
                    f"(in {time_until.total_seconds()/3600:.1f} hours)"
                )
            else:
                logger.info("No more jobs scheduled")
        else:
            logger.info("No jobs currently scheduled")

def schedule_in_et(time_str, func):
    """Schedule a job to run at a specific time in ET
    
    Args:
        time_str (str): Time in format "HH:MM:SS" in ET
        func: Function to schedule
    """
    try:
        # Store the target time as an attribute of the function
        func.target_time = time_str
        
        # Convert ET time to local time for scheduler
        et_tz = pytz.timezone('US/Eastern')
        local_tz = datetime.now().astimezone().tzinfo
        
        # Parse the ET time
        et_time = datetime.strptime(time_str, "%H:%M:%S")
        et_time = et_tz.localize(datetime.combine(datetime.now().date(), et_time.time()))
        
        # Convert to local time
        local_time = et_time.astimezone(local_tz)
        local_time_str = local_time.strftime("%H:%M:%S")
        
        # Schedule the job using local time
        scheduler.every().day.at(local_time_str).do(func)
        logger.debug(f"Scheduled {func.__name__} for {time_str} ET ({local_time_str} local)")
        
    except Exception as e:
        logger.error(f"Failed to schedule {func.__name__} for {time_str} ET: {str(e)}")
        logger.error(traceback.format_exc())

def main():
    global logger
    et_tz = pytz.timezone('US/Eastern')
    logger = setup_logging()
    
    if sys.platform == 'darwin':
        setup_power_management()
    
    # Initialize market schedule
    if not initialize_market_schedule():
        logger.error("Failed to initialize market schedule after max retries")
        return
    
    # Initial setup
    today = datetime.now(et_tz)
    last_date_checked = today.date()
    last_resource_log = time_lib.time()
    resource_log_interval = 300  # 5 minutes
    
    # Schedule initial jobs
    market_times = get_market_times(market_schedule, today)
    schedule_daily_jobs(market_times)
    logger.info(f"Current ET time: {datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Main loop
    while True:
        try:
            current_time = datetime.now(et_tz)
            
            # Check for day change
            if current_time.date() != last_date_checked:
                logger.info(f"New day detected: {current_time.date()}")
                
                # Reinitialize logger for new day
                logger = setup_logging()
                
                refresh_market_schedule()

                # Check if today is a market date
                if not is_market_date(market_schedule, current_time):
                    logger.info(f"Today ({today.strftime('%Y-%m-%d')}) is not a trading day")
                    while not is_market_date(market_schedule, current_time):
                        current_time = datetime.now(et_tz)
                        if current_time.minute == 0:
                            logger.info("Bot is running - Waiting for next trading day")
                        time_lib.sleep(60)
                    logger.info("Today is now a trading day.")
                
                if is_market_date(market_schedule, current_time):
                    logger.info("Scheduling jobs for new trading day")
                    scheduler.clear()
                    market_times = get_market_times(market_schedule, current_time)
                    schedule_daily_jobs(market_times)
                
                last_date_checked = current_time.date()
            
            # Get and process jobs
            jobs = scheduler.get_jobs()
            log_bot_status(current_time, jobs)
            
            # Sleep and run jobs
            sleep_time = calculate_sleep_time(current_time, jobs)
            time_lib.sleep(sleep_time)
            scheduler.run_pending()
            
            # Periodic maintenance
            if time_lib.time() - last_resource_log >= resource_log_interval:
                gc.collect()
                last_resource_log = time_lib.time()
                
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            logger.error(traceback.format_exc())
            time_lib.sleep(5)

if __name__ == "__main__":
    main() 