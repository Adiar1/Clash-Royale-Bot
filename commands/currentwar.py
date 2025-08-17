import asyncio
import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
import aiohttp
import csv
import io

from commands.lastwar import excel_like_sort_key
from utils.api import get_current_clan_members, get_former_clan_members, is_new_player, get_current_fame, \
    get_members_current_decks_used, is_real_clan_tag
from utils.helpers import FAME_EMOJI, NEW_MEMBER_EMOJI, MULTIDECK_EMOJI, FORMER_MEMBER_EMOJI, get_clan_tag_by_nickname, \
    sanitize_tag


class SelectDataOrder(Select):
    OPTIONS = [
        SelectOption(label="Order: [Fame - Name - Decks]", value="fame_name_decks"),
        SelectOption(label="Order: [Fame - Decks - Name]", value="fame_decks_name"),
        SelectOption(label="Order: [Name - Fame - Decks]", value="name_fame_decks"),
        SelectOption(label="Order: [Name - Decks - Fame]", value="name_decks_fame"),
        SelectOption(label="Order: [Decks - Fame - Name]", value="decks_fame_name"),
        SelectOption(label="Order: [Decks - Name - Fame]", value="decks_name_fame"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self._view = view

    async def callback(self, interaction):
        clan_tag = interaction.message.embeds[0].title.split('#')[1]
        self._view.arrange_data_order = self.values[0]
        await self.handle_command(
            interaction.client,
            interaction,
            f"/{self.command_type} {clan_tag}",
            arrange_listing_order=self._view.arrange_listing_order,
            arrange_data_order=self._view.arrange_data_order
        )

class SelectListingOrder(Select):
    OPTIONS = [
        SelectOption(label="Sort by Fame Ascending", value="fame_asc"),
        SelectOption(label="Sort by Fame Descending", value="fame_desc"),
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Decks Used Ascending", value="decks_asc"),
        SelectOption(label="Sort by Decks Used Descending", value="decks_desc"),
        SelectOption(label="Sort by Tag A-Z", value="tag_asc"),
        SelectOption(label="Sort by Tag Z-A", value="tag_desc"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self._view = view

    async def callback(self, interaction):
        clan_tag = interaction.message.embeds[0].title.split('#')[1]
        self._view.arrange_listing_order = self.values[0]
        await self.handle_command(
            interaction.client,
            interaction,
            f"/{self.command_type} {clan_tag}",
            arrange_listing_order=self._view.arrange_listing_order,
            arrange_data_order=self._view.arrange_data_order
        )

class DownloadCSVButton(Button):
    def __init__(self, members_with_info, order):
        super().__init__(label="Download CSV", style=discord.ButtonStyle.primary)
        self.members_with_info = members_with_info
        self.order = order

    async def callback(self, interaction):
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        # Write CSV header
        writer.writerow(self.order)

        # Write CSV rows
        for member in self.members_with_info:
            row = [self.get_member_value(member, key) for key in self.order]
            writer.writerow(row)

        buffer.seek(0)
        file = File(buffer, filename="clan_members.csv")

        await interaction.response.send_message(file=file, ephemeral=True)

    def get_member_value(self, member, key):
        if key == "fame":
            return member[2]
        elif key == "decks":
            return member[3]
        elif key == "name":
            return member[1]
        else:
            return ""

async def handle_currentwar_command(bot, interaction: Interaction, user_message: str,
                                    arrange_listing_order: str = "tag_asc",
                                    arrange_data_order: str = "fame_name_decks") -> None:
    parts = user_message.split()
    input_value = sanitize_tag(parts[1])


    if len(input_value) < 5:
        clan_tag = get_clan_tag_by_nickname(input_value, interaction.guild.id)
        if clan_tag is None:
            await interaction.response.send_message("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
            return
    else:
        clan_tag = input_value

    if not await is_real_clan_tag(clan_tag):
        await interaction.response.send_message("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
        return

    try:
        await interaction.response.defer()

        timeout = 15
        try:
            embed, members_with_info, order = await asyncio.wait_for(
                format_clan_members_embed(clan_tag, arrange_listing_order, arrange_data_order, get_current_fame,
                                          get_members_current_decks_used),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
            return

        view = View()
        view.arrange_listing_order = arrange_listing_order
        view.arrange_data_order = arrange_data_order
        view.add_item(SelectListingOrder("currentwar", handle_currentwar_command, view))
        view.add_item(SelectDataOrder("currentwar", handle_currentwar_command, view))
        view.add_item(DownloadCSVButton(members_with_info, order))

        await interaction.edit_original_response(embed=embed, view=view)

    except Exception as e:
        print(f"Error handling currentwar command: {e}")
        await interaction.response.send_message("An error occurred while processing your request.")

async def format_clan_members_embed(clan_tag: str, arrange_listing_order: str, arrange_data_order: str, fame_func,
                                    decks_func) -> (Embed, list, list):
    active_clan_name, active_members = await get_current_clan_members(clan_tag)
    former_members = await get_former_clan_members(clan_tag)
    members = active_members + former_members

    members_with_info = []
    async with aiohttp.ClientSession() as session:
        for tag, name in members:
            fame = await fame_func(clan_tag, tag)
            decks_used = await decks_func(clan_tag, tag)
            new_status = await is_new_player(clan_tag, tag)
            is_former = (tag, name) in former_members

            # Exclude members who used 0 decks and are former members
            if not (decks_used == 0 and is_former):
                members_with_info.append((tag, name, fame, decks_used, new_status, is_former))

    # Sorting logic based on arrange_listing_order value
    if arrange_listing_order == "decks_asc":
        members_with_info.sort(key=lambda x: x[3])
    elif arrange_listing_order == "decks_desc":
        members_with_info.sort(key=lambda x: x[3], reverse=True)
    elif arrange_listing_order == "name_asc":
        members_with_info.sort(key=lambda x: excel_like_sort_key(x[1]))
    elif arrange_listing_order == "name_desc":
        members_with_info.sort(key=lambda x: excel_like_sort_key(x[1]), reverse=True)
    elif arrange_listing_order == "fame_asc":
        members_with_info.sort(key=lambda x: int(x[2]))
    elif arrange_listing_order == "fame_desc":
        members_with_info.sort(key=lambda x: int(x[2]), reverse=True)
    elif arrange_listing_order == "tag_asc":
        members_with_info.sort(key=lambda x: excel_like_sort_key(x[0]))
    elif arrange_listing_order == "tag_desc":
        members_with_info.sort(key=lambda x: excel_like_sort_key(x[0]), reverse=True)

    # Data ordering logic
    def format_member_line(tag, name, fame, decks_used, new_status, is_former, order):
        formatted_line = []
        for key in order:
            if key == "fame":
                formatted_line.append(f"{fame}")
            elif key == "decks":
                formatted_line.append(f"{decks_used}")
            elif key == "name":
                formatted_line.append(
                    f"`{name}`{FORMER_MEMBER_EMOJI if is_former else ''}{' ' + NEW_MEMBER_EMOJI if new_status else ''}")
        return " - ".join(formatted_line)

    if arrange_data_order == "fame_name_decks":
        order = ["fame", "name", "decks"]
    elif arrange_data_order == "fame_decks_name":
        order = ["fame", "decks", "name"]
    elif arrange_data_order == "name_fame_decks":
        order = ["name", "fame", "decks"]
    elif arrange_data_order == "name_decks_fame":
        order = ["name", "decks", "fame"]
    elif arrange_data_order == "decks_fame_name":
        order = ["decks", "fame", "name"]
    elif arrange_data_order == "decks_name_fame":
        order = ["decks", "name", "fame"]
    else:
        order = ["fame", "name", "decks"]

    member_lines = [
        format_member_line(tag, name, fame, decks_used, new_status, is_former, order)
        for tag, name, fame, decks_used, new_status, is_former in members_with_info
    ]

    header = " - ".join(
        FAME_EMOJI if key == "fame" else MULTIDECK_EMOJI if key == "decks" else "Player"
        for key in order
    )
    embed = Embed(title=f"Fame Earned and Decks Used in Current War by Members of {active_clan_name} #{clan_tag}",
                  color=0x1E133E)
    embed.description = "\n".join([header] + member_lines)
    embed.set_footer(
        text=f"{FORMER_MEMBER_EMOJI} Indicates a former member \n{NEW_MEMBER_EMOJI} Indicates a member who joined after"
             f" last war ended")
    return embed, members_with_info, order