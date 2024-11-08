import asyncio
import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
import aiohttp
import csv
import io

from commands.lastwar import excel_like_sort_key
from utils.api import get_current_clan_members, get_former_clan_members, is_new_player, get_fame_n_wars_ago, \
    get_decks_used_n_wars_ago, is_real_clan_tag
from utils.helpers import FAME_EMOJI, NEW_MEMBER_EMOJI, MULTIDECK_EMOJI, FORMER_MEMBER_EMOJI, get_clan_tag_by_nickname


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
            f"/{self.command_type} {clan_tag} {self._view.n}",
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
            f"/{self.command_type} {clan_tag} {self._view.n}",
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

async def handle_nthwar_command(bot, interaction: Interaction, user_message: str,
                                arrange_listing_order: str = "tag_asc",
                                arrange_data_order: str = "fame_name_decks") -> None:
    parts = user_message.split()
    input_value = parts[1].lstrip('#')
    n = int(parts[2])

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
                format_clan_members_embed(clan_tag, arrange_listing_order, arrange_data_order,
                                          lambda ct, pt: get_fame_n_wars_ago(ct, pt, n),
                                          lambda ct, pt: get_decks_used_n_wars_ago(ct, pt, n),
                                          n),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
            return

        view = View()
        view.arrange_listing_order = arrange_listing_order
        view.arrange_data_order = arrange_data_order
        view.n = n
        view.add_item(SelectListingOrder("nthwar", handle_nthwar_command, view))
        view.add_item(SelectDataOrder("nthwar", handle_nthwar_command, view))
        view.add_item(DownloadCSVButton(members_with_info, order))

        await interaction.edit_original_response(embed=embed, view=view)

    except Exception as e:
        print(f"Error handling nthwar command: {e}")
        await interaction.response.send_message("An error occurred while processing your request.")


async def format_clan_members_embed(clan_tag: str, arrange_listing_order: str, arrange_data_order: str, fame_func,
                                    decks_func, n: int) -> (Embed, list, list):
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

            if not (decks_used == 0 and is_former):
                members_with_info.append((tag, name, fame, decks_used, new_status, is_former))

    # Sorting logic
    sorting_key = {
        "decks_asc": lambda x: x[3],
        "decks_desc": lambda x: x[3],
        "name_asc": lambda x: excel_like_sort_key(x[1]),
        "name_desc": lambda x: excel_like_sort_key(x[1]),
        "fame_asc": lambda x: int(x[2]),
        "fame_desc": lambda x: int(x[2]),
        "tag_asc": lambda x: excel_like_sort_key(x[0]),
        "tag_desc": lambda x: excel_like_sort_key(x[0]),
    }

    reverse_order = arrange_listing_order.endswith("desc")
    members_with_info.sort(key=sorting_key[arrange_listing_order], reverse=reverse_order)

    # Format the data
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

    order_map = {
        "fame_name_decks": ["fame", "name", "decks"],
        "fame_decks_name": ["fame", "decks", "name"],
        "name_fame_decks": ["name", "fame", "decks"],
        "name_decks_fame": ["name", "decks", "fame"],
        "decks_fame_name": ["decks", "fame", "name"],
        "decks_name_fame": ["decks", "name", "fame"],
    }
    order = order_map.get(arrange_data_order, ["fame", "name", "decks"])

    member_lines = [
        format_member_line(tag, name, fame, decks_used, new_status, is_former, order)
        for tag, name, fame, decks_used, new_status, is_former in members_with_info
    ]

    header = " - ".join(
        FAME_EMOJI if key == "fame" else MULTIDECK_EMOJI if key == "decks" else "Player"
        for key in order
    )

    # Create Embed
    embed = Embed(title=f"Fame Earned and Decks Used {n} Wars Ago by Members of {active_clan_name} #{clan_tag}",
                  color=0x1E133E)
    description = "\n".join([header] + member_lines)

    # Truncate description if necessary
    if len(description) > 4096:
        description = description[:4093] + "..."

    embed.description = description
    embed.set_footer(
        text=f"{FORMER_MEMBER_EMOJI} Indicates a former member \n{NEW_MEMBER_EMOJI} Indicates a member who joined after"
             f" last war ended")

    return embed, members_with_info, order