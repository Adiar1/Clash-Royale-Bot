import json
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
        c.execute('''
            CREATE TABLE IF NOT EXISTS automated_reminders (
                guild_id INTEGER,
                channel_id INTEGER,
                clan_tag TEXT,
                reminder_times TEXT,  # JSON-serialized list of UTC times
                days_to_remind TEXT,  # JSON-serialized list of days
                PRIMARY KEY (guild_id, clan_tag)
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("Database updated with automated_reminders table.")
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")

    def save_automated_reminder(guild_id, channel_id, clan_tag, reminder_times, days_to_remind):
        """
        Save an automated reminder configuration

        :param guild_id: Discord guild ID
        :param channel_id: Channel to send reminders in
        :param clan_tag: Clan to send reminders about
        :param reminder_times: List of UTC times to send reminders
        :param days_to_remind: List of days to send reminders
        """
        try:
            conn = sqlite3.connect(DATABASE_NAME)
            c = conn.cursor()

            # Convert times and days to JSON strings for storage
            times_json = json.dumps(reminder_times)
            days_json = json.dumps(days_to_remind)

            # Replace or insert the reminder configuration
            c.execute('''
                    INSERT OR REPLACE INTO automated_reminders 
                    (guild_id, channel_id, clan_tag, reminder_times, days_to_remind) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (guild_id, channel_id, clan_tag, times_json, days_json))

            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error saving automated reminder: {e}")
            return False

    def get_automated_reminders():
        """
        Retrieve all configured automated reminders

        :return: List of automated reminder configurations
        """
        try:
            conn = sqlite3.connect(DATABASE_NAME)
            c = conn.cursor()

            c.execute('SELECT * FROM automated_reminders')
            reminders = c.fetchall()

            # Convert results to a more usable format
            formatted_reminders = []
            for reminder in reminders:
                formatted_reminders.append({
                    'guild_id': reminder[0],
                    'channel_id': reminder[1],
                    'clan_tag': reminder[2],
                    'reminder_times': json.loads(reminder[3]),
                    'days_to_remind': json.loads(reminder[4])
                })

            conn.close()
            return formatted_reminders
        except sqlite3.Error as e:
            logger.error(f"Error retrieving automated reminders: {e}")
            return []


