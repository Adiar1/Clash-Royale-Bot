import discord
from discord import Embed, Interaction, ButtonStyle
from utils.helpers import MULTIDECK_EMOJI, FAME_EMOJI, NEW_MEMBER_EMOJI, FORMER_MEMBER_EMOJI

async def handle_info_command(interaction: Interaction) -> None:
    embed = Embed(
        title="Clash Royale Clan Information Bot 🗣️🗣️🔥🔥🔥",
        description="Manage and track your clan's performance!",
        color=0x1E133E
    )

    embed.add_field(
        name="📊 Commands",
        value="""
- `/currentwar [clan_tag]` - Get current war stats. Customize order and download CSV!
- `/lastwar [clan_tag]` - Get last war stats. Customize order and download CSV!
- `/members [clan_tag]` - View the current members of a clan
- `/player [player_tag]` - View player stats and access their RoyaleAPI profile
- `/link [player_tag] [alt_account]` - Link a Clash Royale player tag to your Discord account
- `/profile [@user]` - View all player tags linked to a Discord account
- `/viewnicks` - View all nicknames linked to clans in this server
- `/wipelinks [@user]` - Remove specific player tags linked to an account
- `/forcelink [@user] [player_tag] [alt_account]` - Forcefully link a player tag to another user
- `/nicklink [clan_tag] [nickname]` - Link a clan tag to a nickname
- `/reminders [channel] [clan_tag]` - Check deck usage and send reminders in a specified channel
- `/info` - Show this guide
        """,
        inline=False
    )

    embed.add_field(
        name="🔄 Sorting Options",
        value="""
Use the dropdown menus to sort and order results:

War Commands (Current & Last):
- Sort by: Fame (Asc/Desc) / Name (A-Z/Z-A) / Decks Used (Asc/Desc)
- Order data: Fame / Name / Decks (in various combinations)

Members Command:
- Sort by: Name (A-Z/Z-A) / Tag (A-Z/Z-A) / Rank (Asc/Desc)
- Order data: Fame / Name / Decks (in various combinations)
        """,
        inline=False
    )

    embed.add_field(
        name="💡 Tips",
        value=f"""
- Clan tags are optional in commands
- Hashtag is optional in clan or player tags
- Tags are not case sensitive
- Fame earned is shown with {FAME_EMOJI}
- Decks used are shown with {MULTIDECK_EMOJI}
- Former members in war lists are marked with {FORMER_MEMBER_EMOJI}
- Members that have not participated in a war yet are marked with {NEW_MEMBER_EMOJI}
- Use clan nicknames instead of clan tag for all war commands
- Admins can use `/forcelink` to link a player tag to another user
- Use `/wipelinks` to remove specific player tags from an account
- Send reminders for deck usage with `/reminders` in the specified channel
        """,
        inline=False
    )

    embed.add_field(
        name="📥 Download CSV",
        value="Download a CSV file for data lists using appropriate buttons in the commands.",
        inline=False
    )

    embed.set_footer(
        text="For support or suggestions contact @adiar.",
        icon_url="https://cdn.discordapp.com/emojis/1259911930802343959.webp?size=96&quality=lossless"
    )

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Contact Developer",
        style=ButtonStyle.link,
        url="https://discord.com/users/880093108153495563"
    ))

    await interaction.response.send_message(embed=embed, view=view)
