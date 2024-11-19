import discord
from utils.helpers import get_member_roles

async def handle_viewmemberroles_command(interaction):
    guild_id = str(interaction.guild.id)
    member_roles = get_member_roles(guild_id)

    embed = discord.Embed(
        title="Member Roles",
        description="Roles corresponding to Clash Royale positions",
        color=0x1E133E
    )

    for position, role_id in member_roles.items():
        role = interaction.guild.get_role(int(role_id)) if role_id else None
        value = role.mention if role else "Not set"
        embed.add_field(name=position.capitalize(), value=value, inline=False)

    await interaction.response.send_message(embed=embed)