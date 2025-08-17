from discord import Interaction, Embed, Client, app_commands
from utils.helpers import get_clan_nickname, link_clan_tag, delete_clan_nickname, sanitize_tag
from utils.api import get_current_clan_members
import asyncio
import logging

logger = logging.getLogger(__name__)


async def handle_nicklink_command(interaction: Interaction, clan_tag: str, nickname: str = None):
    # Sanitize the clan_tag
    clan_tag = sanitize_tag(clan_tag)
    guild_id = str(interaction.guild_id)  # Get the guild ID

    # Check if this is a deletion request (nickname is None or empty)
    if nickname is None or nickname.strip() == "":
        await handle_nickname_deletion(interaction, clan_tag, guild_id)
        return

    nickname = nickname.strip()

    if len(nickname) >= 5:
        await interaction.response.send_message("Nickname must be less than 5 characters.", ephemeral=True)
        return

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


async def handle_nickname_deletion(interaction: Interaction, clan_tag: str, guild_id: str):
    """Handle deletion of a clan nickname"""
    existing_nickname = get_clan_nickname(clan_tag, guild_id)

    if not existing_nickname:
        await interaction.response.send_message(
            f"No nickname found for clan tag `{clan_tag}` in this server.",
            ephemeral=True
        )
        return

    # Show confirmation dialog
    embed = Embed(
        title="Delete Nickname Confirmation",
        description=f"Are you sure you want to delete the nickname `{existing_nickname}` for clan tag `{clan_tag}`?",
        color=0xff6b6b
    )
    embed.add_field(name="⚠️ Warning", value="This action cannot be undone.", inline=False)
    embed.set_footer(text="React with ✅ to confirm deletion or ❌ to cancel.")

    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    await message.add_reaction("✅")
    await message.add_reaction("❌")

    def check(reaction, user):
        return user == interaction.user and reaction.message.id == message.id and str(reaction.emoji) in ["✅", "❌"]

    try:
        reaction, _ = await interaction.client.wait_for("reaction_add", timeout=60.0, check=check)

        if str(reaction.emoji) == "✅":
            success = delete_clan_nickname(clan_tag, guild_id)
            if success:
                final_embed = Embed(
                    title="Nickname Deleted",
                    description=f"The nickname `{existing_nickname}` for clan tag `{clan_tag}` has been successfully deleted.",
                    color=0x00ff00
                )
            else:
                final_embed = Embed(
                    title="Deletion Failed",
                    description="An error occurred while deleting the nickname. Please try again later.",
                    color=0xff0000
                )
        else:
            final_embed = Embed(
                title="Deletion Canceled",
                description=f"The nickname deletion for clan tag `{clan_tag}` has been canceled.",
                color=0x1E133E
            )

        await interaction.followup.send(embed=final_embed)

    except asyncio.TimeoutError:
        timeout_embed = Embed(
            title="Deletion Timeout",
            description="You did not respond in time. No changes were made.",
            color=0x1E133E
        )
        await interaction.followup.send(embed=timeout_embed)