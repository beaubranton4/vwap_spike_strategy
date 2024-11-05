- BUILD STREAMER BOT THAT CHECKS THE PRICES OF ALL THESE STOCKS AND THEN BUYS THEM IF THEY MEET THE CRITERIA
    - Make screener it's own function
    - Build orchestrator:

    - Start streamer so that it's always running during market hours (inputs: ticker, buy price, time threshold to buy, sell prices (stop and take), time threshold to sell)
    - for every output of the stream, we must create a condition checker to tell it if it should buy/sell
    - If ticker crosses buy price, use short_stock_function
    - Create buy (short) function that takes in (ticker, buy price, time threshold to buy)
        - Make sure to check if the stock is eligible to be shorted
        - Make sure to check stock has not already been shorted
        - Market vs limit order
    - Must create sell function that takes in (bought price, sell price, time threshold to sell)
        - Ensure stock has been shorted first
        - Sell at stop
        - Sell at take
        - Sell at time threshold
    - Tie all these pieces together
    - Increase number of orders per minute
    - Make sure we're auto authenticating
        - Can i consolidate the tokens into one file?
    - Make sure we aren't spending cash that we don't have
    - Make all functions async
    - Test as print statements before making trade calls to Schwab API

- Add trade history log
- Add better error handling

- BUILD THEM AS AN AUTOMATED STRATEGY


- OTHER TO-DO's
    - Seperate functions and input variables into different files
        - config.py (for config variables)
        - functions.py (for functions)
    - Find a way to get latest stocks info (like float and market cap) and all stock without having to manually download them through finviz
    - See if there's a way we can filter out stocks hard to borrow or have high interest rates (based on float and market cap?)
    



OVERALL GOAL:

I need your help to put together an automated trading strategy for me. I have built a lot of the individual pieces, but now i need help putting all the pieces together. 

Here is how the strategy works. Every night i want to run new_vwap_spike_strategy_screener. This should return a dataframe of stocks that i want to monitor on the next trading day with a information on target entry, a buy time threshold (representing the time at which i want to short the stock prior to), a quantity to buy, a stop loss price, a profit taking price, and a time at which i sell if neither the stop loss price or the profit taking price is hit.

I have a streamer_sd.py file that will stream the price of a given stock. For each row output in the screener, i want to start a stream. If the price goes above the target entry i want to short the stock. The short_stock.py file has that functionality and will take in the ticker, target entry and quantity. If i do short the stock, i want to continue to monitor the stock and cover the short if the price goes below the profit take price, goes above the stop price, or hits the sell time threshold (end of trading day). The cover_short.py has this functionality.

Please give me a detailed overview of changes i need to make to my files and how to best structure everything.