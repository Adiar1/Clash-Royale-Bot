import os
from dotenv import load_dotenv
from bot import bot
from utils.database import init_db, logger


def main():
    load_dotenv()
    try:
        init_db()  # Initialize the database before running the bot
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    TOKEN = os.getenv('DISCORD_TOKEN')

    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.error("DISCORD_TOKEN not found in environment variables.")


if __name__ == '__main__':
    main()
