from dataclasses import dataclass
from datetime import UTC, datetime

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
        last_404_body = ""
        for tag_variant in (hashed, hashed.lstrip("#")):
            try:
                return await self.get_json(
                    "/clan-war-spy",
                    params={"accountId": str(account_id), "opponentPlayerTag": tag_variant},
                    use_cache=False,
                )
            except NotFoundError as exc:
                last_404_body = exc.body

        # DeckAI 404s carry the actual reason in the body; surface it instead of
        # letting the caller show a generic "no data" message.
        reason = last_404_body.strip().lower()
        if "no matching user id" in reason:
            raise BotError(
                "DeckAI doesn't recognize the linked DeckAI ID. "
                "Double-check it in the DeckAI app and re-link it with `/link`."
            )
        if "clan war decks not set" in reason:
            raise BotError(
                "DeckAI says: **Clan war decks not set.**\n"
                "This usually means the clan war decks aren't set up on the linked DeckAI account — "
                "open the DeckAI app, set your 4 war decks, then try again.\n"
                "It can also mean DeckAI has no war-deck data for that opponent."
            )
        return None


# ---- Deck-availability and matchup math (pure, no I/O) ----

@dataclass(frozen=True)
class DeckRecommendation:
    player_deck_index: int
    average_win_rate: float


def _parse_deck_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def split_available_decks(
    opponent_decks: list[dict], now: datetime | None = None
) -> tuple[list[dict], list[dict]]:
    """Split opponent decks into (available, used_today) by UTC calendar date.

    War decks reset daily; a deck last played today has already been spent and
    can't be replayed in a new duel, so only the remainder is available.
    """
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    available: list[dict] = []
    used_today: list[dict] = []
    for deck in opponent_decks:
        parsed = _parse_deck_date(deck.get("date", "")) if isinstance(deck, dict) else None
        bucket = used_today if parsed and parsed.astimezone(UTC).date() == today else available
        bucket.append(deck)
    return available, used_today


def recommend_deck(
    player_decks: list,
    opponent_decks: list[dict],
    excluded_player_indices: frozenset[int] = frozenset(),
) -> DeckRecommendation | None:
    """Best remaining player deck by average win rate across the given opponent decks.

    None if there's no opponent deck data or every player deck is excluded
    (already played earlier in this duel).
    """
    if not opponent_decks:
        return None

    best: DeckRecommendation | None = None
    for i in range(len(player_decks)):
        if i in excluded_player_indices:
            continue
        rates = [
            deck["winRates"][i]
            for deck in opponent_decks
            if isinstance(deck, dict) and i < len(deck.get("winRates") or [])
        ]
        if not rates:
            continue
        average = sum(rates) / len(rates)
        if best is None or average > best.average_win_rate:
            best = DeckRecommendation(i, average)
    return best
