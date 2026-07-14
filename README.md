# Clash Royale Discord Bot

This Discord bot provides various commands and functionalities related to Clash Royale, allowing users to track player and clan statistics, manage linked accounts, and more.

## Features

- Player statistics and information
- Clan war performance tracking
- Automated attack reminders on war days (per-server channel, timezone, and reminder times)
- Account linking and management (Clash Royale tags and optional DeckAI IDs)
- Opponent war-deck scouting via DeckAI (`/spy_ai`)
- Clan member kick and promotion recommendations
- Tournament rankings
- Privileged role management
- Web control panel for managing the bot process, `.env`, and database
- And more!

## Add the Bot to Your Server

To use this bot in your Discord server, simply click on the following link:

[Add Clash Royale Bot to Your Server](https://discord.com/oauth2/authorize?client_id=1260102504377483286&permissions=8&integration_type=0&scope=bot)

**Note:** This bot is currently being used by 13 of the top 100 clans in the USA!

## Prerequisites

- Python 3.12+
- Discord Bot Token found [here](https://discord.com/developers/applications)
- Clash Royale API Key found [here](https://developer.clashroyale.com/#/)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/Adiar1/Clash-Royale-Bot.git
   cd Clash-Royale-Bot
   ```

2. Install the project (dependencies are pinned in `pyproject.toml`):
   ```
   python -m venv .venv && source .venv/bin/activate
   pip install .
   ```

3. Create a `.env` file in the root directory with the following content:
   ```
   DISCORD_TOKEN=your_discord_bot_token
   CLASH_ROYALE_API_KEY=your_clash_royale_api_key
   DECKAI_API_KEY=optional_deckai_key       # only needed for /spy_ai
   FLASK_SECRET_KEY=random_secret           # only needed for the control panel
   ADMIN_PASSWORD=control_panel_password    # only needed for the control panel
   ```

## Usage

Run the bot using:

```
python main.py
```

On first start after upgrading from the old schema, the database is migrated
automatically (the original tables are kept as `legacy_*` backups).

### Control Panel

An optional Flask control panel lets you start/stop the bot, pull updates from
git (with an update-and-restart shortcut), browse and download the bot's files,
edit `.env`, and inspect the database from a browser:

```
python control_panel.py
```

It listens on port 5000 by default (override with `PORT`) and requires
`FLASK_SECRET_KEY` and `ADMIN_PASSWORD` to be set in `.env`.

For a production host, run the bot and panel as systemd services so they start
on boot and restart on crash — see [`linode/DEPLOY.md`](linode/DEPLOY.md). When
`BOT_SERVICE` is set in `.env` (e.g. `BOT_SERVICE=crbot.service`), the panel's
start/stop toggle drives that systemd service instead of spawning the bot as a
child process, which keeps the bot's lifecycle clean across panel restarts.

## Project Structure

```
main.py            entry point: config -> bot.run()
bot.py             ClashBot: shared aiohttp session, service clients, global error handler
config.py          typed env config (fails fast on missing vars)
errors.py          BotError hierarchy shown to users by the global handler
control_panel.py   Flask web control panel (process control, .env editor, DB viewer)
cogs/              slash commands grouped by domain (war, clan, links, admin, misc, reminders)
services/          all external HTTP calls (Clash Royale API, DeckAI) + scoring math
db/                aiosqlite schema/migration + repository with every query
ui/                shared embeds, emoji constants, and reusable views
linode/            control panel templates/static, systemd unit files, DEPLOY.md
tests/             pytest suite (repository, migration, war-log math, HTTP client)
```

## Development

```
pip install --group dev .
ruff check .        # lint
pytest              # tests
```

## Commands

### War

- `/currentwar <clan_tag>`: Get information about the current war for a clan
- `/lastwar <clan_tag>`: Get information about the last war for a clan
- `/nthwar <clan_tag> <n>`: Get information about the nth previous war for a clan (1-10)
- `/stats <player_tag> <from_war> <to_war>`: Calculate individual stats over a range of wars

### Player & Clan

- `/player <player_tag>`: Get detailed information about a player
- `/members <clan_tag>`: Get information about current clan members
- `/clan <clan_tag>`: List current clan members and how many weeks ago they joined
- `/viewlinks <clan_tag>`: List clan members with their linked Discord accounts
- `/rankings <tourny_tag>`: List tournament members' names, scores, and ranks
- `/whotokick <clan_tag> [n] [exclude_leadership]`: Get recommendations for members to kick from the clan
- `/whotopromote <clan_tag> [n] [exclude_leadership]`: Get recommendations for members who might deserve a promotion
- `/spy_ai <opponent_player_tag> [someone_else]`: Scout an opponent's recent clan war decks via DeckAI

### Account Linking

- `/link [user]`: Open the link manager to set a main player tag, add alts, edit DeckAI IDs, or remove accounts (managing another user requires privileges)
- `/profile [user]`: View linked player tags for yourself or another user
- `/wipelinks [user]`: Remove linked player tags

### Server Management

- `/nicklink <clan_tag> [nickname]`: Link a clan tag to a nickname (leave nickname empty to delete it)
- `/viewnicks`: View all clan nicknames in this server
- `/reminders <clan_tag>`: Set up or edit automated attack reminders sent on war days
- `/editperms` / `/viewperms`: Edit or view privileged roles in this server
- `/editmemberroles` / `/viewmemberroles`: Edit or view roles corresponding to Clash Royale positions

Clan commands accept a server nickname in place of a tag, and player commands
accept a Discord @mention in place of a tag. For a full list of commands, use
the `/info` command in Discord after adding the bot to your server.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This content is not affiliated with, endorsed, sponsored, or specifically approved by Supercell and Supercell is not responsible for it. For more information see Supercell's Fan Content Policy: www.supercell.com/fan-content-policy.
