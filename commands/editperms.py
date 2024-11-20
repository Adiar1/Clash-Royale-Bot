import discord
from discord.ext import commands
from utils.helpers import get_privileged_roles, add_privileged_roles
import math


async def handle_editperms_command(bot, interaction):
    guild_id = str(interaction.guild.id)
    current_roles = get_privileged_roles(guild_id)

    embed = discord.Embed(
        title="Edit Privileged Roles",
        description="Add/remove privileged roles.\n\nSelect roles across multiple dropdowns if needed.",
        color=0x1E133E
    )

    # Filter out any empty or invalid role IDs
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

    class RoleSelect(discord.ui.Select):
        def __init__(self, roles, page=0):
            # Create options for this specific page of roles
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
            self.page = page
            self.all_roles = roles

        async def callback(self, interaction):
            # Combine selected roles from all dropdowns
            selected_roles = set(self.values)

            # Toggle selected roles (add or remove)
            updated_roles = set(current_roles) ^ selected_roles

            if add_privileged_roles(guild_id, list(updated_roles)):
                # Get mentions of updated roles
                updated_role_mentions = [
                    interaction.guild.get_role(int(role_id)).mention
                    for role_id in updated_roles
                    if role_id.isdigit() and interaction.guild.get_role(int(role_id))
                ]

                # Create success embed
                success_embed = discord.Embed(
                    title="Success",
                    description=f"Privileged roles updated successfully: {', '.join(updated_role_mentions) or 'No roles changed'}",
                    color=discord.Color.green()
                )

                await interaction.response.edit_message(embed=success_embed, view=None)
            else:
                # Create error embed
                error_embed = discord.Embed(
                    title="Error",
                    description="Failed to update roles.",
                    color=discord.Color.red()
                )

                await interaction.response.edit_message(embed=error_embed, view=None)

    # Create view with multiple dropdowns if needed
    view = discord.ui.View()
    all_server_roles = sorted(interaction.guild.roles, key=lambda r: r.position, reverse=True)

    # Calculate number of pages needed
    num_pages = math.ceil(len(all_server_roles) / 25)

    # Add dropdowns for each page
    for page in range(num_pages):
        role_select = RoleSelect(all_server_roles, page)
        view.add_item(role_select)

    # Send the message with all dropdowns
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)