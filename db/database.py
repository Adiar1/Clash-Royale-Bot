import logging

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS player_links (
    discord_id INTEGER NOT NULL,
    player_tag TEXT NOT NULL PRIMARY KEY,
    position   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_player_links_discord ON player_links (discord_id, position);

CREATE TABLE IF NOT EXISTS deckai_links (
    player_tag TEXT PRIMARY KEY,
    deckai_id  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS clan_links (
    clan_tag  TEXT NOT NULL,
    guild_id  INTEGER NOT NULL,
    nickname  TEXT NOT NULL,
    PRIMARY KEY (clan_tag, guild_id)
);

CREATE TABLE IF NOT EXISTS clan_needs (
    clan_tag   TEXT NOT NULL,
    guild_id   INTEGER NOT NULL,
    needed     INTEGER NOT NULL DEFAULT 0,
    manual     INTEGER NOT NULL DEFAULT 0,  -- 1 = a leader pinned this value; 0 = auto-tracked open slots
    last_count INTEGER,                      -- member count at last poll (for change detection)
    thread_id  INTEGER,                      -- the clan's recruiting thread, if created
    updated_at TEXT,                         -- ISO8601 timestamp of the last change
    PRIMARY KEY (clan_tag, guild_id)
);

CREATE TABLE IF NOT EXISTS clan_managers (
    guild_id INTEGER NOT NULL,
    clan_tag TEXT NOT NULL,
    user_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, clan_tag, user_id)
);

CREATE TABLE IF NOT EXISTS recruit_settings (
    guild_id   INTEGER PRIMARY KEY,
    channel_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS privileged_roles (
    guild_id INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS member_roles (
    guild_id    INTEGER PRIMARY KEY,
    member_id   INTEGER,
    elder_id    INTEGER,
    coleader_id INTEGER
);

CREATE TABLE IF NOT EXISTS reminders (
    clan_tag   TEXT NOT NULL,
    guild_id   INTEGER NOT NULL,
    channel_id INTEGER NOT NULL,
    timezone   TEXT NOT NULL,
    PRIMARY KEY (clan_tag, guild_id)
);

CREATE TABLE IF NOT EXISTS reminder_times (
    clan_tag TEXT NOT NULL,
    guild_id INTEGER NOT NULL,
    time     TEXT NOT NULL,
    PRIMARY KEY (clan_tag, guild_id, time)
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        self.conn = await aiosqlite.connect(self.path)
        await self._migrate_legacy_privileged_roles()
        await self.conn.executescript(SCHEMA)
        await self._migrate_legacy_user_links()
        await self._migrate_clan_needs_columns()
        await self.conn.commit()
        logger.info("Database ready at %s", self.path)
        return self.conn

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None

    async def _table_exists(self, name: str) -> bool:
        cursor = await self.conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
        return await cursor.fetchone() is not None

    async def _table_has_column(self, table: str, column: str) -> bool:
        cursor = await self.conn.execute(f"PRAGMA table_info({table})")
        return any(row[1].lower() == column.lower() for row in await cursor.fetchall())

    async def _migrate_legacy_privileged_roles(self) -> None:
        """v1 stored a comma-joined role_ids string per guild; v2 stores one row per role."""
        if not await self._table_exists("privileged_roles"):
            return
        if not await self._table_has_column("privileged_roles", "role_ids"):
            return  # already v2

        logger.info("Migrating legacy privileged_roles table")
        await self.conn.execute("ALTER TABLE privileged_roles RENAME TO legacy_privileged_roles")
        await self.conn.execute(
            "CREATE TABLE privileged_roles ("
            " guild_id INTEGER NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY (guild_id, role_id))"
        )
        cursor = await self.conn.execute("SELECT guild_id, role_ids FROM legacy_privileged_roles")
        for guild_id, role_ids in await cursor.fetchall():
            for role_id in str(role_ids).split(","):
                role_id = role_id.strip()
                if role_id.isdigit():
                    await self.conn.execute(
                        "INSERT OR IGNORE INTO privileged_roles (guild_id, role_id) VALUES (?, ?)",
                        (int(guild_id), int(role_id)),
                    )

    async def _migrate_clan_needs_columns(self) -> None:
        """The first version of clan_needs held only (clan_tag, guild_id, needed);
        recruit tracking added more columns. Backfill them on older databases."""
        if not await self._table_exists("clan_needs"):
            return
        for column, ddl in (
            ("manual", "manual INTEGER NOT NULL DEFAULT 0"),
            ("last_count", "last_count INTEGER"),
            ("thread_id", "thread_id INTEGER"),
            ("updated_at", "updated_at TEXT"),
        ):
            if not await self._table_has_column("clan_needs", column):
                await self.conn.execute(f"ALTER TABLE clan_needs ADD COLUMN {ddl}")

    async def _migrate_legacy_user_links(self) -> None:
        """v1 stored comma-joined player_tags per user; v2 stores one row per tag."""
        if not await self._table_exists("user_links"):
            return

        logger.info("Migrating legacy user_links table")
        cursor = await self.conn.execute("SELECT discord_id, player_tags FROM user_links")
        for discord_id, player_tags in await cursor.fetchall():
            tags = [t.strip() for t in str(player_tags or "").split(",") if t.strip()]
            for position, tag in enumerate(tags):
                await self.conn.execute(
                    "INSERT OR IGNORE INTO player_links (discord_id, player_tag, position) VALUES (?, ?, ?)",
                    (int(discord_id), tag, position),
                )
        await self.conn.execute("ALTER TABLE user_links RENAME TO legacy_user_links")
