import asyncio
import logging
import discord
from discord import Interaction

from utils.helpers import (
    sanitize_tag, LEVEL_EMOJIS, EMOJI_TROPHYROAD, EVOLUTION_EMOJI,
    LEVEL_16_EMOJI, LEVEL_15_EMOJI, LEVEL_14_EMOJI, CW2_EMOJI, CC_EMOJI,
    GC_EMOJI, FAME_EMOJI, MULTIDECK_EMOJI, rankedMEDAL_EMOJI, LEAGUE_IMAGES,
    get_player_tag_from_mention
)
from utils.api import (
    get_player_trophies, get_player_clan_info, get_player_badges, get_player_cards,
    get_player_best_trophies, get_player_info, get_player_path_of_legends_info,
    get_current_fame, get_last_fame, get_members_current_decks_used, get_last_decks_used
)

logger = logging.getLogger(__name__)


async def handle_player_command(interaction: Interaction, user_or_tag: str):
    """Entry point for the /player command."""
    try:
        player_tag = (
            sanitize_tag(user_or_tag)
            if not user_or_tag.startswith('<@')
            else get_player_tag_from_mention(user_or_tag, str(interaction.guild.id))
        )

        if not player_tag:
            await interaction.response.send_message(
                "Player not found or user doesn't have a linked Clash Royale account.",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        # Fetch essential info
        player_info = await get_player_info(player_tag)
        if not player_info:
            await interaction.followup.send("Player not found. Please check the tag and try again.")
            return

        trophies = await get_player_trophies(player_tag, player_info)
        best_trophies = await get_player_best_trophies(player_tag, player_info)

        # Fetch all data in parallel
        tasks = [
            get_player_cards(player_tag),
            get_player_badges(player_tag),
            get_player_clan_info(player_tag),
            get_player_path_of_legends_info(player_tag),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=False)
        full_results = [player_info, trophies, best_trophies] + list(results)

        await _handle_player_data(interaction, full_results)

    except asyncio.TimeoutError:
        logger.warning("Timeout while handling player command", exc_info=True)
        await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
    except Exception:
        logger.exception("Unhandled error while handling player command")
        await interaction.followup.send("An unexpected error occurred while processing your request.")


async def _handle_player_data(interaction: Interaction, results):
    """Build and send the embed based on fetched data."""
    player_info, trophies, best_trophies, cards, badges, clan_tag, ranked_info = results

    nohash_clan_tag = (clan_tag or {}).get('tag', '').strip('#')
    player_tag = player_info.get('tag', '')

    try:
        current_fame, last_fame, current_decks_used, last_decks_used = await asyncio.gather(
            get_current_fame(nohash_clan_tag, player_tag),
            get_last_fame(nohash_clan_tag, player_tag),
            get_members_current_decks_used(nohash_clan_tag, player_tag),
            get_last_decks_used(nohash_clan_tag, player_tag),
        )
    except Exception:
        logger.exception("Failed to fetch war stats for player %s", player_tag)
        current_fame = last_fame = current_decks_used = last_decks_used = 0

    embed = _create_player_embed(
        player_info=player_info,
        player_tag=player_tag,
        trophies=trophies,
        best_trophies=best_trophies,
        cards=cards,
        badges=badges,
        clan_tag=clan_tag,
        current_fame=current_fame or 0,
        current_decks_used=current_decks_used or 0,
        last_fame=last_fame or 0,
        last_decks_used=last_decks_used or 0,
        ranked_info=ranked_info,
    )

    await interaction.followup.send(embed=embed)


def _create_player_embed(
    *,
    player_info: dict,
    player_tag: str,
    trophies: int,
    best_trophies: int,
    cards: list,
    badges: list,
    clan_tag: dict | None,
    current_fame: int,
    current_decks_used: int,
    last_fame: int,
    last_decks_used: int,
    ranked_info: dict | None,
) -> discord.Embed:
    """Construct the Discord embed for player data."""
    embed = discord.Embed(
        title=f"{player_info.get('name','')} {player_tag} {LEVEL_EMOJIS.get(player_info.get('expLevel', 0), '')}",
        color=0x1E133E,
        url=f"https://royaleapi.com/player/{player_info.get('tag','').strip('#').upper()}"
    )

    # Clan
    if clan_tag:
        clan_name = clan_tag.get('name', 'No Clan')
        nohash_clan_tag = clan_tag.get('tag', '').strip('#')
        clan_url = f"https://royaleapi.com/clan/{nohash_clan_tag}"
        role = (player_info.get('role') or '').capitalize()
        embed.add_field(
            name="**__Clan__**",
            value=f"[{clan_name}](<{clan_url}>) #{nohash_clan_tag} ({role})",
            inline=True
        )
    else:
        embed.add_field(name="**__Clan__**", value='No Clan', inline=True)

    # Trophy Road
    embed.add_field(
        name="**__Trophy Road__**",
        value=f"Current: {EMOJI_TROPHYROAD} {trophies}\nBest: {EMOJI_TROPHYROAD} {best_trophies}",
        inline=False
    )

    # Card Levels - Updated for max level 16
    safe_cards = cards or []
    evolution_cards = [c for c in safe_cards if c.get('evolutionLevel', 0) == 1]
    level_16_cards = [c for c in safe_cards if c.get('level') == c.get('maxLevel', 0) ]
    level_15_cards = [c for c in safe_cards if c.get('level') == c.get('maxLevel', 0) - 1]
    level_14_cards = [c for c in safe_cards if c.get('level') == c.get('maxLevel', 0) - 2]

    embed.add_field(
        name="**__Card Levels__**",
        value=(
            f"{EVOLUTION_EMOJI}: {len(evolution_cards)}\n"
            f"{LEVEL_16_EMOJI}: {len(level_16_cards)}\n"
            f"{LEVEL_15_EMOJI}: {len(level_15_cards)}\n"
            f"{LEVEL_14_EMOJI}: {len(level_14_cards)}"
        ),
        inline=False
    )

    # Ranked (Path of Legends) - Always show if available
    if ranked_info:
        ranked_current_display = _format_ranked_entry(ranked_info.get('current', {}))
        ranked_best_display = _format_ranked_entry(ranked_info.get('best', {}))
        embed.add_field(
            name="**__Ranked__**",
            value=f"Current: {ranked_current_display}\nBest: {ranked_best_display}",
            inline=False
        )

        # Coerce to int for LEAGUE_IMAGES keys
        current_league = ranked_info.get('current', {}).get('leagueNumber', None)
        try:
            current_league = int(current_league) if current_league is not None else None
        except (ValueError, TypeError):
            current_league = None

        if current_league and current_league in LEAGUE_IMAGES:
            embed.set_thumbnail(url=LEAGUE_IMAGES[current_league])

    # War stats
    cw2_wins = next((b.get('progress', '0') for b in (badges or []) if b.get('name') == 'ClanWarWins'), '0')
    gc_wins = next((b.get('progress', '0') for b in (badges or []) if b.get('name') == 'Grand12Wins'), '0')
    cc_wins = next((b.get('progress', '0') for b in (badges or []) if b.get('name') == 'Classic12Wins'), '0')

    embed.add_field(name="**__CW2 Wins__**", value=f"{CW2_EMOJI} {cw2_wins}", inline=True)
    embed.add_field(name="**__CC Wins__**", value=f"{CC_EMOJI} {cc_wins}", inline=True)
    embed.add_field(name="**__GC Wins__**", value=f"{GC_EMOJI} {gc_wins}", inline=True)

    embed.add_field(
        name="**__Current War Stats__**",
        value=f"{FAME_EMOJI} {current_fame}\n{MULTIDECK_EMOJI} {current_decks_used}",
        inline=True
    )
    embed.add_field(
        name="**__Last War Stats__**",
        value=f"{FAME_EMOJI} {last_fame}\n{MULTIDECK_EMOJI} {last_decks_used}",
        inline=True
    )

    return embed


def _format_ranked_entry(ranked_entry: dict) -> str:
    """Format ranked entry for display; robust to missing/typed fields."""
    league_number = ranked_entry.get('leagueNumber')
    try:
        league_number = int(league_number) if league_number is not None else None
    except (ValueError, TypeError):
        league_number = None

    if league_number is not None and league_number >= 7:
        trophies = ranked_entry.get('trophies', 0)
        rank = ranked_entry.get('rank')
        display = f"{rankedMEDAL_EMOJI} {trophies}"
        if rank is not None:
            display += f" (Rank: #{rank})"
        return display

    if league_number is None:
        return "League ---"
    return f"League {league_number}"