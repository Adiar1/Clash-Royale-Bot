import os
import logging

import discord
from dotenv import load_dotenv
from discord import Intents, app_commands, User, TextChannel
from discord.ext import commands

from commands.spyai import handle_clan_war_spy_command
from commands.stats import handle_stats_command
from commands.clan import handle_clan_command
from commands.editperms import handle_editperms_command
from commands.forcelink import handle_forcelink_command
from commands.nthwar import handle_nthwar_command
from commands.player import handle_player_command
from commands.link import handle_link_command
from commands.profile import handle_profile_command
from commands.currentwar import handle_currentwar_command
from commands.lastwar import handle_lastwar_command
from commands.members import handle_members_command
from commands.info import handle_info_command
from commands.nicklink import handle_nicklink_command
from commands.reminders import handle_reminders_command
from commands.viewmemberroles import handle_viewmemberroles_command
from commands.viewnicks import handle_viewnicks_command
from commands.rankings import handle_rankings_command
from commands.viewperms import handle_viewperms_command
from commands.whotokick import handle_whotokick_command
from commands.whotopromote import handle_whotopromote_command
from commands.wipelinks import handle_wipelinks_command
from utils.database import init_db
from commands.editmemberroles import handle_editmemberroles_command
from utils.helpers import is_privileged, get_privileged_roles
from commands.viewlinks import handle_viewlinks_command

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot setup
intents = Intents.default()
intents.message_content = True
intents.members = True  # Enable member tracking
bot = commands.Bot(command_prefix='/', intents=intents, disable_voice=True)


@bot.event
async def on_ready():
    print(f'{bot.user} is now running!')

    # Update bot status to show server and user count
    num_servers = len(bot.guilds)
    num_users = sum(guild.member_count for guild in bot.guilds)

    # Set the bot's activity to show server and user count
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name=f"{num_servers} server{'s' if num_servers != 1 else ''} | {num_users} users"
    )
    await bot.change_presence(activity=activity)

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

@bot.tree.command(name="nthwar", description="Get information about how current members of a clan performed n wars ago")
@app_commands.describe(clan_tag="The tag of the clan", n="Number of wars ago (1-10)")
async def nthwar(interaction, clan_tag: str, n: int):
    if not 1 <= n <= 10:
        await interaction.response.send_message("The war number must be between 1 and 10.", ephemeral=True)
        return
    await handle_nthwar_command(bot, interaction, f"/nthwar {clan_tag} {n}")

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
    deckai_id="Optional DeckAI ID to link",
    alt_account="Is this an alternate account?",

)
async def link(interaction, player_tag: str, alt_account: bool = False, deckai_id: str = None):
    await handle_link_command(interaction, player_tag, alt_account, deckai_id)

@bot.tree.command(name="profile", description="View all player tags linked to your Discord account or someone else's")
@app_commands.describe(someone_else="Mention another user to see their linked player tags")
async def profile(interaction, someone_else: User = None):
    await handle_profile_command(interaction, someone_else)

@bot.tree.command(name="viewnicks", description="View all clan nicknames in this server")
async def viewnicks(interaction):
    await handle_viewnicks_command(interaction)

@bot.tree.command(name="wipelinks", description="Remove specific player tags linked to your Discord account or someone else's")
@app_commands.describe(someone_else="Mention another user to remove their linked player tags")
async def wipelinks(interaction, someone_else: User = None):
    if await is_privileged(interaction):
        await handle_wipelinks_command(interaction, someone_else)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.tree.command(name="forcelink", description="Forcefully link a player tag to another user's Discord account")
@app_commands.describe(
    target_user="Mention the user to link the player tag to",
    player_tag="The tag of the player",
    deckai_id="Optional DeckAI ID to link",
    alt_account="Is this an alternate account?"
)
async def forcelink(interaction, target_user: User, player_tag: str, alt_account: bool = False, deckai_id: str = None):
    if await is_privileged(interaction):
        await handle_forcelink_command(interaction, target_user, player_tag, alt_account, deckai_id)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.tree.command(name="nicklink", description="Link a clan tag to a nickname or delete an existing nickname (leave nickname empty to delete)")
@app_commands.describe(
    clan_tag="The tag of the clan",
    nickname="The nickname to associate with the clan (leave empty to delete existing nickname)"
)
async def nicklink(interaction, clan_tag: str, nickname: str = None):
    if await is_privileged(interaction):
        await handle_nicklink_command(interaction, clan_tag, nickname)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.tree.command(name="reminders", description="Check current deck usage for a clan")
@app_commands.describe(
    channel="The channel to send the deck usage report in",
    clan_tag="The tag of the clan"
)
async def reminders(interaction: discord.Interaction, channel: TextChannel, clan_tag: str):
    if await is_privileged(interaction):
        await handle_reminders_command(interaction, channel, clan_tag)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.tree.command(name="rankings", description="List members' names, scores, and ranks")
@app_commands.describe(tourny_tag="The tag of the tournament")
async def rankings(interaction, tourny_tag: str):
    await handle_rankings_command(bot, interaction, f"/rankings {tourny_tag}")

@bot.tree.command(name="editperms", description="Edit privileged roles in this server")
async def editperms(interaction):
    await handle_editperms_command(bot, interaction)



@bot.tree.command(name="viewperms", description="View privileged roles in this server")
async def viewperms(interaction):
    await handle_viewperms_command(interaction)


@bot.tree.command(name="stats", description="Calculate individual stats over a range of wars")
@app_commands.describe(
    player_tag="The tag of the player",
    from_war="Starting from how many weeks ago (1-10)",
    to_war="Ending at how many weeks ago (1-10)"
)
async def stats(interaction, player_tag: str, from_war: int, to_war: int):
    await handle_stats_command(interaction, player_tag, from_war, to_war)

@bot.tree.command(name="clan", description="List current clan members and how many weeks ago they joined")
@app_commands.describe(clan_tag="The tag of the clan")
async def clan(interaction, clan_tag: str):
    await handle_clan_command(bot, interaction, f"/clan {clan_tag}")

@bot.tree.command(name="whotokick", description="Get recommendations for members to kick from the clan")
@app_commands.describe(
    clan_tag="Enter either a clan tag or a nickname",
    n="Number of members to list (1-24)",
    exclude_leadership="Exclude Co-Leaders and Leaders from kick recommendations"
)
async def whotokick(interaction, clan_tag: str, n: int = 5, exclude_leadership: bool = False):
    if not 1 <= n <= 24:
        await interaction.response.send_message("The number of members to list must be between 1 and 24.", ephemeral=True)
        return
    await handle_whotokick_command(bot, interaction, clan_tag, n, exclude_leadership)

@bot.tree.command(name="whotopromote", description="Get recommendations for members who might deserve a promotion")
@app_commands.describe(
    clan_tag="Enter either a clan tag or a nickname",
    n="Number of members to list (1-24)",
    exclude_leadership="Exclude Co-Leaders and Leaders from promotion recommendations"
)
async def whotopromote(interaction, clan_tag: str, n: int = 5, exclude_leadership: bool = False):
    if not 1 <= n <= 24:
        await interaction.response.send_message("The number of members to list must be between 1 and 24.", ephemeral=True)
        return
    await handle_whotopromote_command(bot, interaction, clan_tag, n, exclude_leadership)

@bot.tree.command(name="editmemberroles", description="Edit roles corresponding to Clash Royale positions")
async def editmemberroles(interaction):
    if await is_privileged(interaction):
        await handle_editmemberroles_command(bot, interaction)
    else:
        await interaction.response.send_message("You don't have permission to use this command.", ephemeral=True)

@bot.tree.command(name="viewmemberroles", description="View roles corresponding to Clash Royale positions")
async def viewmemberroles(interaction):
    await handle_viewmemberroles_command(interaction)


@bot.tree.command(name="viewlinks", description="List all players in a clan")
@app_commands.describe(clan_tag="Enter either a clan tag or nickname")
async def viewlinks(interaction, clan_tag: str):
    await handle_viewlinks_command(interaction, clan_tag)


@bot.tree.command(name="spy_ai", description="Get detailed info on opponent's clan war decks")
@app_commands.describe(
    opponent_player_tag="Enter the opponent's player tag",
    someone_else="Optionally mention another user whose DeckAI account to use"
)
async def clan_war_spy(
    interaction: discord.Interaction,
    opponent_player_tag: str,
    someone_else: User = None
):
    await handle_clan_war_spy_command(interaction, opponent_player_tag, someone_else)

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
