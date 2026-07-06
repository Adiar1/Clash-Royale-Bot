import sqlite3

import pytest

from db.database import Database
from db.repository import Repository


@pytest.fixture
async def repo(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    conn = await db.connect()
    yield Repository(conn)
    await db.close()


async def test_link_main_and_alt_tags(repo):
    assert await repo.link_player_tag(1, "#abc123", alt=False) == "linked"
    assert await repo.player_tags(1) == ["ABC123"]

    assert await repo.link_player_tag(1, "DEF456", alt=True) == "linked"
    assert await repo.player_tags(1) == ["ABC123", "DEF456"]

    # Replacing the main keeps alts
    assert await repo.link_player_tag(1, "NEW999", alt=False) == "linked"
    assert await repo.player_tags(1) == ["NEW999", "DEF456"]


async def test_alt_guards(repo):
    assert await repo.link_player_tag(2, "ALT111", alt=True) == "no_main_tag"

    await repo.link_player_tag(2, "MAIN11", alt=False)
    assert await repo.link_player_tag(2, "MAIN11", alt=True) == "exists"

    for i in range(19):
        assert await repo.link_player_tag(2, f"TAG{i:03}", alt=True) == "linked"
    assert await repo.link_player_tag(2, "TOOMANY", alt=True) == "too_many_tags"


async def test_unlink_and_lookup(repo):
    await repo.link_player_tag(3, "AAA111", alt=False)
    await repo.link_player_tag(3, "BBB222", alt=True)

    assert await repo.discord_id_for_tag("#aaa111") == 3

    await repo.unlink_player_tags(3, ["AAA111"])
    assert await repo.player_tags(3) == ["BBB222"]
    assert await repo.discord_id_for_tag("AAA111") is None


async def test_clan_nicknames_case_insensitive(repo):
    await repo.set_clan_nickname("#clan99", 42, "abc")
    assert await repo.clan_tag_for_nickname("ABC", 42) == "CLAN99"
    assert await repo.clan_tag_for_nickname("abc", 43) is None  # other guild
    assert await repo.nickname_for_clan("CLAN99", 42) == "abc"

    assert await repo.delete_clan_nickname("CLAN99", 42) is True
    assert await repo.delete_clan_nickname("CLAN99", 42) is False


async def test_privileged_roles(repo):
    assert await repo.privileged_role_ids(7) == []
    await repo.set_privileged_roles(7, [111, 222])
    assert sorted(await repo.privileged_role_ids(7)) == [111, 222]
    await repo.set_privileged_roles(7, [333])
    assert await repo.privileged_role_ids(7) == [333]


async def test_member_roles(repo):
    roles = await repo.member_roles(9)
    assert roles == {"member": None, "elder": None, "coLeader": None}

    await repo.set_member_role(9, "elder", 555)
    await repo.set_member_role(9, "coleader", 666)
    roles = await repo.member_roles(9)
    assert roles["elder"] == 555
    assert roles["coLeader"] == 666

    with pytest.raises(ValueError):
        await repo.set_member_role(9, "leader; DROP TABLE member_roles", 1)


async def test_reminders(repo):
    assert await repo.reminder("CLAN01", 1) is None
    assert await repo.all_reminders() == []

    await repo.set_reminder("#clan01", 1, 555, "America/New_York", ["21:00", "18:00"])
    reminder = await repo.reminder("clan01", 1)
    assert reminder.clan_tag == "CLAN01"
    assert reminder.channel_id == 555
    assert reminder.timezone == "America/New_York"
    assert reminder.times == ("18:00", "21:00")  # stored sorted

    await repo.set_reminder_channel("CLAN01", 1, 777)
    assert (await repo.reminder("CLAN01", 1)).channel_id == 777

    # Re-saving replaces the previous times instead of accumulating them
    await repo.set_reminder("CLAN01", 1, 777, "UTC", ["09:00"])
    reminder = await repo.reminder("CLAN01", 1)
    assert reminder.timezone == "UTC"
    assert reminder.times == ("09:00",)

    await repo.set_reminder("CLAN02", 2, 888, "UTC", ["12:00"])
    assert {r.clan_tag for r in await repo.all_reminders()} == {"CLAN01", "CLAN02"}

    assert await repo.delete_reminder("CLAN01", 1) is True
    assert await repo.delete_reminder("CLAN01", 1) is False
    assert await repo.reminder("CLAN01", 1) is None


async def test_deckai_links(repo):
    assert await repo.deckai_id("XYZ") is None
    await repo.set_deckai_id("#xyz", "deck-1")
    assert await repo.deckai_id("xyz") == "deck-1"
    await repo.delete_deckai_id("XYZ")
    assert await repo.deckai_id("XYZ") is None


async def test_legacy_migration(tmp_path):
    """A v1 database (comma-joined columns) is converted to v2 on connect."""
    path = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE user_links (discord_id INTEGER PRIMARY KEY, player_tags TEXT NOT NULL);
        INSERT INTO user_links VALUES (100, 'MAIN01,ALT001,ALT002');
        INSERT INTO user_links VALUES (200, 'SOLO01');

        CREATE TABLE privileged_roles (guild_id INTEGER PRIMARY KEY, role_ids INTEGER NOT NULL);
        INSERT INTO privileged_roles VALUES (5, '123,456');
        INSERT INTO privileged_roles VALUES (6, 789);

        CREATE TABLE deckai_links (player_tag TEXT PRIMARY KEY, deckai_id TEXT NOT NULL);
        INSERT INTO deckai_links VALUES ('MAIN01', 'deck-99');

        CREATE TABLE clan_links (clan_tag TEXT, guild_id INTEGER, nickname TEXT NOT NULL,
                                 PRIMARY KEY (clan_tag, guild_id));
        INSERT INTO clan_links VALUES ('CLAN01', 5, 'main');

        CREATE TABLE member_roles (guild_id INTEGER PRIMARY KEY, member_id INTEGER,
                                   elder_id INTEGER, coLeader_id INTEGER);
        INSERT INTO member_roles VALUES (5, 1, 2, 3);
    """)
    conn.commit()
    conn.close()

    db = Database(path)
    repo = Repository(await db.connect())

    assert await repo.player_tags(100) == ["MAIN01", "ALT001", "ALT002"]
    assert await repo.player_tags(200) == ["SOLO01"]
    assert sorted(await repo.privileged_role_ids(5)) == [123, 456]
    assert await repo.privileged_role_ids(6) == [789]
    assert await repo.deckai_id("MAIN01") == "deck-99"
    assert await repo.clan_tag_for_nickname("main", 5) == "CLAN01"
    assert (await repo.member_roles(5))["coLeader"] == 3

    await db.close()

    # Reconnecting must not re-run or duplicate the migration.
    db = Database(path)
    repo = Repository(await db.connect())
    assert await repo.player_tags(100) == ["MAIN01", "ALT001", "ALT002"]
    await db.close()
