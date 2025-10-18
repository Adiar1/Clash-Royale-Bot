import urllib.parse
import time
from utils.helpers import sanitize_tag, CLASH_ROYALE_API_BASE_URL, CLASH_ROYALE_API_KEY
import urllib.parse
from utils.helpers import DECK_AI_API_KEY, DECK_AI_API_BASE_URL
import aiohttp
from typing import List, Tuple

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
    print(f"DEBUG get_last_fame: Called with clan_tag={clan_tag}, player_tag={player_tag}")

    cache_key = f"last_fame_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_last_fame: Returning cached data for {player_tag}: {cached_data}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_last_fame: Sanitized player_tag: {player_tag}")
    fame = '0'

    print(f"DEBUG get_last_fame: Calling last_war_log for clan {clan_tag}")
    log_type, log_data = await last_war_log(clan_tag)
    print(f"DEBUG get_last_fame: last_war_log returned log_type={log_type}, data_available={log_data is not None}")

    if log_data is None:
        print(f"DEBUG get_last_fame: No log data available, returning default fame: {fame}")
        return fame

    items = log_data.get('items', [])
    print(f"DEBUG get_last_fame: Processing {len(items)} war log items")

    for i, item in enumerate(items):
        print(f"DEBUG get_last_fame: Processing item {i + 1}")
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        print(f"DEBUG get_last_fame: Found {len(participants)} participants in item {i + 1}")

        for j, participant in enumerate(participants):
            player_list = participant.get('clan', {}).get('participants', []) if 'clan' in participant else [
                participant]
            for k, player in enumerate(player_list):
                if player.get('tag') == player_tag:
                    fame = player.get('fame', '0')
                    print(f"DEBUG get_last_fame: Found player {player_tag}, fame: {fame}")
                    set_cache(cache_key, fame)
                    return fame

    print(f"DEBUG get_last_fame: Player {player_tag} not found in war log, returning default fame: {fame}")
    set_cache(cache_key, fame)
    return fame


async def get_current_fame(clan_tag: str, player_tag: str) -> str:
    print(f"DEBUG get_current_fame: Called with clan_tag={clan_tag}, player_tag={player_tag}")

    cache_key = f"current_fame_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_current_fame: Returning cached data for {player_tag}: {cached_data}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_current_fame: Sanitized player_tag: {player_tag}")
    fame = '0'

    print(f"DEBUG get_current_fame: Calling current_war_log for clan {clan_tag}")
    log_type, log_data = await current_war_log(clan_tag)
    print(
        f"DEBUG get_current_fame: current_war_log returned log_type={log_type}, data_available={log_data is not None}")

    if log_data is None:
        print(f"DEBUG get_current_fame: No log data available, returning default fame: {fame}")
        return fame

    participants = log_data.get('clan', {}).get('participants', [])
    print(f"DEBUG get_current_fame: Processing {len(participants)} participants")

    for participant in participants:
        if participant.get('tag') == player_tag:
            fame = participant.get('fame', '0')
            print(f"DEBUG get_current_fame: Found player {player_tag}, fame: {fame}")
            set_cache(cache_key, fame)
            return fame

    print(f"DEBUG get_current_fame: Player {player_tag} not found in current war, returning default fame: {fame}")
    set_cache(cache_key, fame)
    return fame


async def is_new_player(clan_tag: str, player_tag: str) -> bool:
    print(f"DEBUG is_new_player: Called with clan_tag={clan_tag}, player_tag={player_tag}")
    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG is_new_player: Sanitized player_tag: {player_tag}")

    # Get weeks ago joined for all members
    print(f"DEBUG is_new_player: Getting weeks ago joined for clan {clan_tag}")
    member_weeks = await get_weeks_ago_joined(clan_tag)
    print(f"DEBUG is_new_player: Retrieved weeks data for {len(member_weeks)} members")

    # Find the player in the member_weeks list
    for member_tag, member_name, weeks_ago in member_weeks:
        if member_tag == player_tag:
            # If weeks_ago is 0, the player is new
            is_new = weeks_ago == 0
            print(f"DEBUG is_new_player: Player {player_tag} found, weeks_ago: {weeks_ago}, is_new: {is_new}")
            return is_new

    # If the player is not found in the list, they're not in the clan
    print(f"DEBUG is_new_player: Player {player_tag} not found in clan {clan_tag}")
    return False


async def get_current_clan_members(clan_tag: str) -> Tuple[str, List[Tuple[str, str]]]:
    print(f"DEBUG get_current_clan_members: Called with clan_tag={clan_tag}")

    cache_key = f"active_members_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_current_clan_members: Returning cached data for clan {clan_tag}")
        return cached_data

    headers = {'Authorization': f'Bearer {CLASH_ROYALE_API_KEY}'}
    encoded_clan_tag = urllib.parse.quote(clan_tag, safe='')
    print(f"DEBUG get_current_clan_members: Encoded clan tag: {encoded_clan_tag}")

    clan_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}'
    members_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}/members'

    print(f"DEBUG get_current_clan_members: Clan API URL: {clan_url}")
    print(f"DEBUG get_current_clan_members: Members API URL: {members_url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(clan_url, headers=headers) as clan_response:
            print(f"DEBUG get_current_clan_members: Clan API response status: {clan_response.status}")
            clan_response.raise_for_status()
            clan_data = await clan_response.json()
            clan_name = clan_data['name']
            print(f"DEBUG get_current_clan_members: Retrieved clan name: {clan_name}")

        async with session.get(members_url, headers=headers, params={'limit': 50}) as members_response:
            print(f"DEBUG get_current_clan_members: Members API response status: {members_response.status}")
            members_response.raise_for_status()
            members_data = await members_response.json()

            members = [
                (member['tag'], member['name'])
                for member in members_data['items']
            ]
            print(f"DEBUG get_current_clan_members: Retrieved {len(members)} members")

            result = (clan_name, members)
            set_cache(cache_key, result)
            return result


async def list_members_in_last_war_log(clan_tag: str) -> List[Tuple[str, str]]:
    print(f"DEBUG list_members_in_last_war_log: Called with clan_tag={clan_tag}")

    cache_key = f"members_last_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG list_members_in_last_war_log: Returning cached data for clan {clan_tag}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    members_in_last_war = []

    print(f"DEBUG list_members_in_last_war_log: Getting last war log for clan {clan_tag}")
    log_type, log_data = await last_war_log(clan_tag)
    print(f"DEBUG list_members_in_last_war_log: Log type: {log_type}, data available: {log_data is not None}")

    if log_data is None:
        print(f"DEBUG list_members_in_last_war_log: No log data, returning empty list")
        set_cache(cache_key, members_in_last_war)
        return members_in_last_war

    items = log_data.get('items', [])
    print(f"DEBUG list_members_in_last_war_log: Processing {len(items)} war log items")

    for item in items:
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        for participant in participants:
            player_list = participant.get('clan', {}).get('participants', []) if 'clan' in participant else [
                participant]
            for player in player_list:
                members_in_last_war.append((player.get('tag'), player.get('name')))

    print(f"DEBUG list_members_in_last_war_log: Found {len(members_in_last_war)} members in last war")
    set_cache(cache_key, members_in_last_war)
    return members_in_last_war


async def get_role(clan_tag: str, member_tag: str) -> str:
    print(f"DEBUG get_role: Called with clan_tag={clan_tag}, member_tag={member_tag}")

    headers = {'Authorization': f'Bearer {CLASH_ROYALE_API_KEY}'}
    encoded_clan_tag = urllib.parse.quote(clan_tag, safe='')
    members_url = f'{CLASH_ROYALE_API_BASE_URL}/clans/%23{encoded_clan_tag}/members'

    print(f"DEBUG get_role: Members API URL: {members_url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(members_url, headers=headers, params={'limit': 50}) as members_response:
            print(f"DEBUG get_role: API response status: {members_response.status}")
            members_response.raise_for_status()
            members_data = await members_response.json()

            for member in members_data['items']:
                if member['tag'] == member_tag:
                    role = member['role']
                    print(f"DEBUG get_role: Found member {member_tag}, role: {role}")
                    return role

            print(f"DEBUG get_role: Member {member_tag} not found in clan {clan_tag}")
            raise ValueError(f"Member with tag {member_tag} not found in clan {clan_tag}")


async def get_former_clan_members(clan_tag: str) -> List[Tuple[str, str]]:
    print(f"DEBUG get_former_clan_members: Called with clan_tag={clan_tag}")

    cache_key = f"former_members_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_former_clan_members: Returning cached data for clan {clan_tag}")
        return cached_data

    # Fetch current clan members
    print(f"DEBUG get_former_clan_members: Getting current clan members for {clan_tag}")
    clan_name, current_members = await get_current_clan_members(clan_tag)
    current_member_tags = {tag for tag, name in current_members}
    print(f"DEBUG get_former_clan_members: Current members count: {len(current_member_tags)}")

    # Fetch participants in the current war log
    print(f"DEBUG get_former_clan_members: Getting current war log for {clan_tag}")
    log_type, log_data = await current_war_log(clan_tag)
    print(f"DEBUG get_former_clan_members: Log type: {log_type}, data available: {log_data is not None}")

    if log_data is None:
        print(f"DEBUG get_former_clan_members: No current war data, returning empty list")
        set_cache(cache_key, [])
        return []

    participants = log_data.get('clan', {}).get('participants', [])
    former_members = []
    print(f"DEBUG get_former_clan_members: Processing {len(participants)} participants from current war")

    # Identify former clan members
    for participant in participants:
        if participant['tag'] not in current_member_tags:
            former_members.append((participant['tag'], participant['name']))
            print(f"DEBUG get_former_clan_members: Found former member: {participant['name']} ({participant['tag']})")

    print(f"DEBUG get_former_clan_members: Found {len(former_members)} former members")
    set_cache(cache_key, former_members)
    return former_members


async def get_last_decks_used(clan_tag: str, player_tag: str) -> int:
    print(f"DEBUG get_last_decks_used: Called with clan_tag={clan_tag}, player_tag={player_tag}")

    cache_key = f"last_decks_used_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data is not None:
        print(f"DEBUG get_last_decks_used: Returning cached data for {player_tag}: {cached_data}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_last_decks_used: Sanitized player_tag: {player_tag}")
    decks_used = 0

    print(f"DEBUG get_last_decks_used: Getting last war log for clan {clan_tag}")
    log_type, log_data = await last_war_log(clan_tag)
    print(f"DEBUG get_last_decks_used: Log type: {log_type}, data available: {log_data is not None}")

    if log_data is None:
        print(f"DEBUG get_last_decks_used: No log data, returning default decks_used: {decks_used}")
        set_cache(cache_key, decks_used)
        return decks_used

    items = log_data.get('items', [])
    print(f"DEBUG get_last_decks_used: Processing {len(items)} war log items")

    for item in items:
        participants = item.get('standings', []) if log_type == 'riverracelog' else item.get('participants', [])
        for participant in participants:
            if log_type == 'riverracelog':
                for player in participant.get('clan', {}).get('participants', []):
                    if player.get('tag') == player_tag:
                        decks_used = player.get('decksUsed', 0)
                        print(f"DEBUG get_last_decks_used: Found player {player_tag}, decks_used: {decks_used}")
                        set_cache(cache_key, decks_used)
                        return decks_used
            else:
                if participant.get('tag') == player_tag:
                    decks_used = participant.get('decksUsed', 0)
                    print(f"DEBUG get_last_decks_used: Found player {player_tag}, decks_used: {decks_used}")
                    set_cache(cache_key, decks_used)
                    return decks_used

    print(f"DEBUG get_last_decks_used: Player {player_tag} not found, returning default decks_used: {decks_used}")
    set_cache(cache_key, decks_used)
    return decks_used


async def get_members_current_decks_used(clan_tag: str, player_tag: str) -> int:
    print(f"DEBUG get_members_current_decks_used: Called with clan_tag={clan_tag}, player_tag={player_tag}")

    cache_key = f"decks_used_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data is not None:
        print(f"DEBUG get_members_current_decks_used: Returning cached data for {player_tag}: {cached_data}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_members_current_decks_used: Sanitized player_tag: {player_tag}")
    decks_used = 0

    print(f"DEBUG get_members_current_decks_used: Getting current war log for clan {clan_tag}")
    log_type, log_data = await current_war_log(clan_tag)
    print(f"DEBUG get_members_current_decks_used: Log type: {log_type}, data available: {log_data is not None}")

    if log_data is None:
        print(f"DEBUG get_members_current_decks_used: No log data, returning default decks_used: {decks_used}")
        set_cache(cache_key, decks_used)
        return decks_used

    participants = log_data.get('clan', {}).get('participants', [])
    print(f"DEBUG get_members_current_decks_used: Processing {len(participants)} participants")

    for participant in participants:
        if participant.get('tag') == player_tag:
            decks_used = participant.get('decksUsed', 0)
            print(f"DEBUG get_members_current_decks_used: Found player {player_tag}, decks_used: {decks_used}")
            set_cache(cache_key, decks_used)
            return decks_used

    print(
        f"DEBUG get_members_current_decks_used: Player {player_tag} not found, returning default decks_used: {decks_used}")
    set_cache(cache_key, decks_used)
    return decks_used


async def last_war_log(clan_tag: str):
    print(f"DEBUG last_war_log: Called with clan_tag={clan_tag}")

    cache_key = f"last_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG last_war_log: Returning cached data for clan {clan_tag}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/riverracelog?limit=1"
    print(f"DEBUG last_war_log: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG last_war_log: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                result = ("riverracelog", data)
                print(f"DEBUG last_war_log: Successfully retrieved river race log for clan {clan_tag}")
                set_cache(cache_key, result)
                return result
            else:
                error_text = await response.text()
                print(f"DEBUG last_war_log: API error {response.status}: {error_text}")

        print(f"DEBUG last_war_log: Failed to get data for clan {clan_tag}, returning None")
        set_cache(cache_key, (None, None))
        return None, None


async def nth_war_log(clan_tag: str, n: int):
    print(f"DEBUG nth_war_log: Called with clan_tag={clan_tag}, n={n}")

    cache_key = f"war_log_{clan_tag}_{n}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG nth_war_log: Returning cached data for clan {clan_tag}, n={n}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/riverracelog?limit={n}"
    print(f"DEBUG nth_war_log: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG nth_war_log: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                if "items" in data and data["items"]:
                    # Find the entry with the smallest seasonId and sectionIndex
                    min_entry = min(data["items"], key=lambda x: (x["seasonId"], x["sectionIndex"]))
                    result = ("riverracelog", min_entry)
                    print(f"DEBUG nth_war_log: Successfully retrieved nth war log for clan {clan_tag}, n={n}")
                    set_cache(cache_key, result)
                    return result
                else:
                    print(f"DEBUG nth_war_log: No items found in response for clan {clan_tag}, n={n}")
            else:
                error_text = await response.text()
                print(f"DEBUG nth_war_log: API error {response.status}: {error_text}")

        print(f"DEBUG nth_war_log: Failed to get data for clan {clan_tag}, n={n}, returning None")
        set_cache(cache_key, (None, None))
        return None, None


async def get_fame_n_wars_ago(clan_tag: str, player_tag: str, n: int) -> str:
    print(f"DEBUG get_fame_n_wars_ago: Called with clan_tag={clan_tag}, player_tag={player_tag}, n={n}")

    cache_key = f"fame_{n}_wars_ago_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_fame_n_wars_ago: Returning cached data: {cached_data}")
        return cached_data

    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_fame_n_wars_ago: Sanitized player_tag: {player_tag}")
    fame = '0'

    log_type, log_data = await nth_war_log(clan_tag, n)
    if log_data is None:
        print(f"DEBUG get_fame_n_wars_ago: No log data, returning default fame: {fame}")
        set_cache(cache_key, fame)
        return fame

    # Log data structure is different, so adjust code accordingly
    standings = log_data.get('standings', [])
    print(f"DEBUG get_fame_n_wars_ago: Processing {len(standings)} standings")

    for standing in standings:
        clan = standing.get('clan', {})
        participants = clan.get('participants', [])
        for player in participants:
            if player.get('tag') == player_tag:
                fame = str(player.get('fame', '0'))
                print(f"DEBUG get_fame_n_wars_ago: Found player {player_tag}, fame: {fame}")
                set_cache(cache_key, fame)
                return fame

    print(f"DEBUG get_fame_n_wars_ago: Player {player_tag} not found, returning default fame: {fame}")
    set_cache(cache_key, fame)
    return fame


async def get_decks_used_n_wars_ago(clan_tag: str, player_tag: str, n: int) -> int:
    print(f"DEBUG get_decks_used_n_wars_ago: Called with clan_tag={clan_tag}, player_tag={player_tag}, n={n}")

    cache_key = f"decks_used_{n}_wars_ago_{clan_tag}_{player_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_decks_used_n_wars_ago: Returning cached data: {cached_data}")
        return int(cached_data)

    player_tag = sanitize_tag(player_tag)
    print(f"DEBUG get_decks_used_n_wars_ago: Sanitized player_tag: {player_tag}")
    decks_used = 0

    log_type, log_data = await nth_war_log(clan_tag, n)
    if log_data is None:
        print(f"DEBUG get_decks_used_n_wars_ago: No log data, returning default decks_used: {decks_used}")
        set_cache(cache_key, decks_used)
        return decks_used

    standings = log_data.get('standings', [])
    print(f"DEBUG get_decks_used_n_wars_ago: Processing {len(standings)} standings")

    for standing in standings:
        clan = standing.get('clan', {})
        participants = clan.get('participants', [])
        for player in participants:
            if player.get('tag') == player_tag:
                decks_used = player.get('decksUsed', 0)
                print(f"DEBUG get_decks_used_n_wars_ago: Found player {player_tag}, decks_used: {decks_used}")
                set_cache(cache_key, decks_used)
                return decks_used

    print(f"DEBUG get_decks_used_n_wars_ago: Player {player_tag} not found, returning default decks_used: {decks_used}")
    set_cache(cache_key, decks_used)
    return decks_used


async def get_weeks_ago_joined(clan_tag: str) -> List[Tuple[str, str, int]]:
    print(f"DEBUG get_weeks_ago_joined: Called with clan_tag={clan_tag}")

    # Get the current clan members
    _, current_members = await get_current_clan_members(clan_tag)
    print(f"DEBUG get_weeks_ago_joined: Processing {len(current_members)} current members")
    member_weeks = []

    # Check each member against past war logs
    for i, (member_tag, member_name) in enumerate(current_members):
        print(
            f"DEBUG get_weeks_ago_joined: Processing member {i + 1}/{len(current_members)}: {member_name} ({member_tag})")
        weeks_ago = 0
        found_in_log = True

        # Check presence in nth war logs
        for n in range(1, 11):
            if not found_in_log:
                break

            _, nth_log = await nth_war_log(clan_tag, n)
            if nth_log is None:
                print(f"DEBUG get_weeks_ago_joined: No log data for n={n}, breaking")
                break

            standings = nth_log.get('standings', [])
            participant_tags = {
                player.get('tag')
                for standing in standings
                for player in standing.get('clan', {}).get('participants', [])
            }

            if member_tag not in participant_tags:
                found_in_log = False
                print(f"DEBUG get_weeks_ago_joined: Member {member_tag} not found in war n={n}, weeks_ago={weeks_ago}")
            else:
                weeks_ago = n

        member_weeks.append((member_tag, member_name, weeks_ago))
        print(f"DEBUG get_weeks_ago_joined: Final result for {member_tag}: weeks_ago={weeks_ago}")

    print(f"DEBUG get_weeks_ago_joined: Completed processing, returning {len(member_weeks)} results")
    return member_weeks


async def get_average_fame_for_members(clan_tag: str):
    print(f"DEBUG get_average_fame_for_members: Called with clan_tag={clan_tag}")

    # Get the current clan members
    _, current_members = await get_current_clan_members(clan_tag)
    member_averages = []

    # Get weeks ago joined for all members at once
    member_weeks = await get_weeks_ago_joined(clan_tag)

    # Create a dictionary for quick lookup of weeks ago
    weeks_dict = {tag: weeks for tag, name, weeks in member_weeks}

    # Calculate the average fame for each member
    for member_tag, member_name in current_members:
        max_n = weeks_dict.get(member_tag, 0)

        if max_n == 0:
            # If max_n is 0, the member has no recorded fame
            member_averages.append((member_name, 0))
            continue

        total_fame = 0.0  # Ensure total_fame is a float to handle division

        # Get fame for each week up to max_n
        for n in range(1, max_n + 1):
            fame = await get_fame_n_wars_ago(clan_tag, member_tag, n)
            if fame is not None:
                total_fame += float(fame)  # Convert fame to float

        # Calculate average fame
        if max_n > 0:
            average_fame = total_fame / max_n
        else:
            average_fame = 0

        member_averages.append((member_name, average_fame))

    return member_averages


async def current_war_log(clan_tag: str):
    print(f"DEBUG current_war_log: Called with clan_tag={clan_tag}")

    cache_key = f"current_war_log_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG current_war_log: Returning cached data for clan {clan_tag}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{clan_tag}/currentriverrace"
    print(f"DEBUG current_war_log: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG current_war_log: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                result = ("currentriverrace", data)
                print(f"DEBUG current_war_log: Successfully retrieved current river race for clan {clan_tag}")
                set_cache(cache_key, result)
                return result
            else:
                error_text = await response.text()
                print(f"DEBUG current_war_log: API error {response.status}: {error_text}")

        print(f"DEBUG current_war_log: Failed to get data for clan {clan_tag}, returning None")
        set_cache(cache_key, (None, None))
        return None, None


async def get_player_info(player_tag: str) -> dict:
    url = f"{CLASH_ROYALE_API_BASE_URL}/players/%23{player_tag}"
    print(f"DEBUG get_player_info: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}) as response:
            print(f"DEBUG get_player_info: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                print(f"DEBUG get_player_info: Successfully retrieved player info for {player_tag}")
                return data
            else:
                error_text = await response.text()
                print(f"DEBUG get_player_info: API error {response.status}: {error_text}")
                return None


async def get_player_trophies(player_tag: str, player_info: dict = None) -> int:
    print(f"DEBUG get_player_trophies: Called with player_tag={player_tag}")

    if not player_info:
        player_info = await get_player_info(player_tag)

    if not player_info:
        print(f"DEBUG get_player_trophies: No player info found")
        return 0

    trophies = player_info.get('trophies', 0)

    # If trophies are at max (10000), check for seasonal trophies
    if trophies == 10000:
        progress = player_info.get('progress', {})
        # Find the seasonal trophy road entry (key starts with "seasonal-trophy-road-")
        for key, value in progress.items():
            if key.startswith('seasonal-trophy-road-'):
                seasonal_trophies = value.get('trophies', 0)
                print(f"DEBUG get_player_trophies: Found seasonal trophies for {player_tag}: {seasonal_trophies}")
                return seasonal_trophies

    print(f"DEBUG get_player_trophies: Player {player_tag} trophies: {trophies}")
    return trophies


async def get_player_best_trophies(player_tag: str, player_info: dict = None) -> int:
    print(f"DEBUG get_player_best_trophies: Called with player_tag={player_tag}")

    if not player_info:
        player_info = await get_player_info(player_tag)

    if not player_info:
        print(f"DEBUG get_player_best_trophies: No player info found")
        return 0

    best_trophies = player_info.get('bestTrophies', 0)

    # If best trophies are at max (10000), check for seasonal best trophies
    if best_trophies == 10000:
        progress = player_info.get('progress', {})
        # Find the seasonal trophy road entry (key starts with "seasonal-trophy-road-")
        for key, value in progress.items():
            if key.startswith('seasonal-trophy-road-'):
                seasonal_best_trophies = value.get('bestTrophies', 0)
                print(
                    f"DEBUG get_player_best_trophies: Found seasonal best trophies for {player_tag}: {seasonal_best_trophies}")
                return seasonal_best_trophies

    print(f"DEBUG get_player_best_trophies: Player {player_tag} best trophies: {best_trophies}")
    return best_trophies


async def get_player_path_of_legends_info(player_tag: str) -> dict:
    print(f"DEBUG get_player_path_of_legends_info: Called with player_tag={player_tag}")
    player_info = await get_player_info(player_tag)
    ranked_info = {
        'current': player_info.get('currentPathOfLegendSeasonResult', {}),
        'best': player_info.get('bestPathOfLegendSeasonResult', {})
    } if player_info else {}
    print(f"DEBUG get_player_path_of_legends_info: Retrieved ranked info for {player_tag}")
    return ranked_info


async def get_player_cards(player_tag: str) -> list:
    print(f"DEBUG get_player_cards: Called with player_tag={player_tag}")
    player_info = await get_player_info(player_tag)
    cards = player_info.get('cards', []) if player_info else []
    print(f"DEBUG get_player_cards: Player {player_tag} has {len(cards)} cards")
    return cards


async def get_player_badges(player_tag: str) -> list:
    print(f"DEBUG get_player_badges: Called with player_tag={player_tag}")
    player_info = await get_player_info(player_tag)
    badges = player_info.get('badges', []) if player_info else []
    print(f"DEBUG get_player_badges: Player {player_tag} has {len(badges)} badges")
    return badges


async def get_player_clan_info(player_tag: str) -> dict:
    print(f"DEBUG get_player_clan_info: Called with player_tag={player_tag}")
    player_info = await get_player_info(player_tag)
    clan_info = player_info.get('clan', {}) if player_info else {}
    print(f"DEBUG get_player_clan_info: Retrieved clan info for {player_tag}")
    return clan_info


async def get_player_role(player_tag: str) -> str:  # Fetch the player's role within their clan.
    print(f"DEBUG get_player_role: Called with player_tag={player_tag}")
    player_info = await get_player_info(player_tag)
    role = player_info.get('role', '') if player_info else ''
    print(f"DEBUG get_player_role: Player {player_tag} role: {role}")
    return role


async def is_real_clan_tag(clan_tag: str) -> bool:
    print(f"DEBUG is_real_clan_tag: Called with clan_tag={clan_tag}")

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = sanitize_tag(clan_tag)
    print(f"DEBUG is_real_clan_tag: Sanitized clan tag: {sanitized_tag}")

    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{sanitized_tag}"
    print(f"DEBUG is_real_clan_tag: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG is_real_clan_tag: API response status: {response.status}")
            is_real = response.status == 200
            print(f"DEBUG is_real_clan_tag: Clan tag {clan_tag} is real: {is_real}")
            return is_real


async def get_decks_used_today(clan_tag: str) -> List[Tuple[str, str, int]]:
    print(f"DEBUG get_decks_used_today: Called with clan_tag={clan_tag}")

    cache_key = f"decks_used_today_{clan_tag}"
    cached_data = get_cache(cache_key)
    if cached_data:
        print(f"DEBUG get_decks_used_today: Returning cached data for clan {clan_tag}")
        return cached_data

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = sanitize_tag(clan_tag)
    print(f"DEBUG get_decks_used_today: Sanitized clan tag: {sanitized_tag}")

    url = f"{CLASH_ROYALE_API_BASE_URL}/clans/%23{sanitized_tag}/currentriverrace"
    print(f"DEBUG get_decks_used_today: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG get_decks_used_today: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                participants = data.get('clan', {}).get('participants', [])
                decks_used_today = [
                    (participant['tag'], participant['name'], participant['decksUsedToday'])
                    for participant in participants
                ]
                print(f"DEBUG get_decks_used_today: Retrieved data for {len(decks_used_today)} participants")
                set_cache(cache_key, decks_used_today)
                return decks_used_today
            else:
                error_text = await response.text()
                print(f"DEBUG get_decks_used_today: API error {response.status}: {error_text}")

    print(f"DEBUG get_decks_used_today: Failed to get data for clan {clan_tag}, returning empty list")
    set_cache(cache_key, [])
    return []


async def get_tournament_info(tournament_tag: str) -> Tuple[str, List[Tuple[str, int, int]]]:
    print(f"DEBUG get_tournament_info: Called with tournament_tag={tournament_tag}")

    headers = {"Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"}
    sanitized_tag = urllib.parse.quote(tournament_tag, safe='')
    url = f"{CLASH_ROYALE_API_BASE_URL}/tournaments/%23{sanitized_tag}"
    print(f"DEBUG get_tournament_info: API URL: {url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            print(f"DEBUG get_tournament_info: API response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                tournament_name = data.get('name', 'Unknown Tournament')
                members_info = [
                    (participant['name'], participant['score'], participant['rank'])
                    for participant in data.get('membersList', [])
                ]
                print(
                    f"DEBUG get_tournament_info: Retrieved tournament {tournament_name} with {len(members_info)} participants")
                return tournament_name, members_info
            else:
                error_text = await response.text()
                print(f"DEBUG get_tournament_info: API error {response.status}: {error_text}")

    print(f"DEBUG get_tournament_info: Failed to get tournament info for {tournament_tag}")
    return "Unknown Tournament", []


async def get_clan_war_spy_info(account_id: str, opponent_player_tag: str) -> dict:
    print(
        f"DEBUG get_clan_war_spy_info: Called with account_id={account_id}, opponent_player_tag={opponent_player_tag}")

    # Validate inputs
    if not account_id:
        print("DEBUG get_clan_war_spy_info: Error - account_id is None or empty")
        return {}

    if not opponent_player_tag:
        print("DEBUG get_clan_war_spy_info: Error - opponent_player_tag is None or empty")
        return {}

    # Check if API key is available
    if not DECK_AI_API_KEY:
        print("DEBUG get_clan_war_spy_info: Error - DECK_AI_API_KEY is not set in environment variables")
        return {}

    # Try with the original tag format (with #) first
    formatted_opponent_tag = opponent_player_tag if opponent_player_tag.startswith('#') else f"#{opponent_player_tag}"
    print(f"DEBUG get_clan_war_spy_info: Formatted opponent tag: {formatted_opponent_tag}")

    url = f"{DECK_AI_API_BASE_URL}/clan-war-spy"
    params = {
        "accountId": str(account_id),
        "opponentPlayerTag": formatted_opponent_tag
    }
    headers = {
        "api-key": DECK_AI_API_KEY
    }

    # Debug logging
    print(f"DEBUG get_clan_war_spy_info: API URL: {url}")
    print(f"DEBUG get_clan_war_spy_info: API Params: {params}")
    print(f"DEBUG get_clan_war_spy_info: API Key present: {DECK_AI_API_KEY is not None}")

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=headers) as response:
            print(f"DEBUG get_clan_war_spy_info: Response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                print(f"DEBUG get_clan_war_spy_info: Response data type: {type(data)}")
                return data
            elif response.status == 404:
                # Try without the # symbol if the first attempt failed
                sanitized_opponent_tag = sanitize_tag(opponent_player_tag)
                params_alt = {
                    "accountId": str(account_id),
                    "opponentPlayerTag": sanitized_opponent_tag
                }
                print(f"DEBUG get_clan_war_spy_info: Trying again with sanitized tag: {sanitized_opponent_tag}")

                async with session.get(url, params=params_alt, headers=headers) as response2:
                    print(f"DEBUG get_clan_war_spy_info: Second attempt response status: {response2.status}")
                    if response2.status == 200:
                        data = await response2.json()
                        print(f"DEBUG get_clan_war_spy_info: Response data type: {type(data)}")
                        return data
                    else:
                        error_text = await response2.text()
                        print(f"DEBUG get_clan_war_spy_info: Second attempt error: {response2.status} - {error_text}")
                        return {}
            else:
                # Handle other error cases
                error_text = await response.text()
                print(f"DEBUG get_clan_war_spy_info: Error: {response.status} - {error_text}")
                return {}