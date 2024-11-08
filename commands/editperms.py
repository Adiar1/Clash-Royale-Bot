import discord
from discord.ext import commands
from utils.helpers import get_privileged_roles, add_privileged_roles


async def handle_editperms_command(bot, interaction):
    guild_id = str(interaction.guild.id)
    current_roles = get_privileged_roles(guild_id)

    embed = discord.Embed(
        title="Edit Privileged Roles",
        description="Add/remove privileged roles.",
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

    view = discord.ui.View()

    class RoleSelect(discord.ui.Select):
        def __init__(self, roles):
            options = [
                discord.SelectOption(label=role.name, value=str(role.id))
                for role in roles
            ]
            super().__init__(
                placeholder="Select new privileged roles",
                options=options,
                min_values=1,
                max_values=len(roles)
            )

        async def callback(self, interaction):
            selected_roles = set(self.values)
            updated_roles = set(current_roles) ^ selected_roles
            if add_privileged_roles(guild_id, list(updated_roles)):
                updated_role_mentions = [
                    interaction.guild.get_role(int(role_id)).mention
                    for role_id in updated_roles
                    if role_id.isdigit() and interaction.guild.get_role(int(role_id))
                ]
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Success",
                        description=f"Privileged roles updated successfully: {', '.join(updated_role_mentions)}",
                        color=discord.Color.green()
                    ),
                    view=None
                )
            else:
                await interaction.response.edit_message(
                    embed=discord.Embed(
                        title="Error",
                        description="Failed to update roles.",
                        color=discord.Color.red()
                    ),
                    view=None
                )

    view.add_item(RoleSelect(interaction.guild.roles))
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
