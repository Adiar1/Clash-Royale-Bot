import os
import sqlite3
from typing import Final
from dotenv import load_dotenv

from utils.database import DATABASE_NAME, logger

load_dotenv()

# Constants
TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')
CLASH_ROYALE_API_KEY: Final[str] = os.getenv('CLASH_ROYALE_API_KEY')
CLASH_ROYALE_API_BASE_URL: Final[str] = 'https://api.clashroyale.com/v1'
TROPHYROAD_EMOJI: Final[str] = '<:trophyroad:1259911930802343959>'
FAME_EMOJI: Final[str] = '<:fame:1260376280767922246>'
NEW_MEMBER_EMOJI: Final[str] = '🆕'
MULTIDECK_EMOJI: Final[str] = '<:multideck:1261593622885957686>'
FORMER_MEMBER_EMOJI: Final[str] = '🚷'
LEVEL_15_EMOJI = "<:experience15:1259916632776511559>"
LEVEL_14_EMOJI = "<:experience14:1259916537939099760>"
LEVEL_13_EMOJI = "<:experience13:1259916353947566172>"
EVOLUTION_EMOJI = "<:evolution:1259918441775894639>"
EMOJI_TROPHYROAD = "<:trophyroad:1259911930802343959>"
POLMEDAL_EMOJI = "<:polmedal:1259901992386428978>"
CW2_EMOJI = "<:cw2:1259911002594742332>"
CC_EMOJI = "<:classicwin:1259902085990715482>"
GC_EMOJI = "<:grandwin:1259902048279859210>"

DEFAULT_WAR_DATA_ORDER: Final[str] = 'fame_name_decks'
DEFAULT_WAR_LISTING_ORDER: Final[str] = 'fame_desc'
DEFAULT_LISTING_ORDER = "tag_asc"
DEFAULT_DATA_ORDER = "tag_name_role"


def sanitize_tag(tag: str) -> str:
    return tag.strip().upper().replace('O', '0')


# Add these to the existing constants
LEAGUE_IMAGES = {
    1: "https://i.imgur.com/MLKoAmu.png",
    2: "https://i.imgur.com/BOXTOdG.png",
    3: "https://i.imgur.com/V1qZXfO.png",
    4: "https://i.imgur.com/Wvd22mf.png",
    5: "https://i.imgur.com/VGtORcN.png",
    6: "https://i.imgur.com/yZV6S0n.png",
    7: "https://i.imgur.com/kNBJ5NF.png",
    8: "https://i.imgur.com/8h0pV54.png",
    9: "https://i.imgur.com/kRRJNtK.png",
    10: "https://i.imgur.com/ALZC2Zk.png"
}

LEVEL_EMOJIS = {
    30: "<:experience30:1259926700385636384>",
    31: "<:experience31:1259926881348616397>",
    32: "<:experience32:1259926950386860114>",
    33: "<:experience33:1259927005726507071>",
    34: "<:experience34:1259928704113705060>",
    35: "<:experience35:1259929000604598383>",
    36: "<:experience36:1259929125687263314>",
    37: "<:experience37:1259929177587453973>",
    38: "<:experience38:1259929229152358503>",
    39: "<:experience39:1259929283703472249>",
    40: "<:experience40:1259929342700683344>",
    41: "<:experience41:1259929400284282981>",
    42: "<:experience42:1259929444982980670>",
    43: "<:experience43:1259929495490793533>",
    44: "<:experience44:1259929546329948293>",
    45: "<:experience45:1259929593381523526>",
    46: "<:experience46:1259929653947138149>",
    47: "<:experience47:1259930180814635039>",
    48: "<:experience48:1259930236402012161>",
    49: "<:experience49:1259930299589066786>",
    50: "<:experience50:1259930336888881284>",
    51: "<:experience51:1259931730480201808>",
    52: "<:experience52:1259931786302062713>",
    53: "<:experience53:1259931838760353874>",
    54: "<:experience54:1259931897270632599>",
    55: "<:experience55:1259931942246289418>",
    56: "<:experience56:1259932025771786261>",
    57: "<:experience57:1259932068570337282>",
    58: "<:experience58:1259932126728556656>",
    59: "<:experience59:1259932183620227206>",
    60: "<:experience60:1259932254197518347>",
    61: "<:experience61:1259932308203372587>",
    62: "<:experience62:1259932554178592889>",
    63: "<:experience63:1259932601578422293>",
    64: "<:experience64:1259932650630545418>",
}


def get_discord_id_from_tag(player_tag):
    try:
        # Strip '#' and capitalize the tag
        formatted_tag = player_tag.lstrip('#').upper()

        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute(
            'SELECT discord_id FROM user_links WHERE player_tags = ? OR player_tags LIKE ? OR player_tags LIKE ? OR player_tags LIKE ?',
            (formatted_tag, f'{formatted_tag},%', f'%,{formatted_tag},%', f'%,{formatted_tag}')
        )
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def get_clan_tag_by_nickname(nickname, guild_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT clan_tag FROM clan_links WHERE nickname = ? AND guild_id = ?', (nickname, guild_id))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def get_all_clan_links():
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT clan_tag, guild_id, nickname FROM clan_links')
        results = c.fetchall()
        conn.close()
        return results
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []


def get_privileged_roles(guild_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT role_ids FROM privileged_roles WHERE guild_id = ?', (guild_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0].split(',')
        return []
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []


def add_privileged_roles(guild_id, role_ids):
    try:
        # Filter any empty strings or None values from the list
        role_ids = list(filter(None, role_ids))

        # Join the role IDs into a single comma-separated string
        role_ids_str = ','.join(role_ids)

        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO privileged_roles (guild_id, role_ids) VALUES (?, ?)',
                  (guild_id, role_ids_str))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False


def update_member_roles(guild_id, position, role_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()

        # Check if the guild already has a row
        c.execute('SELECT * FROM member_roles WHERE guild_id = ?', (guild_id,))
        existing_row = c.fetchone()

        if existing_row:
            # Update the existing row
            c.execute(f'''
                UPDATE member_roles
                SET {position}_id = ?
                WHERE guild_id = ?
            ''', (role_id, guild_id))
        else:
            # Insert a new row
            c.execute(f'''
                INSERT INTO member_roles (guild_id, {position}_id)
                VALUES (?, ?)
            ''', (guild_id, role_id))

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating member roles: {e}")
        return False
    finally:
        conn.close()


def update_player_tags(discord_id, new_tags):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('UPDATE user_links SET player_tags = ? WHERE discord_id = ?', (new_tags, discord_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False


def delete_clan_tag(clan_tag, guild_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('DELETE FROM clan_links WHERE clan_tag = ? AND guild_id = ?', (clan_tag, guild_id))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False


def get_clan_nickname(clan_tag, guild_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT nickname FROM clan_links WHERE clan_tag = ? AND guild_id = ?', (clan_tag, guild_id))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def link_clan_tag(clan_tag, guild_id, nickname):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO clan_links (clan_tag, guild_id, nickname) VALUES (?, ?, ?)', (clan_tag, guild_id, nickname))
        conn.commit()
        conn.close()
        return "linked"
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def delete_all_player_tags(discord_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('DELETE FROM user_links WHERE discord_id = ?', (discord_id,))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False


def get_all_player_tags(discord_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT player_tags FROM user_links WHERE discord_id = ?', (discord_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return result[0].split(',')
        return []
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return []


def link_player_tag(discord_id, player_tag, alt=False):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()

        c.execute('SELECT player_tags FROM user_links WHERE discord_id = ?', (discord_id,))
        result = c.fetchone()

        if result:
            existing_tags = result[0].split(',')
            if alt:
                if player_tag not in existing_tags:
                    existing_tags.append(player_tag)
                    c.execute('UPDATE user_links SET player_tags = ? WHERE discord_id = ?', (','.join(existing_tags), discord_id))
                    conn.commit()
                    conn.close()
                    return "linked"
                else:
                    conn.close()
                    return "exists"
            else:
                existing_tags[0] = player_tag
                c.execute('UPDATE user_links SET player_tags = ? WHERE discord_id = ?', (','.join(existing_tags), discord_id))
                conn.commit()
                conn.close()
                return "updated"
        else:
            c.execute('INSERT INTO user_links (discord_id, player_tags) VALUES (?, ?)', (discord_id, player_tag))
            conn.commit()
            conn.close()
            return "linked"
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def get_linked_discord_id(player_tag):
    try:
        # Strip '#' and capitalize the tag
        formatted_tag = player_tag.lstrip('#').upper()

        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute(
            'SELECT discord_id FROM user_links WHERE player_tags = ? OR player_tags LIKE ? OR player_tags LIKE ? OR player_tags LIKE ?',
            (formatted_tag, f'{formatted_tag},%', f'%,{formatted_tag},%', f'%,{formatted_tag}')
        )
        result = c.fetchone()
        conn.close()
        if result:
            return result[0]
        else:
            return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None


def get_player_tag_from_mention(user_mention, guild_id):
    try:
        # Extract user ID from mention
        user_id = user_mention.strip('<@!>')
        
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT player_tags FROM user_links WHERE discord_id = ?', (user_id,))
        result = c.fetchone()
        conn.close()
        
        if result and result[0]:
            # Return the first (main) player tag
            return result[0].split(',')[0]
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None




async def is_privileged(interaction):
    guild_id = str(interaction.guild.id)
    user_roles = [role.id for role in interaction.user.roles]
    privileged_roles = get_privileged_roles(guild_id)
    return any(str(role_id) in privileged_roles for role_id in user_roles)

def get_member_roles(guild_id):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('SELECT member_id, elder_id, coLeader_id FROM member_roles WHERE guild_id = ?', (guild_id,))
        result = c.fetchone()
        conn.close()
        if result:
            return {
                'member': result[0],
                'elder': result[1],
                'coLeader': result[2]
            }
        return None
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return None
