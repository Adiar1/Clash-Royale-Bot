"""Clash Royale API client and in-memory war-log computations.

The client fetches whole responses (clan, members, current river race, race
log); everything per-member — fame, decks used, weeks in clan, new/former
status — is computed here from those responses instead of re-hitting the API
for each member.

Tags are handled in normalized form (no leading '#', uppercase) everywhere in
the bot; they are prefixed with '%23' only when building request URLs.
"""

from dataclasses import dataclass

import aiohttp

from errors import ClanNotFound, PlayerNotFound, TournamentNotFound
from services.http import BaseAPIClient, NotFoundError

BASE_URL = "https://api.clashroyale.com/v1"

ROLE_DISPLAY = {
    "member": "Member",
    "elder": "Elder",
    "coLeader": "Co-leader",
    "leader": "Leader",
    "former": "Former Member",
}


def normalize_tag(tag: str) -> str:
    """Canonical tag form: no '#', uppercase, common O/0 typo fixed."""
    return tag.strip().lstrip("#").upper().replace("O", "0")


@dataclass(frozen=True)
class ClanMember:
    tag: str  # normalized
    name: str
    role: str  # member | elder | coLeader | leader


@dataclass(frozen=True)
class TournamentPlayer:
    name: str
    score: int
    rank: int


class ClashRoyaleClient(BaseAPIClient):
    def __init__(self, session: aiohttp.ClientSession, api_key: str, base_url: str = BASE_URL):
        super().__init__(session, base_url, {"Authorization": f"Bearer {api_key}"})

    async def clan(self, clan_tag: str) -> dict:
        try:
            return await self.get_json(f"/clans/%23{normalize_tag(clan_tag)}")
        except NotFoundError:
            raise ClanNotFound() from None

    async def clan_members(self, clan_tag: str) -> list[ClanMember]:
        try:
            data = await self.get_json(f"/clans/%23{normalize_tag(clan_tag)}/members", params={"limit": 50})
        except NotFoundError:
            raise ClanNotFound() from None
        return [
            ClanMember(tag=normalize_tag(m["tag"]), name=m["name"], role=m["role"])
            for m in data.get("items", [])
        ]

    async def clan_exists(self, clan_tag: str) -> bool:
        try:
            await self.clan(clan_tag)
            return True
        except ClanNotFound:
            return False

    async def current_river_race(self, clan_tag: str) -> dict | None:
        """The in-progress river race, or None if the clan has no current race."""
        try:
            return await self.get_json(f"/clans/%23{normalize_tag(clan_tag)}/currentriverrace")
        except NotFoundError:
            return None

    async def river_race_log(self, clan_tag: str, limit: int = 10) -> "WarHistory":
        """Finished river races, most recent first (war 1 = last finished war)."""
        try:
            data = await self.get_json(f"/clans/%23{normalize_tag(clan_tag)}/riverracelog", params={"limit": limit})
        except NotFoundError:
            return WarHistory([])
        return WarHistory(data.get("items", []))

    async def player(self, player_tag: str) -> dict:
        try:
            return await self.get_json(f"/players/%23{normalize_tag(player_tag)}")
        except NotFoundError:
            raise PlayerNotFound() from None

    async def tournament(self, tournament_tag: str) -> tuple[str, list[TournamentPlayer]]:
        try:
            data = await self.get_json(f"/tournaments/%23{normalize_tag(tournament_tag)}")
        except NotFoundError:
            raise TournamentNotFound() from None
        players = [
            TournamentPlayer(name=p["name"], score=p["score"], rank=p["rank"])
            for p in data.get("membersList", [])
        ]
        return data.get("name", "Unknown Tournament"), players


# ---- In-memory war-log computations (no extra API calls) ----

def race_participants(race: dict | None) -> dict[str, dict]:
    """Participants of the clan's current river race, keyed by normalized tag."""
    if not race:
        return {}
    return {normalize_tag(p["tag"]): p for p in race.get("clan", {}).get("participants", [])}


def former_member_tags(race: dict | None, members: list[ClanMember]) -> dict[str, str]:
    """Race participants who are no longer in the clan: {normalized_tag: name}."""
    current = {m.tag for m in members}
    return {
        tag: participant.get("name", "Unknown")
        for tag, participant in race_participants(race).items()
        if tag not in current
    }


class WarHistory:
    """Finished river races for a clan, with per-war participant lookups.

    War numbers count backwards: war 1 is the most recently finished war.
    """

    def __init__(self, log_items: list[dict]):
        log_items = sorted(
            log_items,
            key=lambda item: (item.get("seasonId", 0), item.get("sectionIndex", 0)),
            reverse=True,
        )
        self._participants_by_war: list[dict[str, dict]] = []
        for item in log_items:
            participants: dict[str, dict] = {}
            for standing in item.get("standings", []):
                for player in standing.get("clan", {}).get("participants", []):
                    participants[normalize_tag(player["tag"])] = player
            self._participants_by_war.append(participants)

    def __len__(self) -> int:
        return len(self._participants_by_war)

    def participants(self, n: int) -> dict[str, dict]:
        """Participants n wars ago (across all clans in that race); {} if out of range."""
        if 1 <= n <= len(self._participants_by_war):
            return self._participants_by_war[n - 1]
        return {}

    def fame(self, member_tag: str, n: int) -> int:
        return int(self.participants(n).get(normalize_tag(member_tag), {}).get("fame", 0))

    def decks_used(self, member_tag: str, n: int) -> int:
        return int(self.participants(n).get(normalize_tag(member_tag), {}).get("decksUsed", 0))

    def weeks_in_clan(self, member_tag: str) -> int:
        """Consecutive wars (from the most recent) the member appears in.

        0 means the member joined after the last war ended ("new member").
        """
        tag = normalize_tag(member_tag)
        weeks = 0
        for n in range(1, len(self._participants_by_war) + 1):
            if tag not in self._participants_by_war[n - 1]:
                break
            weeks = n
        return weeks

    def is_new_member(self, member_tag: str) -> bool:
        return self.weeks_in_clan(member_tag) == 0

    def fame_history(self, member_tag: str, weeks: int) -> list[int]:
        """Fame per war for wars 1..weeks ago (most recent first)."""
        return [self.fame(member_tag, n) for n in range(1, weeks + 1)]

    def average_fame(self, member_tag: str) -> float:
        weeks = self.weeks_in_clan(member_tag)
        if weeks == 0:
            return 0.0
        return sum(self.fame_history(member_tag, weeks)) / weeks
