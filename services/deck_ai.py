import aiohttp

from errors import BotError
from services.http import BaseAPIClient, NotFoundError

BASE_URL = "https://deckai.app/api"


class DeckAIClient(BaseAPIClient):
    def __init__(self, session: aiohttp.ClientSession, api_key: str | None):
        super().__init__(session, BASE_URL, {"api-key": api_key or ""})
        self._configured = bool(api_key)

    async def clan_war_spy(self, account_id: str, opponent_player_tag: str) -> dict | None:
        """Opponent war-deck intel from DeckAI. None if DeckAI has no data for that player."""
        if not self._configured:
            raise BotError("DeckAI is not configured on this bot (missing DECKAI_API_KEY).")

        # DeckAI expects '#TAG'; some accounts are stored without the '#', so retry bare.
        hashed = opponent_player_tag if opponent_player_tag.startswith("#") else f"#{opponent_player_tag}"
        for tag_variant in (hashed, hashed.lstrip("#")):
            try:
                return await self.get_json(
                    "/clan-war-spy",
                    params={"accountId": str(account_id), "opponentPlayerTag": tag_variant},
                    use_cache=False,
                )
            except NotFoundError:
                continue
        return None
