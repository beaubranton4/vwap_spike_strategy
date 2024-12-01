

Let me break down this strategy's logic:

### Buy Signal Conditions (ALL must be met):
1. **Volume Spike Detection**:
   - Must be highest volume of the day
   - Volume must be > X times the 10-day average volume (X is defined in `strategy[vol_spike_thresh_index]`)

2. **Price Spike Detection**:
   - Price must spike up from the day's opening low by a certain percentage (defined in `strategy[price_spike_thresh_index]`)
   - The spike's high must be the highest price of the day

3. **Timing Requirements**:
   - Spike must occur before a certain time threshold (defined in `strategy[time_sig_thresh_index]`)
   - Must be during market hours (not before 9:30 AM or after 3:30 PM)

4. **Entry Setup**:
   - After these conditions are met, the strategy waits for the stock to close below VWAP on the signal day
   - The actual entry attempt happens the next business day
   - Pre-market high on entry day must not be higher than previous day's high

### Sell Signal Conditions (ANY of these trigger a sell):
1. **Target Hit**: Price reaches the target profit level (defined by `strategy[target_index]`)
2. **Stop Loss**: Price hits the stop loss level (defined by `strategy[stop_index]`)
3. **Time-Based Exit**: Reaches the sell time threshold (defined by `strategy[sell_time_threshold_index]`)

### Additional Notes:
- The strategy appears to be looking for stocks that make significant moves (both in price and volume) early in the day
- It then waits for a pullback (close below VWAP) before attempting an entry the next day
- The position sizing is determined by `strategy[bet_size_index]` as a percentage of the account size
- The backtest tracks various metrics including win rate, average profit percentage, and different types of exits (target hits, stops, time-based exits)

This appears to be a mean reversion strategy that looks for explosive moves followed by pullbacks, with the expectation of a continuation move the next day.




----

VIRTUAL ENVIRONMENT SETUP

1. Launch EC2 Instance (t3.micro or t3.small)

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
git clone [your-repository-url]

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

Detach from tmux session using `Ctrl+b d` or `tmux detach-client -s trading_bot' from another terminal
To view tmux session you can use: tmux attach-session -t trading_bot
To stop tmux session: tmux kill-session -t trading_bot
To start tmux session: tmux new -s trading_bot
To activate virtual environment: source myenv/bin/activate
To run trading bot: python main.py
