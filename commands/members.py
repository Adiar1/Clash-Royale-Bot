import discord
from discord import Interaction, Embed, SelectOption, File
from discord.ui import View, Select, Button
import csv
import io
import asyncio
from utils.api import get_current_clan_members, get_role, is_new_player, get_former_clan_members, is_real_clan_tag
from utils.database import get_clan_tag_by_nickname
from utils.helpers import NEW_MEMBER_EMOJI

class SelectListingOrder(Select):
    OPTIONS = [
        SelectOption(label="Sort Name A-Z", value="name_asc"),
        SelectOption(label="Sort Name Z-A", value="name_desc"),
        SelectOption(label="Sort Tag A-Z", value="tag_asc"),
        SelectOption(label="Sort Tag Z-A", value="tag_desc"),
        SelectOption(label="Sort by Rank Descending", value="role_desc"),
        SelectOption(label="Sort by Rank Ascending", value="role_asc"),
    ]

    def __init__(self, command_type, handle_command, clan_tag, sort_by, order_by):
        super().__init__(placeholder="Select Listing Order", min_values=1, max_values=1, options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self.clan_tag = clan_tag
        self.sort_by = sort_by
        self.order_by = order_by

    async def callback(self, interaction: Interaction):
        self.sort_by = self.values[0]
        await self.handle_command(interaction.client, interaction, f"/members #{self.clan_tag}", self.sort_by, self.order_by)

class SelectDataOrder(Select):
    OPTIONS = [
        SelectOption(label="Order: [Tag, Name, Rank]", value="tag_name_role"),
        SelectOption(label="Order: [Tag, Rank, Name]", value="tag_role_name"),
        SelectOption(label="Order: [Name, Tag, Rank]", value="name_tag_role"),
        SelectOption(label="Order: [Name, Rank, Tag]", value="name_role_tag"),
        SelectOption(label="Order: [Rank, Tag, Name]", value="role_tag_name"),
        SelectOption(label="Order: [Rank, Name, Tag]", value="role_name_tag"),
    ]

    def __init__(self, command_type, handle_command, clan_tag, sort_by, order_by):
        super().__init__(placeholder="Select Data Order", min_values=1, max_values=1, options=self.OPTIONS)
        self.command_type = command_type
        self.handle_command = handle_command
        self.clan_tag = clan_tag
        self.sort_by = sort_by
        self.order_by = order_by

    async def callback(self, interaction: Interaction):
        self.order_by = self.values[0]
        await self.handle_command(interaction.client, interaction, f"/members #{self.clan_tag}", self.sort_by, self.order_by)

class DownloadCSVButton(Button):
    def __init__(self, clan_tag, sort_by, order_by):
        super().__init__(label="Download CSV", style=discord.ButtonStyle.primary)
        self.clan_tag = clan_tag
        self.sort_by = sort_by
        self.order_by = order_by

    async def callback(self, interaction: Interaction):
        await generate_and_send_csv(interaction, self.clan_tag, self.sort_by, self.order_by)

class ToggleMemberViewButton(Button):
    def __init__(self, clan_tag, sort_by, order_by):
        super().__init__(label="View: All Members", style=discord.ButtonStyle.secondary)
        self.clan_tag = clan_tag
        self.sort_by = sort_by
        self.order_by = order_by
        self.view_mode = "all"

    async def callback(self, interaction: Interaction):
        if self.view_mode == "all":
            self.view_mode = "new"
            self.label = "View: Only New Members"
            text = "New members:"
        elif self.view_mode == "new":
            self.view_mode = "former"
            self.label = "View: Only Former Members"
            text = "Former members:"
        elif self.view_mode == "former":
            self.view_mode = "none"
            self.label = "View: No New Members"
            text = "Everyone but the new members:"
        else:
            self.view_mode = "all"
            self.label = "View: All Members"
            text = "Members:"

        embed = await format_clan_members_embed(self.clan_tag, self.sort_by, self.order_by, self.view_mode, text)
        await interaction.response.edit_message(embed=embed, view=self.view)

async def handle_members_command(client, interaction: Interaction, user_message: str, sort_by: str = "name_asc", order_by: str = "name_tag_role") -> None:
    parts = user_message.split()
    input_value = parts[1].lstrip('#')

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
        if not interaction.response.is_done():
            await interaction.response.defer()

        embed = await format_clan_members_embed(clan_tag, sort_by, order_by, "all", "Members:")

        view = View()
        view.add_item(SelectListingOrder("members", handle_members_command, clan_tag, sort_by, order_by))
        view.add_item(SelectDataOrder("members", handle_members_command, clan_tag, sort_by, order_by))
        view.add_item(DownloadCSVButton(clan_tag, sort_by, order_by))
        view.add_item(ToggleMemberViewButton(clan_tag, sort_by, order_by))

        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        print(f"Error handling members command: {e}")
        error_message = f"An error occurred while processing your request: {str(e)}"
        if interaction.response.is_done():
            await interaction.edit_original_response(content=error_message)
        else:
            await interaction.followup.send(content=error_message)

async def format_clan_members_embed(clan_tag: str, sort_by: str, order_by: str, view_mode: str, text: str) -> Embed:
    if view_mode == "former":
        members = await get_former_clan_members(clan_tag)
        members_with_status = [(tag, name, "former", False) for tag, name in members]
        clan_name = "Former Members"
    else:
        clan_name, members = await get_current_clan_members(clan_tag)

        tasks = [
            fetch_member_details(clan_tag, tag, name)
            for tag, name in members
        ]
        members_with_status = await asyncio.gather(*tasks)

        if view_mode == "new":
            members_with_status = [m for m in members_with_status if m[3]]
        elif view_mode == "none":
            members_with_status = [m for m in members_with_status if not m[3]]

    role_order = {"leader": 4, "coLeader": 3, "elder": 2, "member": 1, "former": 0}

    if sort_by == "tag_asc":
        members_with_status.sort(key=lambda x: x[0])
    elif sort_by == "tag_desc":
        members_with_status.sort(key=lambda x: x[0], reverse=True)
    elif sort_by == "name_asc":
        members_with_status.sort(key=lambda x: x[1])
    elif sort_by == "name_desc":
        members_with_status.sort(key=lambda x: x[1], reverse=True)
    elif sort_by == "role_desc":
        members_with_status.sort(key=lambda x: (role_order.get(x[2], 5), not x[3], x[1]), reverse=True)
    elif sort_by == "role_asc":
        members_with_status.sort(key=lambda x: (not x[3], role_order.get(x[2], 5), x[1]))

    header = format_header(order_by)

    member_lines = [
        f"{format_member_line(tag, name, role, new_status, order_by)}"
        for tag, name, role, new_status in members_with_status
    ]

    member_count = len(members_with_status)

    description = f"** {text} {member_count}**\n\n{header}\n" + "\n".join(member_lines)

    embed = Embed(title=f"Members of {clan_name} #{clan_tag}", color=0x1E133E)
    embed.description = description
    return embed

async def fetch_member_details(clan_tag: str, tag: str, name: str):
    role = await get_role(clan_tag, tag)
    new_status = await is_new_player(clan_tag, tag)
    return tag, name, role, new_status

def format_header(order_by: str) -> str:
    if order_by == "tag_name_role":
        return "Tag - Name - Rank"
    elif order_by == "tag_role_name":
        return "Tag - Rank - Name"
    elif order_by == "name_tag_role":
        return "Name - Tag - Rank"
    elif order_by == "name_role_tag":
        return "Name - Rank - Tag"
    elif order_by == "role_tag_name":
        return "Rank - Tag - Name"
    elif order_by == "role_name_tag":
        return "Rank - Name - Tag"

def format_member_line(tag: str, name: str, role: str, new_status: bool, order_by: str) -> str:
    role_display_map = {
        "member": "Member",
        "elder": "Elder",
        "leader": "Leader",
        "coLeader": "Co-leader",
        "former": "Former Member"
    }

    role_display = role_display_map.get(role, role)

    line = {
        "tag_name_role": f"{tag} - `{name}`{NEW_MEMBER_EMOJI if new_status else ''} - {role_display}".strip(),
        "tag_role_name": f"{tag} - {role_display} - `{name}`{NEW_MEMBER_EMOJI if new_status else ''}".strip(),
        "name_tag_role": f"`{name}`{NEW_MEMBER_EMOJI if new_status else ''} - {tag} - {role_display}".strip(),
        "name_role_tag": f"`{name}`{NEW_MEMBER_EMOJI if new_status else ''} - {role_display} - {tag}".strip(),
        "role_tag_name": f"{role_display} - {tag} - `{name}`{NEW_MEMBER_EMOJI if new_status else ''}".strip(),
        "role_name_tag": f"{role_display} - `{name}`{NEW_MEMBER_EMOJI if new_status else ''} - {tag}".strip(),
    }

    return line.get(order_by, "")

async def generate_and_send_csv(interaction: Interaction, clan_tag: str, sort_by: str, order_by: str):
    clan_name, members = await get_current_clan_members(clan_tag)

    tasks = [
        fetch_member_details(clan_tag, tag, name)
        for tag, name in members
    ]
    members_with_status = await asyncio.gather(*tasks)

    role_order = {"leader": 4, "coLeader": 3, "elder": 2, "member": 1}

    if sort_by == "tag_asc":
        members_with_status.sort(key=lambda x: x[0])
    elif sort_by == "tag_desc":
        members_with_status.sort(key=lambda x: x[0], reverse=True)
    elif sort_by == "name_asc":
        members_with_status.sort(key=lambda x: x[1])
    elif sort_by == "name_desc":
        members_with_status.sort(key=lambda x: x[1], reverse=True)
    elif sort_by == "role_desc":
        members_with_status.sort(key=lambda x: (role_order.get(x[2], 5), not x[3], x[1]), reverse=True)
    elif sort_by == "role_asc":
        members_with_status.sort(key=lambda x: (not x[3], role_order.get(x[2], 5), x[1]))

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Tag", "Name", "Rank", "New Member"])
    for tag, name, role, new_status in members_with_status:
        writer.writerow([tag, name, role, "Yes" if new_status else "No"])

    buffer.seek(0)
    file = File(buffer, filename=f"{clan_name}_members.csv")

    await interaction.response.send_message("Here is the CSV file with the members data:", file=file)