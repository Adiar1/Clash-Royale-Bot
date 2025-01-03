import discord
from discord import Embed, Interaction, ButtonStyle
from utils.helpers import MULTIDECK_EMOJI, FAME_EMOJI, NEW_MEMBER_EMOJI, FORMER_MEMBER_EMOJI

async def handle_info_command(interaction: Interaction) -> None:
    embed = Embed(
        title="Clash Royale Clan Management Bot 🗣️🗣️🔥🔥🔥",
        description="Your ultimate tool for managing and tracking your Clash Royale clan's performance!",
        color=0x1E133E
    )

    embed.add_field(
        name="📊 War Commands",
        value="""
- `/currentwar [clan_tag]` - Get current war stats
- `/lastwar [clan_tag]` - Get last war stats
- `/nthwar [clan_tag] [n]` - Get stats from n wars ago (1-10)
        """,
        inline=False
    )

    embed.add_field(
        name="👥 Player & Clan Commands",
        value="""
- `/members [clan_tag]` - View current clan members
- `/player [player_tag]` - View detailed player stats
- `/clan [clan_tag]` - List clan members and join dates
- `/rankings [tourny_tag]` - List tournament rankings
- `/stats [player_tag] [from_war] [to_war]` - Calculate player stats over war range
        """,
        inline=False
    )

    embed.add_field(
        name="🔗 Account Linking",
        value="""
- `/link [player_tag] [alt_account]` - Link your account (non server specific)
- `/forcelink [@user] [player_tag] [alt_account]` - Force link an account (non server specific)
- `/profile [@user]` - View linked accounts
- `/wipelinks [@user]` - Remove linked accounts
        """,
        inline=False
    )

    embed.add_field(
        name="⚙️ Server Management",
        value="""
- `/nicklink [clan_tag] [nickname]` - Link clan tag to nickname (server specific)
- `/viewnicks` - View clan nicknames in this server
- `/reminders [channel] [clan_tag]` - Ping member with less than 4 decks used
- `/editperms` - Edit privileged roles (server specific)
- `/viewperms` - View privileged roles
- `/editmemberroles` - Edit roles for clan roles (server specific)
- `/viewmemberroles` - View roles for clan roles (server specific)
        """,
        inline=False
    )

    embed.add_field(
        name="📊 Advanced Features",
        value="""
- `/whotokick [clan_tag] [n]` - Get recommendations for kicking members (n is by default 5 but can be from 1 to 24)
- `/whotopromote [clan_tag] [n]` - Get recommendations for promoting members (n is by default 5 but can be from 1 to 24)
        """,
        inline=False
    )

    embed.add_field(
        name="🔄 Sorting & Customization",
        value="""
- Use dropdown menus to sort and order results in war and member commands
- Sort by: Fame, Name, Decks Used, Tag, Rank (options vary by command)
- Order data: Customize the display order of all data
        """,
        inline=False
    )

    embed.add_field(
        name="💡 Pro Tips",
        value=f"""
- Hashtags (#) are optional in clan or player tags
- Tags are not case-sensitive
- Use clan nicknames instead of tags for convenience
- Download CSV files for detailed data analysis
- {FAME_EMOJI} Fame earned | {MULTIDECK_EMOJI} Decks used
- {FORMER_MEMBER_EMOJI} Former members | {NEW_MEMBER_EMOJI} New members (joined after last war ended)
- Privileged commands require proper server permissions (All command can be used by anyone before permissions are set up with `/editperms`. Once privileges are set up, only those roles can use them)
        """,
        inline=False
    )

    adiar_user = await interaction.client.fetch_user(880093108153495563)

    embed.set_footer(
        text="For support or suggestions, contact @adiar.",
        icon_url=adiar_user.display_avatar.url
    )
    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="Contact Developer",
        style=ButtonStyle.link,
        url="https://discord.com/users/880093108153495563"
    ))

    await interaction.response.send_message(embed=embed, view=view)