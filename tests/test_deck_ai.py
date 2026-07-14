from datetime import UTC, datetime

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from errors import BotError
from services.deck_ai import DeckAIClient, recommend_deck, split_available_decks


def opponent_deck(win_rates, date="2024-12-07T21:26:52.000Z"):
    return {"deck": [], "winRates": win_rates, "gameMode": "Clan War Duel", "date": date}


# ---- clan_war_spy error translation ----

@pytest.fixture
async def deckai():
    """Local fake DeckAI. Tests set app["response"] = (status, text_or_dict)."""
    app = web.Application()
    app["response"] = (404, "")

    async def handler(request: web.Request):
        status, payload = app["response"]
        if isinstance(payload, dict):
            return web.json_response(payload, status=status)
        return web.Response(text=payload, status=status)

    app.router.add_get("/{tail:.*}", handler)
    server = TestServer(app)
    await server.start_server()

    async with aiohttp.ClientSession() as session:
        client = DeckAIClient(session, "key")
        client._base_url = str(server.make_url("")).rstrip("/")
        yield app, client

    await server.close()


async def test_spy_success_returns_payload(deckai):
    app, client = deckai
    app["response"] = (200, {"opponentDecks": [], "playerDecks": []})
    assert await client.clan_war_spy("acc", "TAG") == {"opponentDecks": [], "playerDecks": []}


async def test_spy_decks_not_set_surfaces_reason(deckai):
    app, client = deckai
    app["response"] = (404, "Clan war decks not set")
    with pytest.raises(BotError, match="Clan war decks not set"):
        await client.clan_war_spy("acc", "TAG")


async def test_spy_bad_account_id_surfaces_reason(deckai):
    app, client = deckai
    app["response"] = (404, "No matching user id")
    with pytest.raises(BotError, match="doesn't recognize the linked DeckAI ID"):
        await client.clan_war_spy("acc", "TAG")


async def test_spy_unknown_404_returns_none(deckai):
    app, client = deckai
    app["response"] = (404, "whatever else")
    assert await client.clan_war_spy("acc", "TAG") is None


# ---- split_available_decks ----

def test_split_available_decks_separates_todays_deck():
    now = datetime(2024, 12, 8, 18, 0, tzinfo=UTC)
    used_today_deck = opponent_deck([0.1, 0.2, 0.3, 0.4], date="2024-12-08T17:35:24.000Z")
    older_deck = opponent_deck([0.5, 0.6, 0.7, 0.8], date="2024-12-07T21:26:52.000Z")

    available, used_today = split_available_decks([older_deck, used_today_deck], now=now)

    assert available == [older_deck]
    assert used_today == [used_today_deck]


def test_split_available_decks_handles_missing_or_bad_dates():
    now = datetime(2024, 12, 8, 18, 0, tzinfo=UTC)
    no_date = opponent_deck([0.1, 0.2, 0.3, 0.4], date="")
    bad_date = opponent_deck([0.1, 0.2, 0.3, 0.4], date="not-a-date")

    available, used_today = split_available_decks([no_date, bad_date], now=now)

    assert available == [no_date, bad_date]
    assert used_today == []


# ---- recommend_deck ----

def test_recommend_deck_picks_highest_average():
    player_decks = [{}, {}, {}]
    opponent_decks = [
        opponent_deck([0.10, 0.90, 0.50]),
        opponent_deck([0.20, 0.10, 0.60]),
    ]

    rec = recommend_deck(player_decks, opponent_decks)

    # Averages: deck 0 -> 0.15, deck 1 -> 0.50, deck 2 -> 0.55 -> deck 2 wins.
    assert rec.player_deck_index == 2
    assert round(rec.average_win_rate, 4) == 0.55


def test_recommend_deck_excludes_already_played_decks():
    player_decks = [{}, {}, {}]
    opponent_decks = [opponent_deck([0.10, 0.90, 0.50])]

    rec = recommend_deck(player_decks, opponent_decks, excluded_player_indices=frozenset({1}))

    assert rec.player_deck_index == 2
    assert rec.average_win_rate == 0.50


def test_recommend_deck_returns_none_without_data():
    assert recommend_deck([{}, {}], []) is None
    assert recommend_deck([{}, {}], [opponent_deck([0.5, 0.5])], excluded_player_indices=frozenset({0, 1})) is None
