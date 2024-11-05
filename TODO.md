- BUILD STREAMER BOT THAT CHECKS THE PRICES OF ALL THESE STOCKS AND THEN BUYS THEM IF THEY MEET THE CRITERIA
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

- BUILD THEM AS AN AUTOMATED STRATEGY
    - Change Account Size to pull from account api in screener 
    Store Tickers w Buy/Sell Prices in a database
    - Feed that into a streamer that buys and sells based on the criteria
    - Put them all together and schedule to run at a specific time using Mage or Airflow or something

- OTHER TO-DO's
    - Seperate functions and input variables into different files
        - config.py (for config variables)
        - functions.py (for functions)
    - Find a way to get latest stocks info (like float and market cap) and all stock without having to manually download them through finviz
    - See if there's a way we can filter out stocks hard to borrow or have high interest rates (based on float and market cap?)
    