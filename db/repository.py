"""All database queries live here. Tags are stored normalized (no '#', uppercase)."""

import aiosqlite

from services.clash_royale import normalize_tag

MAX_LINKED_TAGS = 20

MEMBER_ROLE_POSITIONS = ("member", "elder", "coleader")


class Repository:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    # ---- player links ----

    async def player_tags(self, discord_id: int) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT player_tag FROM player_links WHERE discord_id = ? ORDER BY position",
            (int(discord_id),),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def set_player_tags(self, discord_id: int, tags: list[str]) -> None:
        await self._conn.execute("DELETE FROM player_links WHERE discord_id = ?", (int(discord_id),))
        for position, tag in enumerate(tags):
            await self._conn.execute(
                "INSERT OR REPLACE INTO player_links (discord_id, player_tag, position) VALUES (?, ?, ?)",
                (int(discord_id), normalize_tag(tag), position),
            )
        await self._conn.commit()

    async def link_player_tag(self, discord_id: int, player_tag: str, alt: bool) -> str:
        """Returns "linked", "exists", "no_main_tag", or "too_many_tags"."""
        tag = normalize_tag(player_tag)
        existing = await self.player_tags(discord_id)

        if alt:
            if not existing:
                return "no_main_tag"
            if len(existing) >= MAX_LINKED_TAGS:
                return "too_many_tags"
            if tag in existing:
                return "exists"
            new_tags = existing + [tag]
        else:
            # Replace the main tag, keeping alts (and dropping a duplicate of the new main).
            new_tags = [tag] + [t for t in existing[1:] if t != tag]

        await self.set_player_tags(discord_id, new_tags)
        return "linked"

    async def unlink_player_tags(self, discord_id: int, tags_to_remove: list[str]) -> None:
        remove = {normalize_tag(t) for t in tags_to_remove}
        remaining = [t for t in await self.player_tags(discord_id) if t not in remove]
        await self.set_player_tags(discord_id, remaining)

    async def discord_id_for_tag(self, player_tag: str) -> int | None:
        cursor = await self._conn.execute(
            "SELECT discord_id FROM player_links WHERE player_tag = ?",
            (normalize_tag(player_tag),),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    # ---- DeckAI links ----

    async def deckai_id(self, player_tag: str) -> str | None:
        cursor = await self._conn.execute(
            "SELECT deckai_id FROM deckai_links WHERE player_tag = ?",
            (normalize_tag(player_tag),),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_deckai_id(self, player_tag: str, deckai_id: str) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO deckai_links (player_tag, deckai_id) VALUES (?, ?)",
            (normalize_tag(player_tag), deckai_id),
        )
        await self._conn.commit()

    async def delete_deckai_id(self, player_tag: str) -> None:
        await self._conn.execute("DELETE FROM deckai_links WHERE player_tag = ?", (normalize_tag(player_tag),))
        await self._conn.commit()

    # ---- clan nicknames ----

    async def clan_tag_for_nickname(self, nickname: str, guild_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT clan_tag FROM clan_links WHERE nickname = ? COLLATE NOCASE AND guild_id = ?",
            (nickname.strip(), int(guild_id)),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def nickname_for_clan(self, clan_tag: str, guild_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT nickname FROM clan_links WHERE clan_tag = ? AND guild_id = ?",
            (normalize_tag(clan_tag), int(guild_id)),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def set_clan_nickname(self, clan_tag: str, guild_id: int, nickname: str) -> None:
        await self._conn.execute(
            "INSERT OR REPLACE INTO clan_links (clan_tag, guild_id, nickname) VALUES (?, ?, ?)",
            (normalize_tag(clan_tag), int(guild_id), nickname.strip()),
        )
        await self._conn.commit()

    async def delete_clan_nickname(self, clan_tag: str, guild_id: int) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM clan_links WHERE clan_tag = ? AND guild_id = ?",
            (normalize_tag(clan_tag), int(guild_id)),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def clan_links_for_guild(self, guild_id: int) -> list[tuple[str, str]]:
        """[(clan_tag, nickname), ...] for a guild."""
        cursor = await self._conn.execute(
            "SELECT clan_tag, nickname FROM clan_links WHERE guild_id = ?",
            (int(guild_id),),
        )
        return [(row[0], row[1]) for row in await cursor.fetchall()]

    # ---- privileged roles ----

    async def privileged_role_ids(self, guild_id: int) -> list[int]:
        cursor = await self._conn.execute(
            "SELECT role_id FROM privileged_roles WHERE guild_id = ?",
            (int(guild_id),),
        )
        return [row[0] for row in await cursor.fetchall()]

    async def set_privileged_roles(self, guild_id: int, role_ids: list[int]) -> None:
        await self._conn.execute("DELETE FROM privileged_roles WHERE guild_id = ?", (int(guild_id),))
        for role_id in role_ids:
            await self._conn.execute(
                "INSERT OR IGNORE INTO privileged_roles (guild_id, role_id) VALUES (?, ?)",
                (int(guild_id), int(role_id)),
            )
        await self._conn.commit()

    # ---- member (position) roles ----

    async def member_roles(self, guild_id: int) -> dict[str, int | None]:
        cursor = await self._conn.execute(
            "SELECT member_id, elder_id, coleader_id FROM member_roles WHERE guild_id = ?",
            (int(guild_id),),
        )
        row = await cursor.fetchone()
        if not row:
            return {"member": None, "elder": None, "coLeader": None}
        return {"member": row[0], "elder": row[1], "coLeader": row[2]}

    async def set_member_role(self, guild_id: int, position: str, role_id: int) -> None:
        if position not in MEMBER_ROLE_POSITIONS:
            raise ValueError(f"Invalid position: {position}")
        await self._conn.execute(
            "INSERT INTO member_roles (guild_id) VALUES (?) ON CONFLICT (guild_id) DO NOTHING",
            (int(guild_id),),
        )
        await self._conn.execute(
            f"UPDATE member_roles SET {position}_id = ? WHERE guild_id = ?",
            (int(role_id), int(guild_id)),
        )
        await self._conn.commit()
