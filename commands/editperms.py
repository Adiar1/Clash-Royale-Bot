import discord
from discord.ext import commands
from utils.helpers import get_privileged_roles, add_privileged_roles
import math

class RoleSelect(discord.ui.Select):
    def __init__(self, roles, page=0):
        self.page = page
        self.roles = roles
        options = [
            discord.SelectOption(label=role.name, value=str(role.id))
            for role in roles[page * 25:(page + 1) * 25]
        ]

        super().__init__(
            placeholder=f"Select roles (Page {page + 1})",
            options=options,
            min_values=1,
            max_values=len(options)
        )

    async def callback(self, interaction):
        selected_roles = set(self.values)
        view = self.view
        current_roles = view.current_roles
        guild_id = str(interaction.guild.id)

        updated_roles = set(current_roles) ^ selected_roles

        if add_privileged_roles(guild_id, list(updated_roles)):
            updated_mentions = [
                interaction.guild.get_role(int(role_id)).mention
                for role_id in updated_roles
                if role_id.isdigit() and interaction.guild.get_role(int(role_id))
            ]
            success_embed = discord.Embed(
                title="Success",
                description=f"Privileged roles updated: {', '.join(updated_mentions) or 'No roles changed'}",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=success_embed, view=None)
        else:
            error_embed = discord.Embed(
                title="Error",
                description="Failed to update roles.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=error_embed, view=None)

class RolePaginationView(discord.ui.View):
    def __init__(self, roles, current_roles):
        super().__init__(timeout=120)
        self.roles = roles
        self.current_roles = current_roles
        self.page = 0
        self.max_pages = min(math.ceil(len(roles) / 25), 10)
        self.select = RoleSelect(roles, self.page)
        self.add_item(self.select)
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        self.select = RoleSelect(self.roles, self.page)
        self.add_item(self.select)
        self.add_item(self.prev_button())
        self.add_item(self.next_button())

    def prev_button(self):
        button = discord.ui.Button(label="Previous", style=discord.ButtonStyle.secondary)
        async def callback(interaction):
            self.page = max(self.page - 1, 0)
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        button.callback = callback
        button.disabled = self.page == 0
        return button

    def next_button(self):
        button = discord.ui.Button(label="Next", style=discord.ButtonStyle.secondary)
        async def callback(interaction):
            self.page = min(self.page + 1, self.max_pages - 1)
            self.update_buttons()
            await interaction.response.edit_message(view=self)
        button.callback = callback
        button.disabled = self.page >= self.max_pages - 1
        return button

async def handle_editperms_command(bot, interaction):
    guild_id = str(interaction.guild.id)
    current_roles = get_privileged_roles(guild_id)

    embed = discord.Embed(
        title="Edit Privileged Roles",
        description="Add/remove privileged roles.",
        color=0x1E133E
    )

    valid_roles = [
        interaction.guild.get_role(int(role_id))
        for role_id in current_roles
        if role_id.isdigit() and interaction.guild.get_role(int(role_id))
    ]
    role_mentions = [role.mention for role in valid_roles]

    embed.add_field(
        name="Current Privileged Roles",
        value=", ".join(role_mentions) if role_mentions else "None",
        inline=False
    )

    all_server_roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)
    view = RolePaginationView(all_server_roles, current_roles)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
