import asyncio
import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
import csv
import io
from utils.api import get_tournament_info
from utils.helpers import sanitize_tag

# Constants for better maintainability
DATA_ORDERS = {
    "score_name_rank": ["score", "name", "rank"],
    "score_rank_name": ["score", "rank", "name"],
    "name_score_rank": ["name", "score", "rank"],
    "name_rank_score": ["name", "rank", "score"],
    "rank_score_name": ["rank", "score", "name"],
    "rank_name_score": ["rank", "name", "score"]
}

SORT_FUNCTIONS = {
    "name_asc": lambda x: excel_like_sort_key(x[0]),
    "name_desc": lambda x: excel_like_sort_key(x[0]),
    "rank_asc": lambda x: x[2],
    "rank_desc": lambda x: x[2]
}

SORT_REVERSE = {
    "name_desc": True,
    "rank_desc": True
}


class BaseSelect(Select):

    def __init__(self, placeholder, options, command_type, handle_command, view):
        super().__init__(placeholder=placeholder, options=options)
        self.command_type = command_type
        self.handle_command = handle_command
        self._view = view

    async def _handle_callback(self, interaction, attribute_name):
        tourny_tag = interaction.message.embeds[0].title.split('#')[1]
        setattr(self._view, attribute_name, self.values[0])
        await self.handle_command(
            interaction.client,
            interaction,
            f"/{self.command_type} {tourny_tag}",
            arrange_listing_order=self._view.arrange_listing_order,
            arrange_data_order=self._view.arrange_data_order
        )


class SelectDataOrder(BaseSelect):
    OPTIONS = [
        SelectOption(label="Order: [Score - Name - Rank]", value="score_name_rank"),
        SelectOption(label="Order: [Score - Rank - Name]", value="score_rank_name"),
        SelectOption(label="Order: [Name - Score - Rank]", value="name_score_rank"),
        SelectOption(label="Order: [Name - Rank - Score]", value="name_rank_score"),
        SelectOption(label="Order: [Rank - Score - Name]", value="rank_score_name"),
        SelectOption(label="Order: [Rank - Name - Score]", value="rank_name_score"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__("Select Data Order", self.OPTIONS, command_type, handle_command, view)

    async def callback(self, interaction):
        await self._handle_callback(interaction, "arrange_data_order")


class SelectListingOrder(BaseSelect):
    OPTIONS = [
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Rank Ascending", value="rank_asc"),
        SelectOption(label="Sort by Rank Descending", value="rank_desc"),
    ]

    def __init__(self, command_type, handle_command, view):
        super().__init__("Select Listing Order", self.OPTIONS, command_type, handle_command, view)

    async def callback(self, interaction):
        await self._handle_callback(interaction, "arrange_listing_order")


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

        # Write CSV rows using list comprehension
        writer.writerows([
            [self._get_member_value(member, key) for key in self.order]
            for member in self.members_with_info
        ])

        buffer.seek(0)
        file = File(buffer, filename="tournament_rankings.csv")
        await interaction.response.send_message(file=file, ephemeral=True)

    def _get_member_value(self, member, key):
        value_map = {"score": 1, "rank": 2, "name": 0}
        return member[value_map.get(key, 0)]


async def handle_rankings_command(bot, interaction: Interaction, user_message: str,
                                  arrange_listing_order: str = "name_asc",
                                  arrange_data_order: str = "score_name_rank") -> None:
    try:
        parts = user_message.split()
        tourny_tag = sanitize_tag(parts[1])  # Use sanitize_tag helper

        await interaction.response.defer()

        # Create the embed with timeout
        embed, members_with_info, order = await asyncio.wait_for(
            format_tourny_rankings_embed(tourny_tag, arrange_listing_order, arrange_data_order),
            timeout=15
        )

        # Create view with components
        view = create_view(arrange_listing_order, arrange_data_order, members_with_info, order)
        await interaction.edit_original_response(embed=embed, view=view)

    except asyncio.TimeoutError:
        await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
    except IndexError:
        await interaction.followup.send("Invalid command format. Please provide a tournament tag.")
    except Exception as e:
        print(f"Error handling rankings command: {e}")
        await interaction.followup.send("An error occurred while processing your request.")


def create_view(arrange_listing_order, arrange_data_order, members_with_info, order):
    view = View()
    view.arrange_listing_order = arrange_listing_order
    view.arrange_data_order = arrange_data_order

    # Add components
    view.add_item(SelectListingOrder("rankings", handle_rankings_command, view))
    view.add_item(SelectDataOrder("rankings", handle_rankings_command, view))
    view.add_item(DownloadCSVButton(members_with_info, order))

    return view


def excel_like_sort_key(s):
    return ''.join(f"{ord(c):04}" for c in s.strip().lower())


def sort_members(members, arrange_listing_order):
    if arrange_listing_order not in SORT_FUNCTIONS:
        return members

    sort_key = SORT_FUNCTIONS[arrange_listing_order]
    reverse = SORT_REVERSE.get(arrange_listing_order, False)

    return sorted(members, key=sort_key, reverse=reverse)


def format_member_line(name, score, rank, order):
    value_map = {
        "score": str(score),
        "rank": str(rank),
        "name": f"`{name}`"
    }
    return " - ".join(value_map[key] for key in order)


def create_embed_description(members, order):
    header = " - ".join(key.capitalize() for key in order)
    member_lines = [format_member_line(name, score, rank, order) for name, score, rank in members]
    combined_text = "\n".join([header] + member_lines)

    # Truncate to fit within Discord's character limit
    if len(combined_text) > 4096:
        combined_text = combined_text[:4060] + "\n \n Download CSV to see more"

    return combined_text


async def format_tourny_rankings_embed(tourny_tag: str, arrange_listing_order: str,
                                       arrange_data_order: str) -> tuple[Embed, list, list]:
    # Get tournament data
    tournament_name, members = await get_tournament_info(tourny_tag)

    # Sort members
    sorted_members = sort_members(members, arrange_listing_order)

    # Get order configuration
    order = DATA_ORDERS.get(arrange_data_order, ["score", "name", "rank"])

    # Create embed description
    description = create_embed_description(sorted_members, order)

    # Create and return embed
    embed = Embed(
        title=f"{tournament_name} - Tournament #{tourny_tag}",
        description=description,
        color=0x1E133E
    )

    return embed, sorted_members, order