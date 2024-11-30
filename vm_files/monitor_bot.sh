if ! tmux has-session -t trading_bot 2>/dev/null; then
    echo "Trading bot session not found. Restarting..."
    ~/start_trading_bot.sh
fi
