import discord
from discord import Interaction, Embed
from utils.helpers import get_all_clan_links
from utils.api import get_current_clan_members


async def handle_viewnicks_command(interaction: Interaction):
    # Defer the interaction to avoid it expiring
    await interaction.response.defer()

    guild_id = str(interaction.guild_id)
    clan_links = get_all_clan_links()

    # Filter links for the current guild
    guild_clan_links = [link for link in clan_links if str(link[1]) == guild_id]

    if guild_clan_links:
        # Sort the clan links alphabetically by nickname
        guild_clan_links.sort(key=lambda x: x[2].lower())

        embed = Embed(
            title="Clan Nicknames",
            description="Here are all the clan nicknames linked in this server, sorted alphabetically:",
            color=0x1E133E
        )

        for clan_tag, _, nickname in guild_clan_links:
            try:
                # Fetch the clan name
                clan_name, _ = await get_current_clan_members(clan_tag)
                if clan_name:
                    embed.add_field(name=f"#{clan_tag} - {clan_name}", value=f"Nickname: {nickname}", inline=False)
                else:
                    embed.add_field(name=f"#{clan_tag}", value=f"Nickname: {nickname}", inline=False)
            except Exception as e:
                # If we can't fetch the clan name, just show the tag
                embed.add_field(name=f"#{clan_tag}", value=f"Nickname: {nickname}", inline=False)

        # Send the embed after processing is complete
        await interaction.followup.send(embed=embed)
    else:
        embed = Embed(
            title="No Nicknames Found",
            description="There are no clan nicknames linked in this server.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed)