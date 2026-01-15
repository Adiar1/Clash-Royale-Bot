import discord
from discord import Interaction
from utils.api import get_current_clan_members, is_real_clan_tag
from utils.helpers import get_clan_tag_by_nickname, get_discord_id_from_tag, sanitize_tag


async def handle_viewlinks_command(interaction: Interaction, input_value: str):
    await interaction.response.defer()

    # Determine if input is a tag or nickname
    input_value = input_value
    if len(input_value) < 5:
        clan_tag = get_clan_tag_by_nickname(input_value, interaction.guild.id)
        if clan_tag is None:
            await interaction.followup.send("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
            return
    else:
        clan_tag = sanitize_tag(input_value)

    if not await is_real_clan_tag(clan_tag):
        await interaction.followup.send("Oopsy daisies. Check that tag/nickname real quick", ephemeral=True)
        return

    try:
        clan_name, members = await get_current_clan_members(clan_tag)

        # Format member list
        lines = []
        for tag, name in members:
            discord_id = get_discord_id_from_tag(tag)
            if discord_id:
                lines.append(f"<@{discord_id}>") # Mentions but doesn't ping by default
            else:
                lines.append(f"`{name}`")

        message = f"**Members of {clan_name} (#{clan_tag}):**\n\n" + "\n".join(lines)
        await interaction.followup.send(
            message[:2000],
            allowed_mentions=discord.AllowedMentions(users=[])
        ) # Discord max message length safety

    except Exception as e:
        print(f"Error in /viewlinks: {e}")
        await interaction.followup.send("Something went wrong while fetching clan members.", ephemeral=True)
