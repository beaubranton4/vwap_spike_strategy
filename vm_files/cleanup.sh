#!/bin/bash

# Path to your project
PROJECT_PATH="/home/ec2-user/vwap_spike_strategy"

# Keep last 7 days of logs
find "$PROJECT_PATH/logs/main" -name "*.log" -type f -mtime +7 -delete

# Keep last 30 days of screener results (if you implement them later)
find "$PROJECT_PATH/screener" -name "*.csv" -type f -mtime +30 -delete

# Log the cleanup
echo "$(date): Cleanup completed" >> "$PROJECT_PATH/logs/cleanup.log"