- BUILD STREAMER BOT THAT CHECKS THE PRICES OF ALL THESE STOCKS AND THEN BUYS THEM IF THEY MEET THE CRITERIA

    - Connect to papermoney account
    - figure out cannot call recv while another coroutine is happening. seems to happen when the streamer is running but nothing to check. No stocks shorted and past buy time threshold.
    - Add trade history log with profit / loss from actual trades
        - If stock failed to short it should not get added to the trade history log.
    - Might need to build failsafe if the program crashes mid-stream. Will need to save the state of the streamer and be able to resume from there.
    - Automate script so that it runs 24/7
    

------        
        
    - Try to get interest rates and hard to borrow data prior to placing trades
        - Keep note of which stocks we can't borrow. 
            - ADD (50M float and 12M market cap)


- OTHER TO-DO's
    - Update backtest to only use current strategy and use schwabdev API for prices
        - also fix so that we don't incorporate current day's data in backtest (current day data is not complete with full pre-market data)
    - Async functions and using another streamer for account positions.
    - Utilize schwabdev streaming functions for more concise code and simplicity.
    - Turn backtest into a script/function. The backtest_functions should be a class and have all the global variables be state variables that get created upon initialization: ENTRY_PRICE
                POSITION
                ENTRY_TIME
                ACCOUNT_SIZE
                BUYS
                RESULT_INDEXER
                BOUGHT_TODAY
                results dataframe
    - Check if there's a way to see the cost of shorting a stock before making a trade call
    - Tune limit and market orders
    - Update organization of "Data base" so that everything can be found in one place. Logs and outputs and files etc.
    

            <!-- # Example organization structure
            project_root/
                └── data/
                    └── YYYY-MM-DD/           # Daily folders
                        ├── daily_screen.xlsx
                        ├── premarket.xlsx
                        ├── trades.xlsx
                        └── results.txt

            # Example code to create and use this structure
            def save_daily_files(data, date):
                folder_path = f"data/{date.strftime('%Y-%m-%d')}"
                os.makedirs(folder_path, exist_ok=True)
                
                # Save files
                data.to_excel(f"{folder_path}/daily_screen.xlsx") -->
    - Find a way to get latest stocks info (like float and market cap) and all stock without having to manually download them through finviz
    - See if there's a way we can filter out stocks hard to borrow or have high interest rates (based on float and market cap?)
    - Maybe i can keep my own DB of historical data for stocks and use that to run my screener?
        - Then the screener would just need to pull data from today and append to my DB
        - It would make the screener faster
        - Learn about access tokens and how to auto authenticate either with my function or with the schwabdev api
    - Make sure we're auto authenticating
        - Can i consolidate the tokens into one file? 
    - Document that we are currently using both in-house Schwab API functions and the schwabdev library.
        - auto_authenticate and get_price_history are using the in-house functions
        - everything else is using the schwabdev library
    


ORCHESTRATOR DESIGN PLAN:

I'd like to turn this into a function that takes in multiple inputs and acts as an orchestrator. I want it to take as input a Ticker, a Target Entry Price, a Buy Time Threshold, a Stop Loss Price, a Profit Take Price, a Sell Time Threshold. 

I want it to run the existing stream for that 'Ticker' and if the price goes above the Target Entry Price, before the Buy Time Threshold i would like to print('SHORT STOCK FUNCTION INITIATED, bought [quantity] shares of [ticker] for a total price of [quantity*ticker price]'). THEN if that message was triggered, i want it to continue streaming until the stop loss price, or the profit take price, or the sell time threshold is hit. I only want to short the stock once, and will always sell the stock by the sell time no matter what.
    



OVERALL GOAL:

I need your help to put together an automated trading strategy for me. I have built a lot of the individual pieces, but now i need help putting all the pieces together. 

Here is how the strategy works. Every night i want to run new_vwap_spike_strategy_screener. This should return a dataframe of stocks that i want to monitor on the next trading day with a information on target entry, a buy time threshold (representing the time at which i want to short the stock prior to), a quantity to buy, a stop loss price, a profit taking price, and a time at which i sell if neither the stop loss price or the profit taking price is hit.

I have a streamer_sd.py file that will stream the price of a given stock. For each row output in the screener, i want to start a stream. If the price goes above the target entry i want to short the stock. The short_stock.py file has that functionality and will take in the ticker, target entry and quantity. If i do short the stock, i want to continue to monitor the stock and cover the short if the price goes below the profit take price, goes above the stop price, or hits the sell time threshold (end of trading day). The cover_short.py has this functionality.

Please give me a detailed overview of changes i need to make to my files and how to best structure everything.