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
                discord_id INTEGER PRIMARY KEY,
                player_tags TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS deckai_links (
                player_tag TEXT PRIMARY KEY,
                deckai_id TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS clan_links (
                clan_tag TEXT,
                guild_id INTEGER,
                nickname TEXT NOT NULL,
                PRIMARY KEY (clan_tag, guild_id)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS privileged_roles (
                guild_id INTEGER PRIMARY KEY,
                role_ids INTEGER NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS member_roles (
                guild_id INTEGER PRIMARY KEY,
                member_id INTEGER,
                elder_id INTEGER,
                coLeader_id INTEGER
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")