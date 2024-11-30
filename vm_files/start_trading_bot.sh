#!/bin/bash
cd vwap_spike_strategy
source myenv/bin/activate
tmux new-session -d -s trading_bot 'python main.py'
