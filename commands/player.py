import asyncio

import aiohttp
import discord
from discord import Interaction
from utils.helpers import sanitize_tag, LEVEL_EMOJIS, EMOJI_TROPHYROAD, EVOLUTION_EMOJI, LEVEL_15_EMOJI, LEVEL_14_EMOJI, \
    LEVEL_13_EMOJI, CW2_EMOJI, CC_EMOJI, GC_EMOJI, FAME_EMOJI, MULTIDECK_EMOJI, POLMEDAL_EMOJI, LEAGUE_IMAGES
from utils.api import get_player_trophies, get_player_clan_info, get_player_badges, get_player_cards, \
    get_player_best_trophies, get_player_info, get_player_path_of_legends_info, get_current_fame, get_last_fame, \
    get_members_current_decks_used, get_last_decks_used


async def handle_player_command(interaction: Interaction, player_tag: str):
    player_tag = sanitize_tag(player_tag)

    if player_tag.startswith('#'):
        player_tag = player_tag[1:]

    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        try:
            # Fetch player trophies to decide which logic to use
            trophies = await get_player_trophies(player_tag)

            # Determine which set of tasks to perform based on trophy count
            if trophies < 5000:
                tasks = [
                    get_player_info(player_tag),
                    get_player_trophies(player_tag),
                    get_player_best_trophies(player_tag),
                    get_player_cards(player_tag),
                    get_player_badges(player_tag),
                    get_player_clan_info(player_tag),
                ]
            else:
                tasks = [
                    get_player_info(player_tag),
                    get_player_trophies(player_tag),
                    get_player_best_trophies(player_tag),
                    get_player_path_of_legends_info(player_tag),
                    get_player_cards(player_tag),
                    get_player_badges(player_tag),
                    get_player_clan_info(player_tag),
                ]

            try:
                results = await asyncio.gather(*tasks)

                if not results[0]:  # player_info
                    await interaction.followup.send("Player not found. Please check the tag and try again.")
                    return

                if trophies < 5000:
                    await handle_below_5000(interaction, results)
                else:
                    await handle_5000_or_above(interaction, results)

            except asyncio.TimeoutError:
                await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
                return

        except aiohttp.ClientError:
            await interaction.followup.send("Network error occurred. Please try again later.")
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")

async def handle_below_5000(interaction, results):
    player_info, trophies, best_trophies, cards, badges, clan_tag = results
    nohash_clan_tag = clan_tag.get('tag', '').strip('#')
    player_tag = f"{player_info.get('tag', '')}"

    current_fame, last_fame, current_decks_used, last_decks_used = await asyncio.gather(
        get_current_fame(nohash_clan_tag, player_tag),
        get_last_fame(nohash_clan_tag, player_tag),
        get_members_current_decks_used(nohash_clan_tag, player_tag),
        get_last_decks_used(nohash_clan_tag, player_tag),
    )

    embed = create_player_embed_below_5000(
        player_info, player_tag, trophies, best_trophies, cards, badges,
        clan_tag, current_fame or 0, current_decks_used or 0, last_fame or 0, last_decks_used or 0
    )

    await interaction.followup.send(embed=embed)

async def handle_5000_or_above(interaction, results):
    player_info, trophies, best_trophies, pol_info, cards, badges, clan_tag = results
    nohash_clan_tag = clan_tag.get('tag', '').strip('#')
    player_tag = f"{player_info.get('tag', '')}"

    current_fame, last_fame, current_decks_used, last_decks_used = await asyncio.gather(
        get_current_fame(nohash_clan_tag, player_tag),
        get_last_fame(nohash_clan_tag, player_tag),
        get_members_current_decks_used(nohash_clan_tag, player_tag),
        get_last_decks_used(nohash_clan_tag, player_tag),
    )

    embed = create_player_embed_5000_or_above(
        player_info, player_tag, trophies, best_trophies, pol_info, cards, badges,
        clan_tag, current_fame or 0, current_decks_used or 0, last_fame or 0, last_decks_used or 0
    )

    await interaction.followup.send(embed=embed)

def create_player_embed_below_5000(player_info, player_tag, trophies, best_trophies, cards, badges, clan_tag,
                                   current_fame, current_decks_used, last_fame, last_decks_used):
    player_name = player_info.get('name', 'Unknown Player')
    player_level = LEVEL_EMOJIS.get(player_info.get('expLevel'), '')

    embed = discord.Embed(
        title=f"{player_name} {player_tag} {player_level}",
        color=0x1E133E,
        url=f"https://royaleapi.com/player/{player_info.get('tag', '').strip('#').upper()}"
    )

    if clan_tag:
        clan_name = clan_tag.get('name', 'No Clan')
        nohash_clan_tag = clan_tag.get('tag', '').strip('#')
        clan_url = f"https://royaleapi.com/clan/{nohash_clan_tag}"
        clan_link = f"[{clan_name}](<{clan_url}>)"
        role = player_info.get('role', 'Member').capitalize()
        embed.add_field(name="**__Clan__**", value=f"{clan_link} #{nohash_clan_tag} ({role})", inline=True)
    else:
        embed.add_field(name="**__Clan__**", value='No Clan', inline=True)

    embed.add_field(name="**__Trophy Road__**",
                    value=f"Current: {EMOJI_TROPHYROAD} {trophies}\nBest: {EMOJI_TROPHYROAD} {best_trophies}",
                    inline=False)

    evolution_cards = [card for card in cards if card.get('evolutionLevel', 0) == 1]
    level_15_cards = [card for card in cards if card.get('level') == card.get('maxLevel') + 1]
    level_14_cards = [card for card in cards if card.get('level') == card.get('maxLevel')]
    level_13_cards = [card for card in cards if card.get('level') == card.get('maxLevel') - 1]

    embed.add_field(name="**__Card Levels__**",
                    value=f"{EVOLUTION_EMOJI}: {len(evolution_cards)}\n"
                          f"{LEVEL_15_EMOJI}: {len(level_15_cards)}\n"
                          f"{LEVEL_14_EMOJI}: {len(level_14_cards)}\n"
                          f"{LEVEL_13_EMOJI}: {len(level_13_cards)}",
                    inline=False)

    cw2_wins = next((badge.get('progress', '0') for badge in badges if badge.get('name') == 'ClanWarWins'), '0')
    gc_wins = next((badge.get('progress', '0') for badge in badges if badge.get('name') == 'Grand12Wins'), '0')
    cc_wins = next((badge.get('progress', '0') for badge in badges if badge.get('name') == 'Classic12Wins'), '0')

    embed.add_field(name="**__CW2 Wins__**", value=f"{CW2_EMOJI} {cw2_wins}", inline=True)
    embed.add_field(name="**__CC Wins__**", value=f"{CC_EMOJI} {cc_wins}", inline=True)
    embed.add_field(name="**__GC Wins__**", value=f"{GC_EMOJI} {gc_wins}", inline=True)

    embed.add_field(name="**__Current War Stats__**",
                    value=f"{FAME_EMOJI} {current_fame}\n{MULTIDECK_EMOJI} {current_decks_used}", inline=True)
    embed.add_field(name="**__Last War Stats__**",
                    value=f"{FAME_EMOJI} {last_fame}\n{MULTIDECK_EMOJI} {last_decks_used}", inline=True)

    return embed

def create_player_embed_5000_or_above(player_info, player_tag, trophies, best_trophies, pol_info, cards, badges, clan_tag,
                                      current_fame, current_decks_used, last_fame, last_decks_used):
    embed = discord.Embed(
        title=f"{player_info['name']} {player_tag} {LEVEL_EMOJIS.get(player_info['expLevel'], '')}",
        color=0x1E133E,
        url=f"https://royaleapi.com/player/{player_info['tag'].strip('#').upper()}"
    )

    if clan_tag:
        clan_name = clan_tag.get('name', 'No Clan')
        nohash_clan_tag = clan_tag.get('tag', '').strip('#')
        clan_url = f"https://royaleapi.com/clan/{nohash_clan_tag}"
        clan_link = f"[{clan_name}](<{clan_url}>)"
        role = player_info.get('role', '').capitalize() if player_info.get('role') else ''
        embed.add_field(name="**__Clan__**", value=f"{clan_link} #{nohash_clan_tag} ({role})", inline=True)
    else:
        embed.add_field(name="**__Clan__**", value='No Clan', inline=True)

    embed.add_field(name="**__Trophy Road__**",
                    value=f"Current: {EMOJI_TROPHYROAD} {trophies}\nBest: {EMOJI_TROPHYROAD} {best_trophies}",
                    inline=False)

    def format_pol_entry(pol_entry):
        league_number = pol_entry.get('leagueNumber', '---')
        if league_number == 10:
            trophies = pol_entry.get('trophies', 0)
            rank = pol_entry.get('rank')
            display = f"{POLMEDAL_EMOJI} {trophies}"
            if rank is not None:
                display += f" (Rank: #{rank})"
        else:
            display = f"League {league_number}"
        return display

    pol_current_display = format_pol_entry(pol_info['current'])
    pol_best_display = format_pol_entry(pol_info['best'])

    embed.add_field(name="**__Path of Legends__**",
                    value=f"Current: {pol_current_display}\nBest: {pol_best_display}",
                    inline=False)

    evolution_cards = [card for card in cards if card.get('evolutionLevel', 0) == 1]
    level_15_cards = [card for card in cards if card.get('level') == card.get('maxLevel') + 1]
    level_14_cards = [card for card in cards if card.get('level') == card.get('maxLevel')]
    level_13_cards = [card for card in cards if card.get('level') == card.get('maxLevel') - 1]

    embed.add_field(name="**__Card Levels__**",
                    value=f"{EVOLUTION_EMOJI}: {len(evolution_cards)}\n"
                          f"{LEVEL_15_EMOJI}: {len(level_15_cards)}\n"
                          f"{LEVEL_14_EMOJI}: {len(level_14_cards)}\n"
                          f"{LEVEL_13_EMOJI}: {len(level_13_cards)}",
                    inline=False)

    current_league = pol_info['current'].get('leagueNumber')
    if current_league in LEAGUE_IMAGES:
        embed.set_thumbnail(url=LEAGUE_IMAGES[current_league])

    cw2_wins = next((badge['progress'] for badge in badges if badge['name'] == 'ClanWarWins'), '0')
    gc_wins = next((badge['progress'] for badge in badges if badge['name'] == 'Grand12Wins'), '0')
    cc_wins = next((badge['progress'] for badge in badges if badge['name'] == 'Classic12Wins'), '0')
    embed.add_field(name="**__CW2 Wins__**", value=f"{CW2_EMOJI} {cw2_wins}", inline=True)
    embed.add_field(name="**__CC Wins__**", value=f"{CC_EMOJI} {cc_wins}", inline=True)
    embed.add_field(name="**__GC Wins__**", value=f"{GC_EMOJI} {gc_wins}", inline=True)

    embed.add_field(name="**__Current War Stats__**",
                    value=f"{FAME_EMOJI} {current_fame}\n{MULTIDECK_EMOJI} {current_decks_used}", inline=True)
    embed.add_field(name="**__Last War Stats__**",
                    value=f"{FAME_EMOJI} {last_fame}\n{MULTIDECK_EMOJI} {last_decks_used}", inline=True)

    return embed