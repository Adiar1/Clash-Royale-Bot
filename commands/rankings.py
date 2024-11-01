import asyncio
import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
import aiohttp
import csv
import io
from utils.api import get_tournament_info

class SelectDataOrder(Select):
    OPTIONS = [
        SelectOption(label="Order: [Score - Name - Rank]", value="score_name_rank"),
        SelectOption(label="Order: [Score - Rank - Name]", value="score_rank_name"),
        SelectOption(label="Order: [Name - Score - Rank]", value="name_score_rank"),
        SelectOption(label="Order: [Name - Rank - Score]", value="name_rank_score"),
        SelectOption(label="Order: [Rank - Score - Name]", value="rank_score_name"),
        SelectOption(label="Order: [Rank - Name - Score]", value="rank_name_score"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self._view = view

    async def callback(self, interaction):
        tourny_tag = interaction.message.embeds[0].title.split('#')[1]
        self._view.arrange_data_order = self.values[0]
        await self.handle_command(
            interaction.client,
            interaction,
            f"/{self.command_type} {tourny_tag}",
            arrange_listing_order=self._view.arrange_listing_order,
            arrange_data_order=self._view.arrange_data_order
        )

class SelectListingOrder(Select):
    OPTIONS = [
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Rank Ascending", value="rank_asc"),
        SelectOption(label="Sort by Rank Descending", value="rank_desc"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self._view = view

    async def callback(self, interaction):
        tourny_tag = interaction.message.embeds[0].title.split('#')[1]
        self._view.arrange_listing_order = self.values[0]
        await self.handle_command(
            interaction.client,
            interaction,
            f"/{self.command_type} {tourny_tag}",
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
        file = File(buffer, filename="tourny_members.csv")

        await interaction.response.send_message(file=file, ephemeral=True)

    def get_member_value(self, member, key):
        if key == "score":
            return member[1]
        elif key == "rank":
            return member[2]
        elif key == "name":
            return member[0]
        else:
            return ""

async def handle_rankings_command(bot, interaction: Interaction, user_message: str,
                                  arrange_listing_order: str = "name_asc",
                                  arrange_data_order: str = "score_name_rank") -> None:
    parts = user_message.split()
    tourny_tag = parts[1].lstrip('#')

    try:
        await interaction.response.defer()

        timeout = 15
        try:
            embed, members_with_info, order = await asyncio.wait_for(
                format_tourny_rankings_embed(tourny_tag, arrange_listing_order, arrange_data_order),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
            return

        view = View()
        view.arrange_listing_order = arrange_listing_order
        view.arrange_data_order = arrange_data_order
        view.add_item(SelectListingOrder("rankings", handle_rankings_command, view))
        view.add_item(SelectDataOrder("rankings", handle_rankings_command, view))
        view.add_item(DownloadCSVButton(members_with_info, order))

        await interaction.edit_original_response(embed=embed, view=view)

    except Exception as e:
        print(f"Error handling rankings command: {e}")
        await interaction.response.send_message("An error occurred while processing your request.")

def excel_like_sort_key(s):
    return ''.join(f"{ord(c):04}" for c in s.strip().lower())

async def format_tourny_rankings_embed(tourny_tag: str, arrange_listing_order: str, arrange_data_order: str) -> (
        Embed, list, list):
    tournament_name, members = await get_tournament_info(tourny_tag)

    if arrange_listing_order == "name_asc":
        members.sort(key=lambda x: excel_like_sort_key(x[0]))
    elif arrange_listing_order == "name_desc":
        members.sort(key=lambda x: excel_like_sort_key(x[0]), reverse=True)
    elif arrange_listing_order == "rank_asc":
        members.sort(key=lambda x: x[2])
    elif arrange_listing_order == "rank_desc":
        members.sort(key=lambda x: x[2], reverse=True)

    def format_member_line(name, score, rank, order):
        formatted_line = []
        for key in order:
            if key == "score":
                formatted_line.append(f"{score}")
            elif key == "rank":
                formatted_line.append(f"{rank}")
            elif key == "name":
                formatted_line.append(f"`{name}`")
        return " - ".join(formatted_line)

    if arrange_data_order == "score_name_rank":
        order = ["score", "name", "rank"]
    elif arrange_data_order == "score_rank_name":
        order = ["score", "rank", "name"]
    elif arrange_data_order == "name_score_rank":
        order = ["name", "score", "rank"]
    elif arrange_data_order == "name_rank_score":
        order = ["name", "rank", "score"]
    elif arrange_data_order == "rank_score_name":
        order = ["rank", "score", "name"]
    elif arrange_data_order == "rank_name_score":
        order = ["rank", "name", "score"]
    else:
        order = ["score", "name", "rank"]

    member_lines = [
        format_member_line(name, score, rank, order)
        for name, score, rank in members
    ]

    header = " - ".join(key.capitalize() for key in order)
    combined_text = "\n".join([header] + member_lines)

    # Truncate to fit within Discord's character limit
    if len(combined_text) > 4096:
        combined_text = combined_text[:4060] + "\n \n Download CSV to see more"

    embed = Embed(title=f"{tournament_name} - Tournament #{tourny_tag}",
                  description=combined_text,
                  color=0x1E133E)
    return embed, members, order