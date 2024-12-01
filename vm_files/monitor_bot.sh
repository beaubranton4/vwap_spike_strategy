#!/bin/bash
echo "$(date): Running monitor_bot.sh" >> ~/cron_monitor.log

if ! tmux has-session -t trading_bot 2>/dev/null; then
    echo "$(date): Trading bot session not found. Restarting..." >> ~/cron_monitor.log
    ~/start_trading_bot.sh
fi