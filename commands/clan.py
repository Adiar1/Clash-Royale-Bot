import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
from utils.api import get_weeks_ago_joined, get_average_fame_for_members, is_real_clan_tag
import io
import csv
from utils.helpers import FAME_EMOJI, get_clan_tag_by_nickname, sanitize_tag, get_discord_id_from_tag


class SelectDataOrder(Select):
    OPTIONS = [
        SelectOption(label="Order: [Name - Weeks - Fame]", value="name_weeks_fame"),
        SelectOption(label="Order: [Name - Fame - Weeks]", value="name_fame_weeks"),
        SelectOption(label="Order: [Weeks - Name - Fame]", value="weeks_name_fame"),
        SelectOption(label="Order: [Weeks - Fame - Name]", value="weeks_fame_name"),
        SelectOption(label="Order: [Fame - Name - Weeks]", value="fame_name_weeks"),
        SelectOption(label="Order: [Fame - Weeks - Name]", value="fame_weeks_name"),
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
            arrange_data_order=self._view.arrange_data_order,
            edit_mode=True
        )


class SelectListingOrder(Select):
    OPTIONS = [
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Oldest to Newest", value="oldest_newest"),
        SelectOption(label="Sort by Newest to Oldest", value="newest_oldest"),
        SelectOption(label="Sort by Fame Descending", value="fame_desc"),
        SelectOption(label="Sort by Fame Ascending", value="fame_asc"),
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
            arrange_data_order=self._view.arrange_data_order,
            edit_mode=True
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
        writer.writerow(["Player", "Weeks Joined", "Avg Fame"])

        # Write CSV rows
        for member in self.members_with_info:
            row = [self.get_member_value(member, key) for key in self.order]
            writer.writerow(row)

        buffer.seek(0)
        file = File(buffer, filename="clan_members.csv")

        await interaction.response.send_message(file=file, ephemeral=True)

    def get_member_value(self, member, key):
        if key == "name":
            return member[0]  # name
        elif key == "weeks":
            return member[1]  # weeks
        elif key == "fame":
            return member[2]  # fame
        else:
            return ""


async def handle_clan_command(bot, interaction: Interaction, user_message: str,
                              arrange_listing_order: str = "name_asc",
                              arrange_data_order: str = "name_weeks_fame",
                              edit_mode: bool = False) -> None:
    parts = user_message.split()
    input_value = parts[1].strip()

    if len(input_value) < 5:
        clan_tag = get_clan_tag_by_nickname(input_value.lower(), str(interaction.guild.id))
        if clan_tag is None:
            await interaction.response.send_message("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
            return
    else:
        clan_tag = sanitize_tag(input_value)

    if not await is_real_clan_tag(clan_tag):
        await interaction.response.send_message("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
        return

    try:
        if not edit_mode:
            await interaction.response.defer()

        # Fetch current clan members and their data
        member_weeks = await get_weeks_ago_joined(clan_tag)
        member_averages = await get_average_fame_for_members(clan_tag)

        # Create a dictionary to store averages by member name
        averages_dict = {name: avg for name, avg in member_averages}

        # Combine data into a list of tuples (now including discord_id)
        members_with_info = []
        for tag, name, weeks in member_weeks:
            discord_id = get_discord_id_from_tag(tag)  # Get the Discord ID if linked
            avg_fame = averages_dict.get(name, 0)
            members_with_info.append((name, weeks, avg_fame, discord_id))

        # Sorting logic based on arrange_listing_order
        if arrange_listing_order == "name_asc":
            members_with_info.sort(key=lambda x: x[0].lower())
        elif arrange_listing_order == "name_desc":
            members_with_info.sort(key=lambda x: x[0].lower(), reverse=True)
        elif arrange_listing_order == "oldest_newest":
            members_with_info.sort(key=lambda x: x[1])
        elif arrange_listing_order == "newest_oldest":
            members_with_info.sort(key=lambda x: x[1], reverse=True)
        elif arrange_listing_order == "fame_asc":
            members_with_info.sort(key=lambda x: x[2])
        elif arrange_listing_order == "fame_desc":
            members_with_info.sort(key=lambda x: x[2], reverse=True)

        # Data ordering logic
        def format_member_line(name, weeks, fame, order, discord_id=None):
            formatted_line = []
            for key in order:
                if key == "name":
                    # If we have a discord_id, show it as a silent mention
                    if discord_id:
                        # Ensure discord_id is a string and is numeric
                        discord_id_str = str(discord_id)
                        if discord_id_str.isdigit():
                            formatted_line.append(f"`{name}` <@{discord_id_str}>")
                        else:
                            # Invalid discord_id, just show the name
                            formatted_line.append(f"`{name}`")
                    else:
                        # No discord_id, just show the name
                        formatted_line.append(f"`{name}`")
                elif key == "weeks":
                    formatted_line.append(str(weeks))
                elif key == "fame":
                    formatted_line.append(f"{int(fame):,}")
            return " - ".join(formatted_line)

        if arrange_data_order == "name_weeks_fame":
            order = ["name", "weeks", "fame"]
        elif arrange_data_order == "name_fame_weeks":
            order = ["name", "fame", "weeks"]
        elif arrange_data_order == "weeks_name_fame":
            order = ["weeks", "name", "fame"]
        elif arrange_data_order == "weeks_fame_name":
            order = ["weeks", "fame", "name"]
        elif arrange_data_order == "fame_name_weeks":
            order = ["fame", "name", "weeks"]
        elif arrange_data_order == "fame_weeks_name":
            order = ["fame", "weeks", "name"]
        else:
            order = ["name", "weeks", "fame"]

        # Add headers
        headers = {
            "name": "Player",
            "weeks": "Weeks Ago Joined",
            "fame": f"Avg {FAME_EMOJI}"
        }
        header_line = " - ".join(headers[key] for key in order)

        member_lines = [
            format_member_line(name, weeks, fame, order, discord_id)
            for name, weeks, fame, discord_id in members_with_info
        ]

        # Create embed message
        embed = Embed(title=f"Average Fame and Weeks Ago Joined Members of Clan #{clan_tag}", color=0x1E133E)
        embed.description = f"{header_line}\n" + "\n".join(member_lines)
        embed.set_footer(
            text=f"Average fame is calculated individually for each member throughout that member's time with the clan. Maximum memory of 10 weeks")
        if len(embed.description) > 4000:
            embed.description = embed.description[:3997] + "..."

        # Create view with interactive components
        view = View()
        view.arrange_listing_order = arrange_listing_order
        view.arrange_data_order = arrange_data_order
        view.add_item(SelectListingOrder("clan", handle_clan_command, view))
        view.add_item(SelectDataOrder("clan", handle_clan_command, view))
        view.add_item(DownloadCSVButton(members_with_info, order))

        if edit_mode:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        print(f"Error handling clan command: {e}")
        await interaction.followup.send("An error occurred while processing your request.")