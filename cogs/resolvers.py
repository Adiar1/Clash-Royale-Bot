"""Shared input resolution for commands: clan tag/nickname and player tag/mention."""

from discord import Interaction

from errors import InvalidClanTag, NotLinked
from services.clash_royale import normalize_tag


async def resolve_clan_tag(interaction: Interaction, value: str) -> str:
    """Resolve user input into a validated, normalized clan tag.

    Inputs shorter than 5 characters are treated as server nicknames
    (real tags are always longer); anything else as a raw tag.
    Raises InvalidClanTag if the nickname is unknown or the clan doesn't exist.
    """
    bot = interaction.client
    value = value.strip()

    if len(value) < 5:
        clan_tag = await bot.repo.clan_tag_for_nickname(value, interaction.guild.id)
        if clan_tag is None:
            raise InvalidClanTag()
    else:
        clan_tag = normalize_tag(value)

    if not await bot.cr.clan_exists(clan_tag):
        raise InvalidClanTag()
    return clan_tag


async def resolve_player_tag(interaction: Interaction, value: str) -> str:
    """Resolve a raw player tag or a Discord @mention into a normalized player tag.

    Mentions resolve to the user's main linked tag; raises NotLinked otherwise.
    """
    value = value.strip()
    if value.startswith("<@") and value.endswith(">"):
        user_id = value.strip("<@!>")
        if not user_id.isdigit():
            raise NotLinked()
        tags = await interaction.client.repo.player_tags(int(user_id))
        if not tags:
            raise NotLinked("That user doesn't have a linked Clash Royale account.")
        return tags[0]
    return normalize_tag(value)
