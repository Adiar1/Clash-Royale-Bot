import discord
from discord import app_commands
from utils.helpers import update_member_roles
import math


async def handle_editmemberroles_command(bot, interaction):
    guild_id = interaction.guild.id
    all_server_roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)

    class RoleSelect(discord.ui.Select):
        def __init__(self, position, roles, page=0):
            # Create options for this specific page of roles
            options = [
                discord.SelectOption(label=role.name, value=str(role.id))
                for role in roles[page * 25:(page + 1) * 25]
            ]

            super().__init__(
                placeholder=f"Select {position} role (Page {page + 1})",
                options=options,
                min_values=1,
                max_values=1
            )
            self.position = position
            self.page = page
            self.all_roles = roles

        async def callback(self, interaction):
            role_id = int(self.values[0])
            role = interaction.guild.get_role(role_id)
            if role:
                position_key = self.position.lower().replace('-', '')  # Convert 'Co-Leader' to 'coleader'
                if update_member_roles(guild_id, position_key, role_id):
                    success_embed = discord.Embed(
                        title="Success",
                        description=f"{self.position} role updated to {role.mention}",
                        color=discord.Color.green()
                    )
                    await interaction.response.edit_message(embed=success_embed, view=None)
                else:
                    error_embed = discord.Embed(
                        title="Error",
                        description=f"Failed to update {self.position} role",
                        color=discord.Color.red()
                    )
                    await interaction.response.edit_message(embed=error_embed, view=None)
            else:
                error_embed = discord.Embed(
                    title="Error",
                    description="Invalid role selected",
                    color=discord.Color.red()
                )
                await interaction.response.edit_message(embed=error_embed, view=None)

    # Create dictionary to store position-specific views
    position_views = {}

    # Create separate views for each position
    for position in ["Member", "Elder", "Co-Leader"]:
        view = discord.ui.View()
        # Add role selects for this position
        for page in range(math.ceil(len(all_server_roles) / 25)):
            view.add_item(RoleSelect(position, all_server_roles, page))
        position_views[position] = view

    # Create buttons to switch between positions
    class PositionButton(discord.ui.Button):
        def __init__(self, position):
            super().__init__(label=position, style=discord.ButtonStyle.primary)
            self.position = position

        async def callback(self, interaction):
            embed = discord.Embed(
                title=f"Edit {self.position} Role",
                description=f"Select the role to assign to {self.position}s.",
                color=0x1E133E
            )
            await interaction.response.edit_message(
                embed=embed,
                view=position_views[self.position]
            )

    # Create main view with position buttons
    main_view = discord.ui.View()
    for position in ["Member", "Elder", "Co-Leader"]:
        main_view.add_item(PositionButton(position))

    # Initial embed
    embed = discord.Embed(
        title="Edit Member Roles",
        description="Select which position you want to edit.",
        color=0x1E133E
    )

    await interaction.response.send_message(embed=embed, view=main_view, ephemeral=True)