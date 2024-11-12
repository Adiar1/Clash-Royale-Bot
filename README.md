# Clash Royale Discord Bot

This Discord bot provides various commands and functionalities related to Clash Royale, allowing users to track player and clan statistics, manage linked accounts, and more.

## Features

- Player statistics and information
- Clan war performance tracking
- Account linking and management
- Clan member recommendations
- Tournament rankings
- Privileged role management
- And more!

## Prerequisites

- Python 3.8+
- Discord Bot Token
- Clash Royale API Key

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/Adiar1/Clash-Royale-Bot.git
   cd Clash-Royale-Bot
   ```

2. Install required packages:
   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file in the root directory with the following content:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   CLASH_ROYALE_API_KEY=your_clash_royale_api_key
   ```

   Replace `your_discord_bot_token` and `your_clash_royale_api_key` with your actual Discord bot token and Clash Royale API key.

## Usage

Run the bot using:

```
python main.py
```

## Commands

Here are some of the available commands:

- `/currentwar <clan_tag>`: Get information about the current war for a clan
- `/lastwar <clan_tag>`: Get information about the last war for a clan
- `/nthwar <clan_tag> <n>`: Get information about the nth previous war for a clan
- `/members <clan_tag>`: Get information about current clan members
- `/player <player_tag>`: Get detailed information about a player
- `/link <player_tag> [alt_account]`: Link a player tag to your Discord account
- `/profile [user]`: View linked player tags for yourself or another user
- `/whotokick <clan_tag> [n]`: Get recommendations for members to kick from the clan

For a full list of commands, use the `/info` command in Discord after adding the bot to your server.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This content is not affiliated with, endorsed, sponsored, or specifically approved by Supercell and Supercell is not responsible for it. For more information see Supercell's Fan Content Policy: www.supercell.com/fan-content-policy.
