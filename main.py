import logging
import sys

from bot import ClashBot
from config import Config, ConfigError


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        config = Config.from_env()
    except ConfigError as exc:
        logging.getLogger(__name__).error("%s", exc)
        sys.exit(1)

    bot = ClashBot(config)
    bot.run(config.discord_token)


if __name__ == "__main__":
    main()
