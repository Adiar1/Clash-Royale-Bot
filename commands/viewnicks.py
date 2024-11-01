import discord
from discord import Interaction, Embed
from utils.database import get_all_clan_links
from utils.api import get_current_clan_members


async def handle_viewnicks_command(interaction: Interaction):
    guild_id = str(interaction.guild_id)
    clan_links = get_all_clan_links()

    # Filter links for the current guild
    guild_clan_links = [link for link in clan_links if link[1] == guild_id]

    if guild_clan_links:
        embed = Embed(
            title="Clan Nicknames",
            description="Here are all the clan nicknames linked in this server:",
            color=0x1E133E
        )

        for clan_tag, _, nickname in guild_clan_links:
            # Fetch the clan name
            clan_name, _ = await get_current_clan_members(clan_tag)
            embed.add_field(name=f"#{clan_tag} - {clan_name}", value=nickname, inline=False)

        await interaction.response.send_message(embed=embed)
    else:
        embed = Embed(
            title="No Nicknames Found",
            description="There are no clan nicknames linked in this server.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)