from discord import Interaction, Embed, Client, app_commands
from utils.database import link_clan_tag, get_clan_nickname
from utils.api import get_current_clan_members
import asyncio
import logging

logger = logging.getLogger(__name__)

async def handle_nicklink_command(interaction: Interaction, clan_tag: str, nickname: str):
    if len(nickname) >= 5:
        await interaction.response.send_message("Nickname must be less than 5 characters.", ephemeral=True)
        return

    clan_tag = clan_tag.replace('#', '').upper()
    guild_id = str(interaction.guild_id)  # Get the guild ID

    try:
        clan_name, members = await asyncio.wait_for(get_current_clan_members(clan_tag), timeout=10)

        if members:
            existing_nickname = get_clan_nickname(clan_tag, guild_id)

            if existing_nickname:
                embed = Embed(
                    title="Update Nickname Confirmation",
                    description=f"The clan tag `{clan_tag}` is already linked with the nickname `{existing_nickname}` in this server.",
                    color=0x1E133E
                )
                embed.add_field(name="New Nickname", value=nickname, inline=False)
                embed.set_footer(text="React with ✅ to confirm or ❌ to cancel.")

                await interaction.response.send_message(embed=embed)
                message = await interaction.original_response()
                await message.add_reaction("✅")
                await message.add_reaction("❌")

                def check(reaction, user):
                    return user == interaction.user and reaction.message.id == message.id and str(reaction.emoji) in [
                        "✅", "❌"]

                try:
                    reaction, _ = await interaction.client.wait_for("reaction_add", timeout=60.0, check=check)

                    if str(reaction.emoji) == "✅":
                        link_clan_tag(clan_tag, guild_id, nickname)
                        final_embed = Embed(
                            title="Nickname Updated",
                            description=f"The nickname for clan tag `{clan_tag}` has been updated to `{nickname}`.",
                            color=0x00ff00
                        )
                    else:
                        final_embed = Embed(
                            title="Update Canceled",
                            description=f"The nickname update for clan tag `{clan_tag}` has been canceled.",
                            color=0xff0000
                        )

                    await interaction.followup.send(embed=final_embed)

                except asyncio.TimeoutError:
                    timeout_embed = Embed(
                        title="Update Timeout",
                        description="You did not respond in time. No changes were made.",
                        color=0x1E133E
                    )
                    await interaction.followup.send(embed=timeout_embed)

            else:
                result = link_clan_tag(clan_tag, guild_id, nickname)
                if result == "linked":
                    await interaction.response.send_message(
                        f"Clan tag {clan_tag} linked with nickname '{nickname}' in this server.")
                else:
                    await interaction.response.send_message(
                        "An error occurred while linking the clan tag. Please try again later.")
        else:
            await interaction.response.send_message("The clan tag is not valid or the clan has no members.")
    except Exception as e:
        logger.error(f"Failed to verify clan tag {clan_tag}: {e}")
        await interaction.response.send_message("The clan tag is not valid or an error occurred while verifying it.")