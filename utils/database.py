import sqlite3
import logging
import os

DATABASE_NAME = 'database.db'
logger = logging.getLogger(__name__)

def init_db():
    db_path = os.path.abspath(DATABASE_NAME)
    logger.info(f"Initializing database at {db_path}")

    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS user_links (
                discord_id TEXT PRIMARY KEY,
                player_tags TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS clan_links (
                clan_tag TEXT,
                guild_id TEXT,
                nickname TEXT NOT NULL,
                PRIMARY KEY (clan_tag, guild_id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS privileged_roles (
                guild_id TEXT PRIMARY KEY,
                role_ids TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        logger.info("Database and tables created successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

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

def add_privileged_roles(guild_id, role_ids):
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO privileged_roles (guild_id, role_ids) VALUES (?, ?)', (guild_id, ','.join(role_ids)))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

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