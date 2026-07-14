import logging
from typing import Any

import aiohttp
from cachetools import TTLCache

from errors import APIUnavailable, RateLimited

logger = logging.getLogger(__name__)


class NotFoundError(Exception):
    """Raised on HTTP 404. Clients translate this into a typed BotError or None.

    ``body`` is the response text: some APIs (DeckAI) put the actual reason
    there, e.g. "Clan war decks not set" vs "No matching user id".
    """

    def __init__(self, url: str, body: str = ""):
        super().__init__(url)
        self.body = body


class BaseAPIClient:
    """Shared plumbing for every external HTTP API the bot talks to.

    Owns auth headers and a TTL cache; uses the single aiohttp session created
    at bot startup. Non-200 responses become typed exceptions instead of being
    silently swallowed.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        headers: dict[str, str] | None = None,
        cache_ttl: int = 60,
        cache_size: int = 2048,
    ):
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._cache: TTLCache = TTLCache(maxsize=cache_size, ttl=cache_ttl)

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> Any:
        cache_key = (path, tuple(sorted((params or {}).items())))
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        url = f"{self._base_url}{path}"
        try:
            async with self._session.get(url, params=params, headers=self._headers) as response:
                if response.status == 200:
                    data = await response.json()
                    if use_cache:
                        self._cache[cache_key] = data
                    return data

                body = await response.text()
                if response.status == 404:
                    raise NotFoundError(url, body)
                if response.status == 429:
                    logger.warning("Rate limited by %s: %s", url, body[:200])
                    raise RateLimited()
                logger.error("HTTP %s from %s: %s", response.status, url, body[:500])
                raise APIUnavailable()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.error("Request to %s failed: %s", url, exc)
            raise APIUnavailable() from exc
