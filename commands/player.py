import asyncio
import aiohttp
import discord
from discord import Interaction
from utils.helpers import sanitize_tag, LEVEL_EMOJIS, EMOJI_TROPHYROAD, EVOLUTION_EMOJI, LEVEL_15_EMOJI, LEVEL_14_EMOJI, \
    LEVEL_13_EMOJI, CW2_EMOJI, CC_EMOJI, GC_EMOJI, FAME_EMOJI, MULTIDECK_EMOJI, POLMEDAL_EMOJI, LEAGUE_IMAGES, \
    get_player_tag_from_mention
from utils.api import get_player_trophies, get_player_clan_info, get_player_badges, get_player_cards, \
    get_player_best_trophies, get_player_info, get_player_path_of_legends_info, get_current_fame, get_last_fame, \
    get_members_current_decks_used, get_last_decks_used


async def handle_player_command(interaction: Interaction, user_or_tag: str):
    player_tag = user_or_tag.lstrip('#').upper() if not user_or_tag.startswith('<@') else get_player_tag_from_mention(
        user_or_tag, str(interaction.guild.id))

    if not player_tag:
        await interaction.response.send_message("Player not found or user doesn't have a linked Clash Royale account.",
                                                ephemeral=True)
        return

    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        try:
            trophies = await get_player_trophies(player_tag)
            tasks = [
                get_player_info(player_tag),
                get_player_trophies(player_tag),
                get_player_best_trophies(player_tag),
                get_player_cards(player_tag),
                get_player_badges(player_tag),
                get_player_clan_info(player_tag),
            ]

            if trophies >= 5000:
                tasks.append(get_player_path_of_legends_info(player_tag))

            results = await asyncio.gather(*tasks)
            if not results[0]:  # player_info
                await interaction.followup.send("Player not found. Please check the tag and try again.")
                return

            handle_function = handle_5000_or_above if trophies >= 5000 else handle_below_5000
            await handle_function(interaction, results)

        except asyncio.TimeoutError:
            await interaction.followup.send("Sorry, it's taking too long to gather the data. Please try again later.")
        except aiohttp.ClientError:
            await interaction.followup.send("Network error occurred. Please try again later.")
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {str(e)}")


async def handle_below_5000(interaction, results):
    await handle_player_data(interaction, results, False)


async def handle_5000_or_above(interaction, results):
    await handle_player_data(interaction, results, True)


async def handle_player_data(interaction, results, above_5000):
    player_info, trophies, best_trophies, cards, badges, clan_tag = results[:6]
    pol_info = results[6] if above_5000 else None

    nohash_clan_tag = clan_tag.get('tag', '').strip('#')
    player_tag = player_info.get('tag', '')

    current_fame, last_fame, current_decks_used, last_decks_used = await asyncio.gather(
        get_current_fame(nohash_clan_tag, player_tag),
        get_last_fame(nohash_clan_tag, player_tag),
        get_members_current_decks_used(nohash_clan_tag, player_tag),
        get_last_decks_used(nohash_clan_tag, player_tag),
    )

    embed = create_player_embed(player_info, player_tag, trophies, best_trophies, cards, badges, clan_tag,
                                current_fame or 0, current_decks_used or 0, last_fame or 0, last_decks_used or 0,
                                pol_info, above_5000)

    await interaction.followup.send(embed=embed)


def create_player_embed(player_info, player_tag, trophies, best_trophies, cards, badges, clan_tag,
                        current_fame, current_decks_used, last_fame, last_decks_used, pol_info, above_5000):
    embed = discord.Embed(
        title=f"{player_info['name']} {player_tag} {LEVEL_EMOJIS.get(player_info['expLevel'], '')}",
        color=0x1E133E,
        url=f"https://royaleapi.com/player/{player_info['tag'].strip('#').upper()}"
    )

    # Clan Info
    if clan_tag:
        clan_name = clan_tag.get('name', 'No Clan')
        nohash_clan_tag = clan_tag.get('tag', '').strip('#')
        clan_url = f"https://royaleapi.com/clan/{nohash_clan_tag}"
        clan_link = f"[{clan_name}](<{clan_url}>)"
        role = player_info.get('role', '').capitalize()
        embed.add_field(name="**__Clan__**", value=f"{clan_link} #{nohash_clan_tag} ({role})", inline=True)
    else:
        embed.add_field(name="**__Clan__**", value='No Clan', inline=True)

    # Trophy Road Info
    embed.add_field(name="**__Trophy Road__**",
                    value=f"Current: {EMOJI_TROPHYROAD} {trophies}\nBest: {EMOJI_TROPHYROAD} {best_trophies}",
                    inline=False)

    # Card Levels Info
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

    # Path of Legends Info (for players above 5000 trophies)
    if above_5000 and pol_info:
        pol_current_display = format_pol_entry(pol_info['current'])
        pol_best_display = format_pol_entry(pol_info['best'])
        embed.add_field(name="**__Path of Legends__**",
                        value=f"Current: {pol_current_display}\nBest: {pol_best_display}", inline=False)
        current_league = pol_info['current'].get('leagueNumber')
        if current_league in LEAGUE_IMAGES:
            embed.set_thumbnail(url=LEAGUE_IMAGES[current_league])

    # War Stats
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
