import aiohttp
import urllib.parse
import time
from typing import List, Tuple
from utils.helpers import sanitize_tag, CLASH_ROYALE_API_BASE_URL, CLASH_ROYALE_API_KEY

# Cache setup
cache = {}
CACHE_DURATION = 60  # Cache duration in seconds


def get_cache(key):
    if key in cache:
        data, timestamp = cache[key]
        if time.time() - timestamp < CACHE_DURATION:
            return data
    return None


def set_cache(key, data):
    cache[key] = (data, time.time())


async def get_last_fame(clan_tag: str, player_tag: str) -> str:
    cache_key = f"last_fame_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    fame = '0'

    log_type, log_data = await last_war_log(clan_tag)
    if log_data is None:
        return fame

    items = log_data.get('items', [])
    for item in items:
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        for participant in participants:
            for player in (
                    participant.get('clan', {}).get('participants', []) if 'clan' in participant else [
                        participant]):
                if player.get('tag') == player_tag:
                    fame = player.get('fame', '0')

    set_cache(cache_key, fame)
    return fame


async def get_current_fame(clan_tag: str, player_tag: str) -> str:
    cache_key = f"current_fame_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    fame = '0'

    log_type, log_data = await current_war_log(clan_tag)
    if log_data is None:
        return fame

    participants = log_data.get('clan', {}).get('participants', [])
    for participant in participants:
        if participant.get('tag') == player_tag:
            fame = participant.get('fame', '0')
            set_cache(cache_key, fame)
            return fame

    set_cache(cache_key, fame)
    return fame



async def is_new_player(clan_tag: str, player_tag: str) -> bool:
    player_tag = sanitize_tag(player_tag)

    # Fetch current clan members
    _, members = await get_current_clan_members(clan_tag)
    member_tags = {tag for tag, name in members}

    # If player is not in the current members, return False
    if player_tag not in member_tags:
        return False

    # Fetch members in the last war log
    warlog_members = await list_members_in_last_war_log(clan_tag)
    warlog_member_tags = {tag for tag, name in warlog_members}

    # Fetch members in the last river race log
    log_type, riverrace_log_data = await last_war_log(clan_tag)
    riverrace_member_tags = set()
    if riverrace_log_data:
        items = riverrace_log_data.get('items', [])
        for item in items:
            participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
            for participant in participants:
                player_list = participant.get('clan', {}).get('participants', []) if 'clan' in participant else [
                    participant]
                for player in player_list:
                    riverrace_member_tags.add(player.get('tag'))

    # Check if player is in the current members but not in warlog or riverrace logs
    if player_tag in member_tags:
        if player_tag not in warlog_member_tags and player_tag not in riverrace_member_tags:
            return True

    return False


async def get_current_clan_members(clan_tag: str) -> Tuple[str, List[Tuple[str, str]]]:
    cache_key = f"active_members_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {'Authorization': f'Bearer {CLASH_ROYALE_API_KEY}'}
    encoded_clan_tag = urllib.parse.quote(clan_tag, safe='')
    clan_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}'
    members_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}/members'

    async with aiohttp.ClientSession() as session:
        async with session.get(clan_url, headers=headers) as clan_response:
            clan_response.raise_for_status()
            clan_data = await clan_response.json()
            clan_name = clan_data['name']

        async with session.get(members_url, headers=headers, params={'limit': 50}) as members_response:
            members_response.raise_for_status()
            members_data = await members_response.json()

            members = [
                (member['tag'], member['name'])
                for member in members_data['items']
            ]

            result = (clan_name, members)
            set_cache(cache_key, result)
            return result


async def list_members_in_last_war_log(clan_tag: str) -> List[Tuple[str, str]]:
    cache_key = f"members_last_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    members_in_last_war = []

    log_type, log_data = await last_war_log(clan_tag)
    if log_data is None:
        set_cache(cache_key, members_in_last_war)
        return members_in_last_war

    items = log_data.get('items', [])
    for item in items:
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        for participant in participants:
            player_list = participant.get('clan', {}).get('participants', []) if 'clan' in participant else [
                participant]
            for player in player_list:
                members_in_last_war.append((player.get('tag'), player.get('name')))

    set_cache(cache_key, members_in_last_war)
    return members_in_last_war


async def get_role(clan_tag: str, member_tag: str) -> str:
    headers = {'Authorization': f'Bearer {CLASH_ROYALE_API_KEY}'}
    encoded_clan_tag = urllib.parse.quote(clan_tag, safe='')
    members_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}/members'

    async with aiohttp.ClientSession() as session:
        async with session.get(members_url, headers=headers, params={'limit': 50}) as members_response:
            members_response.raise_for_status()
            members_data = await members_response.json()

            for member in members_data['items']:
                if member['tag'] == member_tag:
                    return member['role']
            raise ValueError(f"Member with tag {member_tag} not found in clan {clan_tag}")


async def get_former_clan_members(clan_tag: str) -> List[Tuple[str, str]]:
    cache_key = f"former_members_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    # Fetch current clan members
    clan_name, current_members = await get_current_clan_members(clan_tag)
    current_member_tags = {tag for tag, name in current_members}

    # Fetch participants in the current war log
    log_type, log_data = await current_war_log(clan_tag)
    if log_data is None:
        set_cache(cache_key, [])
        return []

    participants = log_data.get('clan', {}).get('participants', [])
    former_members = []

    # Identify former clan members
    for participant in participants:
        if participant['tag'] not in current_member_tags:
            former_members.append((participant['tag'], participant['name']))

    set_cache(cache_key, former_members)
    return former_members


async def get_last_decks_used(clan_tag: str, player_tag: str) -> int:
    cache_key = f"last_decks_used_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data is not None:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    decks_used = 0

    log_type, log_data = await last_war_log(clan_tag)
    if log_data is None:
        set_cache(cache_key, decks_used)
        return decks_used

    items = log_data.get('items', [])
    for item in items:
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        for participant in participants:
            if log_type == 'riverracelog':
                for player in participant.get('clan', {}).get('participants', []):
                    if player.get('tag') == player_tag:
                        decks_used = player.get('decksUsed', 0)
                        set_cache(cache_key, decks_used)
                        return decks_used
            else:
                if participant.get('tag') == player_tag:
                    decks_used = participant.get('decksUsed', 0)
                    set_cache(cache_key, decks_used)
                    return decks_used

    set_cache(cache_key, decks_used)
    return decks_used


async def get_members_current_decks_used(clan_tag: str, player_tag: str) -> int:
    cache_key = f"decks_used_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data is not None:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    decks_used = 0

    log_type, log_data = await current_war_log(clan_tag)
    if log_data is None:
        set_cache(cache_key, decks_used)
        return decks_used

    participants = log_data.get('clan', {}).get('participants', [])
    for participant in participants:
        if participant.get('tag') == player_tag:
            decks_used = participant.get('decksUsed', 0)
            set_cache(cache_key, decks_used)
            return decks_used

    set_cache(cache_key, decks_used)
    return decks_used


async def last_war_log(clan_tag: str):
    cache_key = f"last_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/riverracelog?limit=1",
                               headers=headers) as response:
            if response.status == 200:
                result = ("riverracelog", await response.json())
                set_cache(cache_key, result)
                return result

        set_cache(cache_key, (None, None))
        return None, None


async def nth_war_log(clan_tag: str, n: int):
    cache_key = f"war_log_{clan_tag}_{n}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/riverracelog?limit={n}",
                               headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                if "items" in data and data["items"]:
                    # Find the entry with the smallest seasonId and sectionIndex
                    min_entry = min(data["items"], key=lambda x: (x["seasonId"], x["sectionIndex"]))
                    result = ("riverracelog", min_entry)
                    set_cache(cache_key, result)
                    return result

        set_cache(cache_key, (None, None))
        return None, None



async def get_fame_n_wars_ago(clan_tag: str, player_tag: str, n: int) -> str:
    cache_key = f"fame_{n}_wars_ago_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    player_tag = sanitize_tag(player_tag)
    fame = '0'

    log_type, log_data = await nth_war_log(clan_tag, n)
    if log_data is None:
        set_cache(cache_key, fame)
        return fame

    # Log data structure is different, so adjust code accordingly
    standings = log_data.get('standings', [])
    for standing in standings:
        clan = standing.get('clan', {})
        participants = clan.get('participants', [])
        for player in participants:
            if player.get('tag') == player_tag:
                fame = str(player.get('fame', '0'))
                set_cache(cache_key, fame)
                return fame

    set_cache(cache_key, fame)
    return fame

async def get_decks_used_n_wars_ago(clan_tag: str, player_tag: str, n: int) -> int:
    cache_key = f"decks_used_{n}_wars_ago_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return int(cached_data)

    player_tag = sanitize_tag(player_tag)
    decks_used = 0

    log_type, log_data = await nth_war_log(clan_tag, n)
    if log_data is None:
        set_cache(cache_key, decks_used)
        return decks_used

    standings = log_data.get('standings', [])
    for standing in standings:
        clan = standing.get('clan', {})
        participants = clan.get('participants', [])
        for player in participants:
            if player.get('tag') == player_tag:
                decks_used = player.get('decksUsed', 0)
                set_cache(cache_key, decks_used)
                return decks_used

    set_cache(cache_key, decks_used)
    return decks_used

async def current_war_log(clan_tag: str):
    cache_key = f"current_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/currentriverrace",
                               headers=headers) as response:
            if response.status == 200:
                result = ("currentriverrace", await response.json())
                set_cache(cache_key, result)
                return result

        set_cache(cache_key, (None, None))
        return None, None

async def get_player_info(player_tag: str) -> dict:
    url = f"{CLASH_ROYALE_API_BASE_URL}/players/%23{player_tag}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}) as response:
            return await response.json() if response.status == 200 else None


async def get_player_trophies(player_tag: str) -> int:
    player_info = await get_player_info(player_tag)
    return player_info['trophies'] if player_info else 0


async def get_player_best_trophies(player_tag: str) -> int:
    player_info = await get_player_info(player_tag)
    return player_info['bestTrophies'] if player_info else 0


async def get_player_path_of_legends_info(player_tag: str) -> dict:
    player_info = await get_player_info(player_tag)
    return {
        'current': player_info.get('currentPathOfLegendSeasonResult', {}),
        'best': player_info.get('bestPathOfLegendSeasonResult', {})
    } if player_info else {}


async def get_player_cards(player_tag: str) -> list:
    player_info = await get_player_info(player_tag)
    return player_info.get('cards', []) if player_info else []


async def get_player_badges(player_tag: str) -> list:
    player_info = await get_player_info(player_tag)
    return player_info.get('badges', []) if player_info else []


async def get_player_clan_info(player_tag: str) -> dict:
    player_info = await get_player_info(player_tag)
    return player_info.get('clan', {}) if player_info else {}


async def get_player_role(player_tag: str) -> str:  #Fetch the player's role within their clan.
    player_info = await get_player_info(player_tag)
    return player_info.get('role', '') if player_info else ''


async def is_real_clan_tag(clan_tag: str) -> bool:
    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = sanitize_tag(clan_tag)
    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{sanitized_tag}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            return response.status == 200


from typing import List, Tuple
import aiohttp

async def get_decks_used_today(clan_tag: str) -> List[Tuple[str, str, int]]:
    cache_key = f"decks_used_today_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = sanitize_tag(clan_tag)

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{sanitized_tag}/currentriverrace", headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                participants = data.get('clan', {}).get('participants', [])
                decks_used_today = [
                    (participant['tag'], participant['name'], participant['decksUsedToday'])
                    for participant in participants
                ]
                set_cache(cache_key, decks_used_today)
                return decks_used_today

    set_cache(cache_key, [])
    return []

from typing import List, Tuple
import urllib.parse
import aiohttp

async def get_tournament_info(tournament_tag: str) -> Tuple[str, List[Tuple[str, int, int]]]:
    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = urllib.parse.quote(tournament_tag, safe='')
    url = f"{CLASH_ROYALE_API_BASE_URL}/tournaments/%23{sanitized_tag}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                tournament_name = data.get('name', 'Unknown Tournament')
                members_info = [
                    (participant['name'], participant['score'], participant['rank'])
                    for participant in data.get('membersList', [])
                ]
                return tournament_name, members_info

    return "Unknown Tournament", []