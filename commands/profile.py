import discord
from discord import Interaction, User, ButtonStyle
from discord.ui import Button, View, Select
from utils.api import (
    get_player_info,
    get_player_clan_info,
    get_player_role,
    get_player_trophies
)
import asyncio
from commands.player import handle_player_command
from utils.helpers import EMOJI_TROPHYROAD, get_all_player_tags
from typing import Optional, Tuple, Any


async def handle_profile_command(interaction: Interaction, someone_else: Optional[User] = None) -> None:
    await interaction.response.defer()

    user = someone_else if someone_else else interaction.user
    user_id = str(user.id)
    player_tags = get_all_player_tags(user_id)

    if not player_tags:
        await interaction.followup.send("No player tags linked.")
        return

    try:
        embeds = []
        view = View()
        num_accounts = len(player_tags)

        # Fetch data for all players concurrently
        all_player_info = await asyncio.gather(
            *[fetch_player_data(tag) for tag in player_tags],
            return_exceptions=True
        )

        # Check for API failures
        if all(isinstance(info, Exception) for info in all_player_info):
            await interaction.followup.send("Failed to fetch player data. Please try again later.")
            return

        # Create embeds with a maximum of 4 accounts each
        for i in range(0, num_accounts, 4):
            embed = create_embed(user, user_id, player_tags[i:i + 4], all_player_info[i:i + 4], i)
            if embed:
                embeds.append(embed)

        if not embeds:
            await interaction.followup.send("No player tags linked.")
            return

        # Create select menu
        select = create_select_menu(player_tags, all_player_info)
        view.add_item(select)

        # Add pagination if needed
        current_page = 0
        if num_accounts > 4:
            add_pagination_buttons(view, embeds, select)

        await interaction.followup.send(embed=embeds[current_page], view=view)

    except Exception as e:
        await interaction.followup.send(f"An error occurred while processing the command: {str(e)}")


async def fetch_player_data(tag: str) -> Tuple[Optional[dict], Optional[int], Optional[dict], Optional[str]]:
    """Fetch data for a specific player tag with error handling."""
    try:
        results = await asyncio.gather(
            get_player_info(tag),
            get_player_trophies(tag),
            get_player_clan_info(tag),
            get_player_role(tag),
            return_exceptions=True
        )

        # Convert exceptions to None
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                processed_results.append(None)
            else:
                processed_results.append(result)

        return tuple(processed_results)
    except Exception:
        return None, None, None, None


def create_embed(user: User, user_id: str, tags: list, player_info: list, start_index: int) -> Optional[discord.Embed]:
    """Create an embed for a set of player accounts."""
    try:
        embed = discord.Embed(color=0x1E133E)
        embed.set_author(
            name=f"{user.display_name} ({user_id})",
            icon_url=user.avatar.url if user.avatar else user.default_avatar.url
        )
        embed.add_field(name="Username", value=user.name, inline=False)

        player_accounts = ""
        for index, (tag, result) in enumerate(zip(tags, player_info)):
            if isinstance(result, tuple) and all(x is not None for x in result):
                player_info_dict, trophies, clan_info, clan_role = result

                player_name = player_info_dict.get('name', 'Unknown')
                clan_name = clan_info.get('name', 'No Clan')
                clan_tag = clan_info.get('tag', '').replace('#', '')

                account_index = start_index + index + 1
                player_accounts += format_player_account(
                    account_index, player_name, tag, trophies,
                    format_role(clan_role or 'Member'), clan_name, clan_tag
                )

        if player_accounts:
            embed.add_field(
                name=f"Player Accounts ({len(tags)})",
                value=player_accounts.strip(),
                inline=False
            )
            return embed
    except Exception:
        pass
    return None


def format_player_account(index: int, name: str, tag: str, trophies: int,
                          role: str, clan_name: str, clan_tag: str) -> str:
    """Format a single player account entry."""
    return (
        f"**{index}. [{name}](https://royaleapi.com/player/{tag})** #{tag}\n"
        f"{EMOJI_TROPHYROAD} {trophies}\n"
        f"{role} of [{clan_name}](https://royaleapi.com/clan/{clan_tag})\n\n"
    )


def create_select_menu(tags: list, player_info: list) -> Select:
    """Create a select menu for player accounts."""
    options = []
    for tag, info in zip(tags, player_info):
        if isinstance(info, tuple) and info[0] is not None:
            name = info[0].get('name', 'Unknown')
        else:
            name = 'Unknown'
        options.append(discord.SelectOption(
            label=f"{name} (#{tag})",
            value=tag
        ))

    select = Select(
        placeholder="Select an account to view more info",
        options=options,
        max_values=1,
        min_values=1
    )
    select.callback = lambda interaction: run_player_command(interaction, select.values[0])
    return select


def add_pagination_buttons(view: View, embeds: list, select: Select) -> None:
    """Add pagination buttons to the view."""
    current_page = 0

    async def update_embed(interaction: Interaction, page_change: int) -> None:
        nonlocal current_page
        current_page += page_change
        current_page = max(0, min(current_page, len(embeds) - 1))

        view.clear_items()
        view.add_item(select)

        prev_button = Button(
            label="Previous",
            style=ButtonStyle.secondary,
            disabled=current_page == 0
        )
        prev_button.callback = lambda i: update_embed(i, -1)
        view.add_item(prev_button)

        next_button = Button(
            label="Next",
            style=ButtonStyle.secondary,
            disabled=current_page == len(embeds) - 1
        )
        next_button.callback = lambda i: update_embed(i, 1)
        view.add_item(next_button)

        await interaction.response.edit_message(embed=embeds[current_page], view=view)

    # Add initial buttons
    prev_button = Button(label="Previous", style=ButtonStyle.secondary, disabled=True)
    prev_button.callback = lambda i: update_embed(i, -1)
    view.add_item(prev_button)

    if len(embeds) > 1:
        next_button = Button(label="Next", style=ButtonStyle.secondary, disabled=False)
        next_button.callback = lambda i: update_embed(i, 1)
        view.add_item(next_button)


def format_role(role: str) -> str:
    """Format the clan role correctly."""
    role = role.lower()
    if role == "coleader":
        return "Co-Leader"
    return role.capitalize()


async def run_player_command(interaction: Interaction, tag: str) -> None:
    """Execute the player command and display its output."""
    await handle_player_command(interaction, tag)