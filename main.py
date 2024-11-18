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

# Setup logging
def setup_logging():
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f'trading_bot_{datetime.now().strftime("%Y%m%d")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

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
        save_dir = Path('screener/premarket_screener_signals')
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

def main():
    et_tz = pytz.timezone('US/Eastern')
    
    def schedule_in_et(job_time, job_func):
        """Schedule a job using Eastern Time"""
        def job_wrapper():
            # Check if it's the right time in ET before executing
            current_et_time = datetime.now(et_tz).strftime("%H:%M")
            if current_et_time == job_time:
                return job_func()
        
        # Schedule the wrapper to check every minute
        return scheduler.every().minute.do(job_wrapper)
    
    # Schedule jobs using ET
    nyse = mcal.get_calendar('NYSE')
    schedule = pd.DataFrame(nyse.schedule(start_date=datetime.now().date(), end_date=datetime.now().date()))
    if len(schedule) > 0:
        market_open = schedule.iloc[0]['market_open'].tz_convert('US/Eastern')
        premarket_time = (market_open - timedelta(minutes=1)).strftime("%H:%M")
        market_open_time = market_open.strftime("%H:%M")
    else:
        # Default to 9:30 AM ET if no schedule found
        premarket_time = "09:29"
        market_open_time = "09:30"

    
    print(f'Current ET time: {datetime.now(et_tz).strftime("%H:%M")}')
    print(f'Scheduling jobs (all times ET):')
    print(f'- Daily Screener: 20:00')
    print(f'- Pre-market Screener: {premarket_time}')
    print(f'- Trading Strategy: {market_open_time}')
    
    schedule_in_et("20:00", run_daily_screener)
    schedule_in_et(premarket_time, schedule_premarket_screener)
    schedule_in_et(market_open_time, run_trading_strategy)
    
    logger.info("Trading bot initialized and scheduled (all times ET):")
    logger.info("- Daily Screener: 20:00 ET")
    logger.info(f"- Pre-market Screener: {premarket_time} ET")
    logger.info(f"- Trading Strategy: {market_open_time} ET")
    logger.info(f"Current ET time: {datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.info("Bot is running and waiting for scheduled tasks...")
    while True:
        scheduler.run_pending()
        time_lib.sleep(1)

if __name__ == "__main__":
    main() 