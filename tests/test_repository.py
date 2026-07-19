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


async def test_clan_needs(repo):
    assert await repo.clan_needs("#clan1", 1) is None
    assert await repo.clan_needs_for_guild(1) == []

    await repo.set_clan_needs("#clan1", 1, 5)
    await repo.set_clan_needs("clan2", 1, 3)
    assert await repo.clan_needs("CLAN1", 1) == 5
    assert await repo.clan_needs("clan1", 2) is None  # other guild

    # Re-setting replaces the previous value
    await repo.set_clan_needs("CLAN1", 1, 8)
    assert await repo.clan_needs("CLAN1", 1) == 8

    assert sorted(await repo.clan_needs_for_guild(1)) == [("CLAN1", 8), ("CLAN2", 3)]

    # A zero need is not returned as an outstanding need
    await repo.set_clan_needs("CLAN2", 1, 0)
    assert await repo.clan_needs_for_guild(1) == [("CLAN1", 8)]

    assert await repo.delete_clan_needs("CLAN1", 1) is True
    assert await repo.delete_clan_needs("CLAN1", 1) is False
    assert await repo.clan_needs("CLAN1", 1) is None
    assert await repo.clan_needs_for_guild(1) == []


async def test_clan_need_tracking(repo):
    assert await repo.clan_need("CLAN1", 1) is None

    # Manual pin records the manual flag; auto set clears it.
    await repo.set_clan_needs("#clan1", 1, 4, manual=True)
    need = await repo.clan_need("CLAN1", 1)
    assert need.needed == 4 and need.manual is True
    assert need.last_count is None and need.thread_id is None

    await repo.set_clan_needs("CLAN1", 1, 2, manual=False)
    need = await repo.clan_need("CLAN1", 1)
    assert need.needed == 2 and need.manual is False

    # Tracking fields update independently and don't clobber the need.
    await repo.set_clan_last_count("CLAN1", 1, 47)
    await repo.set_clan_thread("CLAN1", 1, 9999)
    need = await repo.clan_need("CLAN1", 1)
    assert need.needed == 2 and need.last_count == 47 and need.thread_id == 9999

    assert await repo.clan_by_thread(9999) == (1, "CLAN1")
    assert await repo.clan_by_thread(123) is None

    # A count/thread update on a fresh clan creates the row with defaults.
    await repo.set_clan_last_count("CLAN2", 1, 50)
    fresh = await repo.clan_need("CLAN2", 1)
    assert fresh.needed == 0 and fresh.manual is False and fresh.last_count == 50
    assert fresh.mode == "standard"  # clans are standard (auto-tracked) unless told otherwise


async def test_clan_mode(repo):
    # Unknown clans and plain need rows default to standard.
    assert await repo.clan_mode("CLAN1", 1) == "standard"
    await repo.set_clan_needs("#clan1", 1, 5)
    assert await repo.clan_mode("CLAN1", 1) == "standard"

    # Switching to rotation persists and shows up on the ClanNeed too.
    await repo.set_clan_mode("clan1", 1, "rotation")
    assert await repo.clan_mode("CLAN1", 1) == "rotation"
    assert (await repo.clan_need("CLAN1", 1)).mode == "rotation"

    # Mode is per (clan, guild) and orthogonal to the need value.
    assert await repo.clan_mode("CLAN1", 2) == "standard"  # other guild
    await repo.set_clan_needs("CLAN1", 1, 9, manual=True)
    assert await repo.clan_mode("CLAN1", 1) == "rotation"  # unchanged by set_clan_needs

    # set_clan_mode on a fresh clan creates the row with default need.
    await repo.set_clan_mode("CLAN2", 1, "rotation")
    fresh = await repo.clan_need("CLAN2", 1)
    assert fresh.mode == "rotation" and fresh.needed == 0

    await repo.set_clan_mode("CLAN1", 1, "standard")
    assert await repo.clan_mode("CLAN1", 1) == "standard"


async def test_clan_managers(repo):
    assert await repo.clan_managers(1, "CLAN1") == []
    assert await repo.managed_clans(1) == []
    assert await repo.all_managed_clans() == []

    await repo.add_clan_manager(1, "#clan1", 100)
    await repo.add_clan_manager(1, "CLAN1", 200)
    await repo.add_clan_manager(1, "CLAN1", 100)  # duplicate ignored
    await repo.add_clan_manager(1, "CLAN2", 300)
    await repo.add_clan_manager(2, "CLAN1", 400)  # other guild

    assert await repo.clan_managers(1, "clan1") == [100, 200]
    assert sorted(await repo.managed_clans(1)) == ["CLAN1", "CLAN2"]
    assert sorted(await repo.all_managed_clans()) == [(1, "CLAN1"), (1, "CLAN2"), (2, "CLAN1")]

    assert await repo.remove_clan_manager(1, "CLAN1", 100) is True
    assert await repo.remove_clan_manager(1, "CLAN1", 100) is False
    assert await repo.clan_managers(1, "CLAN1") == [200]


async def test_recruit_channel(repo):
    assert await repo.recruit_channel(1) is None
    await repo.set_recruit_channel(1, 555)
    assert await repo.recruit_channel(1) == 555
    await repo.set_recruit_channel(1, 777)  # replaces
    assert await repo.recruit_channel(1) == 777
    assert await repo.recruit_channel(2) is None


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


async def test_clan_needs_column_migration(tmp_path):
    """An early clan_needs table (only clan_tag/guild_id/needed) gains the new columns."""
    path = str(tmp_path / "old_needs.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE clan_needs (clan_tag TEXT NOT NULL, guild_id INTEGER NOT NULL,
                                 needed INTEGER NOT NULL, PRIMARY KEY (clan_tag, guild_id));
        INSERT INTO clan_needs VALUES ('CLAN1', 1, 6);
    """)
    conn.commit()
    conn.close()

    db = Database(path)
    repo = Repository(await db.connect())

    need = await repo.clan_need("CLAN1", 1)
    assert need.needed == 6 and need.manual is False
    assert need.last_count is None and need.thread_id is None

    # New tracking columns are writable after the migration.
    await repo.set_clan_thread("CLAN1", 1, 42)
    assert await repo.clan_by_thread(42) == (1, "CLAN1")
    await db.close()


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
