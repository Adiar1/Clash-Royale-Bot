import os
import logging

import discord
from dotenv import load_dotenv
from discord import Intents, app_commands, User, TextChannel
from discord.ext import commands

from commands.forcelink import handle_forcelink_command
from commands.player import handle_player_command
from commands.link import handle_link_command
from commands.profile import handle_viewlinks_command
from commands.currentwar import handle_currentwar_command
from commands.lastwar import handle_lastwar_command
from commands.members import handle_members_command
from commands.info import handle_info_command
from commands.nicklink import handle_nicklink_command
from commands.reminders import handle_reminders_command
from commands.viewnicks import handle_viewnicks_command
from commands.rankings import handle_rankings_command
from commands.wipelinks import handle_wipelinks_command
from utils.database import init_db

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot setup
intents = Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} is now running!')
    await bot.tree.sync()

@bot.tree.command(name="currentwar",
                  description="Get information about how current members of a clan are performing this war")
@app_commands.describe(clan_tag="The tag of the clan")
async def currentwar(interaction, clan_tag: str):
    await handle_currentwar_command(bot, interaction, f"/currentwar {clan_tag}")

@bot.tree.command(name="lastwar", description="Get information about how current members of a clan performed last war")
@app_commands.describe(clan_tag="The tag of the clan")
async def lastwar(interaction, clan_tag: str):
    await handle_lastwar_command(bot, interaction, f"/lastwar {clan_tag}")

@bot.tree.command(name="members", description="Get information about the current members of a clan")
@app_commands.describe(clan_tag="The tag of the clan")
async def members(interaction, clan_tag: str):
    await handle_members_command(bot, interaction, f"/members {clan_tag}")

@bot.tree.command(name="info", description="Display information about the bot")
async def info(interaction):
    await handle_info_command(interaction)

@bot.tree.command(name="player", description="Get detailed information about a Clash Royale player")
@app_commands.describe(player_tag="The tag of the player")
async def player(interaction, player_tag: str):
    await handle_player_command(interaction, player_tag)

@bot.tree.command(name="link", description="Link, unlink, or update your Discord account with a Clash Royale player tag")
@app_commands.describe(
    player_tag="The tag of the player",
    alt_account="Is this an alternate account?"
)
async def link(interaction, player_tag: str, alt_account: bool = False):
    await handle_link_command(interaction, player_tag, alt_account)

@bot.tree.command(name="profile", description="View all player tags linked to your Discord account or someone else's")
@app_commands.describe(someone_else="Mention another user to see their linked player tags")
async def viewlinks(interaction, someone_else: User = None):
    await handle_viewlinks_command(interaction, someone_else)

@bot.tree.command(name="viewnicks", description="View all clan nicknames in this server")
async def viewnicks(interaction):
    await handle_viewnicks_command(interaction)

@bot.tree.command(name="wipelinks", description="Remove specific player tags linked to your Discord account or someone else's")
@app_commands.describe(someone_else="Mention another user to remove their linked player tags")
async def wipelinks(interaction, someone_else: User = None):
    await handle_wipelinks_command(interaction, someone_else)

@bot.tree.command(name="forcelink", description="Forcefully link a player tag to another user's Discord account")
@app_commands.describe(
    target_user="Mention the user to link the player tag to",
    player_tag="The tag of the player",
    alt_account="Is this an alternate account?"
)
async def forcelink(interaction, target_user: User, player_tag: str, alt_account: bool = False):
    await handle_forcelink_command(interaction, target_user, player_tag, alt_account)

@bot.tree.command(name="nicklink", description="Link a clan tag to a nickname")
@app_commands.describe(
    clan_tag="The tag of the clan",
    nickname="The nickname to associate with the clan"
)
async def nicklink(interaction, clan_tag: str, nickname: str):
    await handle_nicklink_command(interaction, clan_tag, nickname)

@bot.tree.command(name="reminders", description="Check current deck usage for a clan")
@app_commands.describe(
    channel="The channel to send the deck usage report in",
    clan_tag="The tag of the clan"
)
async def reminders(interaction: discord.Interaction, channel: TextChannel, clan_tag: str):
    await handle_reminders_command(interaction, channel, clan_tag)

@bot.tree.command(name="rankings", description="List members' names, scores, and ranks")
@app_commands.describe(tourny_tag="The tag of the tournament")
async def rankings(interaction, tourny_tag: str):
    await handle_rankings_command(bot, interaction, f"/rankings {tourny_tag}")

def main():
    load_dotenv()
    try:
        init_db()  # Initialize the database
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    TOKEN = os.getenv('DISCORD_TOKEN')

    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("DISCORD_TOKEN not found in environment variables.")

if __name__ == "__main__":
    main()