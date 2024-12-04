#!/bin/bash

# Find and kill the bot process
echo "Stopping the bot..."
pkill -f main.py

# Pull the latest changes from Git
echo "Pulling latest changes..."
git pull origin master

# Restart the bot
echo "Restarting the bot..."
source /root/Clash-Royale-Bot
python3 main.py &

# To use, paste this into the terminal: `./update_bot.sh`