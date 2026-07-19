# Clash Royale Discord Bot

This Discord bot provides various commands and functionalities related to Clash Royale, allowing users to track player and clan statistics, manage linked accounts, and more.

## Features

- Player statistics and information
- Clan war performance tracking
- Automated attack reminders on war days (per-server channel, timezone, and reminder times)
- Recruiting needs tracking for a clan family — auto-derived from each clan's open slots, with one-tap manager prompts when a clan loses members
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
   GUIDE_URL=https://adiar1.github.io/Clash-Royale-Bot/   # optional; where /info links for the command guide
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
edit `.env`, and inspect the database from a browser. Its `/guide` route
redirects to the hosted [command guide](#command-guide) (or serves it directly
if `GUIDE_URL` isn't set):

```
python control_panel.py
```

It listens on port 5000 by default (override with `PORT`) and requires
`FLASK_SECRET_KEY` and `ADMIN_PASSWORD` to be set in `.env`.

For a production host, run the bot and panel as systemd services so they start
on boot and restart on crash — unit files are in [`linode/`](linode/). When
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
cogs/              slash commands grouped by domain (war, clan, links, admin, misc, reminders, recruit)
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

## Command Guide

Full usage docs for every command — war tracking, member scoring, account
links, reminders, and the recruiting system — live in a single self-contained
page at [`docs/index.html`](docs/index.html), hosted by GitHub Pages at
**<https://adiar1.github.io/Clash-Royale-Bot/>**.

Point the bot's `GUIDE_URL` at that address and the in-Discord `/info` command
links straight to it. The control panel's `/guide` route redirects there too,
so older links keep working.

In Discord, `/info` gives a short overview and the guide link, and typing `/`
lists every command with its own description and parameter hints.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This content is not affiliated with, endorsed, sponsored, or specifically approved by Supercell and Supercell is not responsible for it. For more information see Supercell's Fan Content Policy: www.supercell.com/fan-content-policy.
