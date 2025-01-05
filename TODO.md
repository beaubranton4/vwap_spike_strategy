

-- Figure out why so many stocks are being skipped in screener and not returning sufficient amount of data from Schwab API
--------------------------------------------------------------------------------------------------

-- Error thrown in close_all_open_orders function

--------------------------------------------------------------------------------------------------

-- Authentication failed and bot got stuck.
        INFO:Schwabdev.Tokens:The refresh token will expire soon! (-02H:41M:29S remaining)
    WARNING:Schwabdev.Tokens:The refresh token has expired!
    [Schwabdev] Open to authenticate: https://api.schwabapi.com/v1/oauth/authorize?client_id=yu3dLbGnr3AXs5j1B9Wjhag1JtzEdXM8&redirect_uri=https://127.0.0.1
    Unable to connect to VS Code server: Error in request.
    Error: connect ENOENT /run/user/1000/vscode-ipc-7bd35661-5e12-4f1d-b24f-43b6a2bbe074.sock
        at PipeConnectWrap.afterConnect [as oncomplete] (node:net:1606:16) {
    errno: -2,
    code: 'ENOENT',
    syscall: 'connect',
    address: '/run/user/1000/vscode-ipc-7bd35661-5e12-4f1d-b24f-43b6a2bbe074.sock'

--------------------------------------------------------------------------------------------------
-- Refresh ticker list (automatically)
--------------------------------------------------------------------------------------------------
-- Join peformance csv with screener to get info on what stocks performed well.
-- Add cumulative performance to screener
-- Add cash balance to performance csv (once we close the long positions)

-- Create update_ticker_list.py to update the ticker_list.csv file with the latest tickers.

--------------------------------------------------------------------------------------------------

-- Analyze what percentage of pre-market screener stocks are actually shorted.
-- Maybe we can remove the pre-market high criteria and see how well that performs in the backtest.


-----------------------------------------------------------------------------------------------------
   
    - Optimize VM costs:
        - Can try and schedule VM instance to only run weekdays. (8-4pm while premarket screener is being used that only pulls since 7am)
        - Other tactics to scale down cost:
            - savings plan


------------------------------------------------------------------------------------------------------

    - Premarket screener to grab premarket data starting at 4:00am ET instead of using Schwab API that only has data starting at 7:00am ET
    - Figure out how many stocks are not getting screened b/c 7am cutoff instead of full data
    - First check that the stream will actually run at 1am ET
    - Use the screener and update screener and main to not rely on premarket screener
        - Start at 1am ET

    
------------------------------------------------------------------------------------------------------

- OTHER TO-DO's
    
    - Incorporate hard to borrow data into screener (premarket or daily screener?)
    - Refresh ticker_list with new fresh data.
    -Instead of relying on trading events i can build a completely seperate function that checks orders to calculate performance
    closed_positions dataframes.
    - Create function to cleanup files taking memory and store them somewhere. or manually do this.
    - Update backtest to only use current strategy and use schwabdev API for prices
        - also fix so that we don't incorporate current day's data in backtest (current day data is not complete with full pre-market data)
        - Turn backtest into a script/function. The backtest_functions should be a class and have all the global variables be state variables that get created upon initialization: ENTRY_PRICE
                POSITION
                ENTRY_TIME
                ACCOUNT_SIZE
                BUYS
                RESULT_INDEXER
                BOUGHT_TODAY
                results dataframe
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
    - Maybe i can keep my own DB of historical data for stocks and use that to run my screener?
        - Then the screener would just need to pull data from today and append to my DB
        - It would make the screener faster
        - Can i consolidate the tokens into one file? 
    - Document that we are currently using both in-house Schwab API functions and the schwabdev library.
        - auto_authenticate and get_price_history are using the in-house functions
        - everything else is using the schwabdev library    



OVERALL GOAL:

I need your help to put together an automated trading strategy for me. I have built a lot of the individual pieces, but now i need help putting all the pieces together. 

Here is how the strategy works. Every night i want to run new_vwap_spike_strategy_screener. This should return a dataframe of stocks that i want to monitor on the next trading day with a information on target entry, a buy time threshold (representing the time at which i want to short the stock prior to), a quantity to buy, a stop loss price, a profit taking price, and a time at which i sell if neither the stop loss price or the profit taking price is hit.

I have a streamer_sd.py file that will stream the price of a given stock. For each row output in the screener, i want to start a stream. If the price goes above the target entry i want to short the stock. The short_stock.py file has that functionality and will take in the ticker, target entry and quantity. If i do short the stock, i want to continue to monitor the stock and cover the short if the price goes below the profit take price, goes above the stop price, or hits the sell time threshold (end of trading day). The cover_short.py has this functionality.

Please give me a detailed overview of changes i need to make to my files and how to best structure everything.