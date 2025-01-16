

# VWAP Spike Trading Strategy Bot

## Overview
This project is a completely autonomous trading system that interfaces with Schwab brokerage accounts to execute a VWAP (Volume Weighted Average Price) spike trading strategy. The system handles everything from market analysis to trade execution with no human intervention required. It was based on a pattern I discovered reading through 30m charts of stocks in 2020. I built the backtest in a jupyter notebook in 2020 but had no idea how to implement it. In 2024, with all of the advancements in AI (specifically Cursor), I decided to revisit the project and build it. It was primarily a fun project to learn about AI, API's, streaming data, and python. It would have been a bonus if the strategy was profitable (sadly it was not).

### Strategy Performance
- Backtesting showed promising results:
  - 65% win rate
  - 40%+ annualized returns
- Real-world implementation challenges:
  - Strategy effectiveness was significantly impacted by hard-to-borrow limitations
  - Many profitable opportunities from backtest were unavailable due to short-selling restrictions
  - Two-month live testing showed proper bot functionality but did not yield profitable results due to the above limitations

### Acknowledgments
Special thanks to the Schwabdev API team for providing the robust library that makes this project possible.

## Project Components


### 1. Core Components
- **Screener System**
  - Daily screener runs nightly to identify potential trades
  - Pre-market screener validates opportunities before market open
  - Implements volume and price spike detection algorithms

- **Trade Execution Engine**
  - Real-time price streaming
  - Automated order placement and management based on screener system
  - Position monitoring and risk management
  - End-of-day position cleanup (no overnight positions held)

- **Authentication System**
  - Handles Schwab API authentication
  - Automatic token refresh
  - Secure credential management

- **Monitoring and Logging**
  - Comprehensive logging system
  - Real-time status monitoring
  - Performance tracking and analysis

### 2. Infrastructure
- **Deployment**
  - AWS EC2 instance based
  - Tmux session management
  - Automated startup and monitoring
  - Cron-based scheduling system

- **Data Management**
  - Historical price data storage
  - Performance metrics tracking
  - Trade journal maintenance
  - Automated cleanup routines

### 3. Safety Features
- Market hours validation
- Position size limits
- Automatic stop-loss enforcement
- End-of-day position closure
- Connection loss handling

### 4. Specific Technical Components of Strategy 

#### Buy Signal Conditions (ALL must be met):
a. **Volume Spike Detection**:
   - Must be highest volume of the day
   - Volume must be > X times the 10-day average volume (X is defined in `strategy[vol_spike_thresh_index]`)

b. **Price Spike Detection**:
   - Price must spike up from the day's opening low by a certain percentage (defined in `strategy[price_spike_thresh_index]`)
   - The spike's high must be the highest price of the day

c. **Timing Requirements**:
   - Spike must occur before a certain time threshold (defined in `strategy[time_sig_thresh_index]`)
   - Must be during market hours (not before 9:30 AM or after 3:30 PM)

d. **Entry Setup**:
   - After these conditions are met, the strategy waits for the stock to close below VWAP on the signal day
   - The actual entry attempt happens the next business day
   - Pre-market high on entry day must not be higher than previous day's high

### Sell Signal Conditions (ANY of these trigger a sell):
1. **Target Hit**: Price reaches the target profit level (defined by `strategy[target_index]`)
2. **Stop Loss**: Price hits the stop loss level (defined by `strategy[stop_index]`)
3. **Time-Based Exit**: Reaches the sell time threshold (defined by `strategy[sell_time_threshold_index]`)


----

VIRTUAL ENVIRONMENT SETUP

1. Launch EC2 Instance (t3.small or greater)

2. Connect to Instance using .pem file (stores keys) 
   - SSH command: `ssh -i [your-key.pem] ec2-user@[your-instance-ip]`
   - Alternatively setup config file to store keys and use `ssh ec2-user@[your-instance-ip]`


# Update system packages
sudo yum update -y  # For Amazon Linux
# OR
sudo apt update && sudo apt upgrade -y  # For Ubuntu

# Install Python and pip
sudo yum install python3 python3-pip  # For Amazon Linux
# OR
sudo apt install python3 python3-pip  # For Ubuntu

# Install git
sudo yum install git  # For Amazon Linux
# OR
sudo apt install git  # For Ubuntu

3. Project Setup

# Clone your repository
git clone vwap_spike_strategy

# Create and activate virtual environment
python3 -m myenv myenv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt


Install tmux
Install cronjob to run monitor_bot.sh every 5 minutes
Create monitor_bot, start_trading_bot, and cleanup scripts:

Setup cronjobs:

      @reboot ~/start_trading_bot.sh
      */5 * * * * ~/monitor_bot.sh
      0 0 * * * /path/to/cleanup.sh

Download schwabdev package from Schwab website and install in virtual environment

Run trading bot using tmux sessions (in start_trading_bot.sh):

   tmux new -s trading_bot
   python3 vwap_spike_strategy/main.py

Detach from tmux session: tmux detach-client -s trading_bot
To view tmux session: tmux attach-session -t trading_bot
To stop tmux session: tmux kill-session -t trading_bot

To activate virtual environment: source myenv/bin/activate
To start tmux session: tmux new -s trading_bot
To run trading bot: python main.py
