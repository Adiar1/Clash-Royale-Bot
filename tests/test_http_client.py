import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from errors import APIUnavailable, ClanNotFound, PlayerNotFound, RateLimited
from services.clash_royale import ClashRoyaleClient


@pytest.fixture
async def api():
    """Local fake Clash Royale API. Tests register responses keyed by raw path."""
    app = web.Application()
    app["responses"] = {}
    app["hits"] = {}

    async def handler(request: web.Request):
        path = request.rel_url.raw_path
        app["hits"][path] = app["hits"].get(path, 0) + 1
        status, payload = app["responses"].get(path, (404, {}))
        return web.json_response(payload, status=status)

    app.router.add_get("/{tail:.*}", handler)
    server = TestServer(app)
    await server.start_server()

    async with aiohttp.ClientSession() as session:
        client = ClashRoyaleClient(session, "key", base_url=str(server.make_url("")))
        yield app, client

    await server.close()


async def test_clan_success_and_cache(api):
    app, client = api
    app["responses"]["/clans/%23ABC123"] = (200, {"name": "MyClan", "tag": "#ABC123"})

    clan = await client.clan("#abc123")
    assert clan["name"] == "MyClan"

    # Same normalized tag => served from cache, no second request.
    await client.clan("ABC123")
    assert app["hits"]["/clans/%23ABC123"] == 1


async def test_status_codes_become_typed_errors(api):
    app, client = api
    with pytest.raises(ClanNotFound):
        await client.clan("MISSING")

    with pytest.raises(PlayerNotFound):
        await client.player("MISSING")

    app["responses"]["/clans/%23LIMITED"] = (429, {})
    with pytest.raises(RateLimited):
        await client.clan("LIMITED")

    app["responses"]["/clans/%23FLAKY1"] = (503, {})
    with pytest.raises(APIUnavailable):
        await client.clan("FLAKY1")


async def test_current_river_race_returns_none_when_absent(api):
    _, client = api
    assert await client.current_river_race("NOWAR") is None


async def test_river_race_log_sorted_newest_first(api):
    app, client = api
    items = [
        {"seasonId": 9, "sectionIndex": 3,
         "standings": [{"clan": {"participants": [{"tag": "#AAA", "fame": 111}]}}]},
        {"seasonId": 10, "sectionIndex": 0,
         "standings": [{"clan": {"participants": [{"tag": "#AAA", "fame": 999}]}}]},
    ]
    app["responses"]["/clans/%23WARL0G/riverracelog"] = (200, {"items": items})

    history = await client.river_race_log("WARL0G")
    assert len(history) == 2
    assert history.fame("AAA", 1) == 999  # newest war first regardless of API order
    assert history.fame("AAA", 2) == 111


async def test_clan_members_parsed_and_normalized(api):
    app, client = api
    app["responses"]["/clans/%23CLAN01/members"] = (200, {"items": [
        {"tag": "#p1", "name": "Alice", "role": "leader"},
        {"tag": "#P2", "name": "Bob", "role": "member"},
    ]})

    members = await client.clan_members("clan01")
    assert [m.tag for m in members] == ["P1", "P2"]
    assert members[0].role == "leader"
