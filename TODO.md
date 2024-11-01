- SCREENER NEEDS TO PASS LIST OF STOCKS, ENTRIES, EXITS, AND BET SIZES
    -Ensure that the screener is working and aligned with same criteria as backtest
        - Seems like some appear in backtest but not screener
        - Confirm with running backtest today
        - Can try to update the screener so that it can run as of point in time
    -Really understand backtest buying and selling logic to replicate in streamer bot

- BUILD STREAMER BOT THAT CHECKS THE PRICES OF ALL THESE STOCKS AND THEN BUYS THEM IF THEY MEET THE CRITERIA

    - get the buys working based on criteria
    - Make sure stock doesn't spike above VWAP pre-market   
    - get the sells working based on criteria
    - make sure that the buys and sells are working with the same criteria as the screener
    - put all of this into a function

- BUILD THEM AS AN AUTOMATED STRATEGY
    - Change Account Size to pull from account api in screener 
    Store Tickers w Buy/Sell Prices in a database
    - Feed that into a streamer that buys and sells based on the criteria

- OTHER TO-DO's
    - Find a way to get latest stocks info (like float and market cap) and all stock without having to manually download them through finviz
    - See if there's a way we can filter out stocks hard to borrow or have high interest rates (based on float and market cap?)
    