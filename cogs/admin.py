import math

import discord
from discord import Interaction, TextChannel, app_commands
from discord.ext import commands
from prettytable import PrettyTable

from cogs.checks import is_privileged
from cogs.resolvers import resolve_clan_tag
from errors import BotError
from services.clash_royale import race_participants
from ui.embeds import make_embed

DISCORD_MESSAGE_LIMIT = 1800

MEMBER_POSITIONS = ("Member", "Elder", "Co-Leader")


# ---- /editperms ----

class PrivilegedRoleSelect(discord.ui.Select):
    def __init__(self, roles: list[discord.Role], page: int):
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles[page * 25:(page + 1) * 25]
        ]
        super().__init__(
            placeholder=f"Select roles (Page {page + 1})",
            options=options,
            min_values=1,
            max_values=len(options),
        )

    async def callback(self, interaction: Interaction):
        # Toggle: selected roles flip in/out of the current privileged set.
        current = set(self.view.current_role_ids)
        updated = current ^ {int(v) for v in self.values}
        await interaction.client.repo.set_privileged_roles(interaction.guild.id, sorted(updated))

        mentions = [
            interaction.guild.get_role(role_id).mention
            for role_id in updated
            if interaction.guild.get_role(role_id)
        ]
        embed = discord.Embed(
            title="Success",
            description=f"Privileged roles updated: {', '.join(mentions) or 'No roles changed'}",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


class RolePaginationView(discord.ui.View):
    def __init__(self, roles: list[discord.Role], current_role_ids: list[int]):
        super().__init__(timeout=120)
        self.roles = roles
        self.current_role_ids = current_role_ids
        self.page = 0
        self.max_pages = max(1, min(math.ceil(len(roles) / 25), 10))
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        self.add_item(PrivilegedRoleSelect(self.roles, self.page))
        prev_button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary,
                                        disabled=self.page == 0)
        next_button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary,
                                        disabled=self.page >= self.max_pages - 1)
        prev_button.callback = self._make_pager(-1)
        next_button.callback = self._make_pager(1)
        self.add_item(prev_button)
        self.add_item(next_button)

    def _make_pager(self, delta: int):
        async def pager(interaction: Interaction):
            self.page = max(0, min(self.page + delta, self.max_pages - 1))
            self._rebuild()
            await interaction.response.edit_message(view=self)
        return pager


# ---- /editmemberroles ----

class PositionRoleSelect(discord.ui.Select):
    def __init__(self, position: str, roles: list[discord.Role], page: int):
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles[page * 25:(page + 1) * 25]
        ]
        super().__init__(placeholder=f"Select {position} role (Page {page + 1})", options=options)
        self.position = position

    async def callback(self, interaction: Interaction):
        role = interaction.guild.get_role(int(self.values[0]))
        if role is None:
            embed = discord.Embed(title="Error", description="Invalid role selected", color=discord.Color.red())
            await interaction.response.edit_message(embed=embed, view=None)
            return

        position_key = self.position.lower().replace("-", "")  # 'Co-Leader' -> 'coleader'
        await interaction.client.repo.set_member_role(interaction.guild.id, position_key, role.id)
        embed = discord.Embed(
            title="Success",
            description=f"{self.position} role updated to {role.mention}",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)


class PositionButton(discord.ui.Button):
    def __init__(self, position: str, position_views: dict[str, discord.ui.View]):
        super().__init__(label=position, style=discord.ButtonStyle.primary)
        self.position = position
        self.position_views = position_views

    async def callback(self, interaction: Interaction):
        embed = make_embed(f"Edit {self.position} Role", f"Select the role to assign to {self.position}s.")
        await interaction.response.edit_message(embed=embed, view=self.position_views[self.position])


class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="editperms", description="Edit privileged roles in this server")
    @is_privileged()
    async def editperms(self, interaction: Interaction):
        current_role_ids = await self.bot.repo.privileged_role_ids(interaction.guild.id)

        embed = make_embed("Edit Privileged Roles", "Add/remove privileged roles.")
        mentions = [
            interaction.guild.get_role(role_id).mention
            for role_id in current_role_ids
            if interaction.guild.get_role(role_id)
        ]
        embed.add_field(
            name="Current Privileged Roles",
            value=", ".join(mentions) if mentions else "None",
            inline=False,
        )

        roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
        await interaction.response.send_message(
            embed=embed, view=RolePaginationView(roles, current_role_ids), ephemeral=True
        )

    @app_commands.command(name="viewperms", description="View privileged roles in this server")
    async def viewperms(self, interaction: Interaction):
        current_role_ids = await self.bot.repo.privileged_role_ids(interaction.guild.id)
        mentions = [
            interaction.guild.get_role(role_id).mention
            for role_id in current_role_ids
            if interaction.guild.get_role(role_id)
        ]
        embed = make_embed("Privileged Roles")
        embed.add_field(name="Roles", value=", ".join(mentions) if mentions else "No privileged roles", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editmemberroles", description="Edit roles corresponding to Clash Royale positions")
    @is_privileged()
    async def editmemberroles(self, interaction: Interaction):
        roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)

        position_views: dict[str, discord.ui.View] = {}
        for position in MEMBER_POSITIONS:
            view = discord.ui.View(timeout=120)
            for page in range(min(math.ceil(len(roles) / 25), 4)):
                view.add_item(PositionRoleSelect(position, roles, page))
            position_views[position] = view

        main_view = discord.ui.View(timeout=120)
        for position in MEMBER_POSITIONS:
            main_view.add_item(PositionButton(position, position_views))

        embed = make_embed("Edit Member Roles", "Select which position you want to edit.")
        await interaction.response.send_message(embed=embed, view=main_view, ephemeral=True)

    @app_commands.command(name="viewmemberroles", description="View roles corresponding to Clash Royale positions")
    async def viewmemberroles(self, interaction: Interaction):
        member_roles = await self.bot.repo.member_roles(interaction.guild.id)

        embed = make_embed("Member Roles", "Roles corresponding to Clash Royale positions")
        for position, role_id in member_roles.items():
            role = interaction.guild.get_role(role_id) if role_id else None
            embed.add_field(name=position.capitalize(), value=role.mention if role else "Not set", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reminders", description="Check current deck usage for a clan")
    @app_commands.describe(
        channel="The channel to send the deck usage report in",
        clan_tag="The tag of the clan (or a server nickname)",
    )
    @is_privileged()
    async def reminders(self, interaction: Interaction, channel: TextChannel, clan_tag: str):
        await interaction.response.defer(ephemeral=True)
        tag = await resolve_clan_tag(interaction, clan_tag)

        clan = await self.bot.cr.clan(tag)
        members = await self.bot.cr.clan_members(tag)
        race = await self.bot.cr.current_river_race(tag)
        participants = race_participants(race)
        if not participants:
            raise BotError("No data found for the specified clan.")

        member_tags = {m.tag for m in members}
        rows = [
            (p_tag, participant.get("name", "Unknown"), int(participant.get("decksUsedToday", 0)))
            for p_tag, participant in participants.items()
            if p_tag in member_tags
        ]
        if not rows:
            await interaction.followup.send(
                f"No current members have used decks today.\n"
                f"Total Current Members in {clan['name']}: {len(members)}",
                ephemeral=True,
            )
            return

        await channel.send(
            f"Player Names with Decks Used Today for Clan #{tag} ({clan['name']}):\n"
            f"Total Current Members: {len(members)}\n\n"
        )

        def new_table() -> PrettyTable:
            table = PrettyTable()
            table.field_names = ["Player Name", "Decks Used"]
            return table

        table = new_table()
        messages = []
        pings = []
        for member_tag, name, decks in rows:
            table.add_row([name, decks])
            discord_id = await self.bot.repo.discord_id_for_tag(member_tag)
            if discord_id and decks < 4:
                pings.append(f"<@{discord_id}>")
            if len(f"```{table}```") >= DISCORD_MESSAGE_LIMIT:
                messages.append(f"```{table}```")
                table = new_table()

        if table.rows:
            messages.append(f"```{table}```")

        for message in messages:
            await channel.send(message)
        if pings:
            await channel.send(" ".join(pings) + " You have used fewer than 4 decks today!")

        await interaction.followup.send(f"List sent to {channel.mention}.", ephemeral=True)
