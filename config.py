import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    discord_token: str
    clash_royale_api_key: str
    deckai_api_key: str | None
    database_path: str
    guide_url: str | None  # public URL of the hosted command guide, shown by /info

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv()

        missing = [name for name in ("DISCORD_TOKEN", "CLASH_ROYALE_API_KEY") if not os.getenv(name)]
        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}")

        return cls(
            discord_token=os.environ["DISCORD_TOKEN"],
            clash_royale_api_key=os.environ["CLASH_ROYALE_API_KEY"],
            deckai_api_key=os.getenv("DECKAI_API_KEY") or None,
            database_path=os.getenv("DATABASE_PATH", "database.db"),
            guide_url=os.getenv("GUIDE_URL") or None,
        )
