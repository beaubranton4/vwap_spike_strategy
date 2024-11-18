- BUILD STREAMER BOT THAT CHECKS THE PRICES OF ALL THESE STOCKS AND THEN BUYS THEM IF THEY MEET THE CRITERIA

    - Need to fix edge case for screener running friday night is for monday next week. 
        if it falls on a friday, then the output should save with monday's date.
    - Update organization of "Data base" so that everything can be found in one place

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

    - Ensure all criteria like buy time threshold are inputted for production runs
        - BUY TIME THRESHOLD, STRATEGY END TIME, MARKET CLOSE TIME, MANUAL ORDER PLACEMENTS, ACCOUNT SIZE (in Screener)
    - Use pre market screener and run streamer with actual trades to see how it goes manually first.

------        
        
    - Tie all these pieces together with scheduler (Mage? or some other scheduler)
        - Schedule screener to run at 5 pm PT every day and save file. (to DB?)
        - pre market screener to run at 30-60 seconds before market open and save another file. (to DB?)
        - Schedule streamer to run from Market Open to 4pm PT every day 

            <!-- - If you want to start the streamer automatically when the market opens then instead of `streamer.start()` use the call `streamer.start_auto(receiver=print, start_time=datetime.time(9, 29, 0), stop_time=datetime.time(16, 0, 0), on_days=(0,1,2,3,4), now_timezone=zoneinfo.ZoneInfo("America/New_York"), daemon=True)`, shown are the default values which will start & stop the streamer during normal market hours (9:30am-4:00pm). If you want to start and/or stop the streamer at specific times then set the `start_time` and `stop_time` parameters to `datetime.time(HH,MM,SS)`, times are in EST ("America/New_York"); You can also change the days when the streamer starts by the `on_days` parameter, the default (Mon-Fri) is `on_days=(0,1,2,3,4)`. Starting the stream automatically will preserve the previous subscriptions. If you want to use a custom timezone for now then set the `now_timezone` parameter to `zoneinfo.ZoneInfo(...)`. -->
    
    - Run on VM so it continuously runs (find out best way to deploy trading bot)



    - Add trade history log with profit / loss etc. Join with the screener output (Ensure it matches with backtest)
    Work on Order functions and integrate:
    - Create buy (short) function that takes in (ticker, buy price, time threshold to buy)
        - Make sure to check if the stock is eligible to be shorted
        - Make sure to check stock has not already been shorted
        - Market vs limit order
    - Must create sell function that takes in (bought price, sell price, time threshold to sell)
        - Ensure stock has been shorted first
        - Sell at stop
        - Sell at take
        - Sell at time threshold
    - Test with very small amounts first (divide account size by 100 and try rerunning screener).
    - Ensure failsafes so i don't lose all my money while testing.
    - How do we ensure this strategy runs every day without touching it?


- OTHER TO-DO's
    
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
    - Add better error handling
    - Use Schwabdev API for all functions in backtest and screener .ipynb
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