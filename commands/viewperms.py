import discord
from utils.helpers import get_privileged_roles

async def handle_viewperms_command(interaction):
    guild_id = str(interaction.guild.id)
    current_roles = get_privileged_roles(guild_id)

    embed = discord.Embed(
        title="Privileged Roles",
        color=0x1E133E
    )

    role_mentions = [
        interaction.guild.get_role(int(role_id)).mention
        for role_id in current_roles
        if role_id.isdigit() and interaction.guild.get_role(int(role_id))
    ]

    if role_mentions:
        embed.add_field(name="Roles", value=", ".join(role_mentions), inline=False)
    else:
        embed.add_field(name="Roles", value="No privileged roles", inline=False)

    await interaction.response.send_message(embed=embed)