import discord
from discord import app_commands
from utils.helpers import update_member_roles

async def handle_editmemberroles_command(bot, interaction):
    guild_id = interaction.guild.id

    embed = discord.Embed(
        title="Edit Member Roles",
        description="Select roles corresponding to Clash Royale positions.",
        color=0x1E133E
    )

    class RoleSelect(discord.ui.Select):
        def __init__(self, position):
            options = [
                discord.SelectOption(label=role.name, value=str(role.id))
                for role in interaction.guild.roles
                if role < interaction.guild.me.top_role and not role.managed
            ]
            super().__init__(
                placeholder=f"Select {position} role",
                options=options,
                min_values=1,
                max_values=1
            )
            self.position = position

        async def callback(self, interaction):
            role_id = int(self.values[0])
            role = interaction.guild.get_role(role_id)
            if role:
                position_key = self.position.lower().replace('-', '')  # Convert 'Co-Leader' to 'coleader'
                if update_member_roles(guild_id, position_key, role_id):
                    await interaction.response.send_message(f"{self.position} role updated to {role.mention}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Failed to update {self.position} role", ephemeral=True)
            else:
                await interaction.response.send_message("Invalid role selected", ephemeral=True)

    view = discord.ui.View()
    for position in ["Member", "Elder", "Co-Leader"]:
        view.add_item(RoleSelect(position))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)