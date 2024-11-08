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


async def handle_viewlinks_command(interaction: Interaction, someone_else: User = None):
    await interaction.response.defer()

    user = someone_else if someone_else else interaction.user
    user_id = str(user.id)
    player_tags = get_all_player_tags(user_id)

    if player_tags:
        embeds = []
        view = View()  # Create a view to hold buttons
        num_accounts = len(player_tags)  # Total number of accounts linked

        # Fetch data for all players once concurrently
        all_player_info = await asyncio.gather(*[fetch_player_data(tag) for tag in player_tags])

        # Create embeds with a maximum of 4 accounts each
        for i in range(0, num_accounts, 4):
            embed = discord.Embed(color=0x1E133E)
            embed.set_author(
                name=f"{user.display_name} ({user_id})",
                icon_url=user.avatar.url
            )
            embed.add_field(name="Username", value=user.name, inline=False)

            player_accounts = ""
            for index, (tag, result) in enumerate(zip(player_tags[i:i + 4], all_player_info[i:i + 4])):
                player_info, trophies, clan_info, clan_role = result
                player_name = player_info.get('name', 'Unknown')
                clan_name = clan_info.get('name', 'No Clan')
                clan_tag = clan_info.get('tag', '').replace('#', '')  # Remove # from clan tag

                # Capitalize role correctly
                clan_role = format_role(clan_role)

                # Account index (1, 2, 3, ...)
                account_index = i + index + 1  # Start counting from 1

                # Add player information with hyperlinks
                player_accounts += (
                    f"**{account_index}. [{player_name}](https://royaleapi.com/player/{tag})** #{tag}\n"
                    f"{EMOJI_TROPHYROAD} {trophies}\n"
                    f"{clan_role} of [{clan_name}](https://royaleapi.com/clan/{clan_tag})\n\n"
                )

            embed.add_field(
                name=f"Player Accounts ({num_accounts})",  # Total number of accounts
                value=player_accounts.strip(),
                inline=False
            )

            embeds.append(embed)

        # Pagination logic
        current_page = 0

        # Create the select dropdown with all player accounts
        select = Select(
            placeholder="Select an account to view more info",
            options=[
                discord.SelectOption(
                    label=f"{player_info.get('name', 'Unknown')} (#{tag})",
                    value=tag,
                )
                for i, (tag, (player_info, _, _, _)) in enumerate(zip(player_tags, all_player_info))
            ],
            max_values=1,
            min_values=1
        )

        # Set the dropdown callback to the run_player_command function
        select.callback = lambda interaction: run_player_command(interaction, select.values[0])
        view.add_item(select)  # Add dropdown to the view

        # Only add buttons if there are more than 4 accounts
        if num_accounts > 4:
            async def update_embed(interaction: Interaction, page_change: int):
                nonlocal current_page
                current_page += page_change
                current_page = max(0, min(current_page, len(embeds) - 1))

                # Update buttons state
                view.clear_items()  # Clear current buttons except the select dropdown
                view.add_item(select)  # Re-add the dropdown to the view

                # Previous button
                prev_button = Button(label="Previous", style=ButtonStyle.secondary, disabled=current_page == 0)
                prev_button.callback = lambda interaction: update_embed(interaction, -1)
                view.add_item(prev_button)

                # Next button
                next_button = Button(label="Next", style=ButtonStyle.secondary, disabled=current_page == len(embeds) - 1)
                next_button.callback = lambda interaction: update_embed(interaction, 1)
                view.add_item(next_button)

                # Show the current page's embed
                await interaction.response.edit_message(embed=embeds[current_page], view=view)

            # Add initial buttons
            prev_button = Button(label="Previous", style=ButtonStyle.secondary, disabled=True)
            prev_button.callback = lambda interaction: update_embed(interaction, -1)
            view.add_item(prev_button)

            if len(embeds) > 1:  # Only show next button if there is more than one page
                next_button = Button(label="Next", style=ButtonStyle.secondary, disabled=False)
                next_button.callback = lambda interaction: update_embed(interaction, 1)
                view.add_item(next_button)

        await interaction.followup.send(embed=embeds[current_page], view=view)
    else:
        await interaction.followup.send("No player tags linked.")

async def fetch_player_data(tag):
    """Fetch data for a specific player tag concurrently."""
    return await asyncio.gather(
        get_player_info(tag),
        get_player_trophies(tag),
        get_player_clan_info(tag),
        get_player_role(tag)
    )

def format_role(role):
    """Format the role correctly."""
    role = role.lower()
    if role == "coleader":
        return "Co-Leader"
    return role.capitalize()

async def run_player_command(interaction: Interaction, tag: str):
    """Execute the player command and display its output."""
    await handle_player_command(interaction, tag)