"""Member scoring used by /whotokick and /whotopromote.

Score = average fame + trend score + weeks in clan, computed entirely from an
already-fetched WarHistory. New members (0 finished wars in the clan) get
``total=None`` and are excluded from recommendations.
"""

import math
from dataclasses import dataclass

import numpy as np

from services.clash_royale import ClanMember, WarHistory


@dataclass(frozen=True)
class MemberScore:
    tag: str
    name: str
    total: float | None  # None => new member, not scorable
    fame_score: float
    slope_score: float
    weeks: int


def _slope_score(slope: float) -> float:
    if slope == 0:
        return 10
    if slope > 0:
        return 10 + 10 * (1 - 1 / (1 + math.log(1 + slope / 3600, 1.03)))
    return 10 - 10 * (1 - 1 / (1 + math.log(1 - slope / 3600, 1.03)))


def score_member(member: ClanMember, history: WarHistory) -> MemberScore:
    weeks = history.weeks_in_clan(member.tag)
    if weeks == 0:
        return MemberScore(tag=member.tag, name=member.name, total=None, fame_score=0, slope_score=0, weeks=0)

    fame_by_war = history.fame_history(member.tag, weeks)
    fame_score = sum(fame_by_war) / weeks

    if len(fame_by_war) > 1:
        x = range(1, weeks + 1)  # wars ago
        slope = -1 * np.polyfit(x, fame_by_war, 1)[0]
    else:
        slope = 0

    slope_score = _slope_score(slope)
    total = fame_score + slope_score + weeks
    return MemberScore(
        tag=member.tag,
        name=member.name,
        total=total,
        fame_score=fame_score,
        slope_score=slope_score,
        weeks=weeks,
    )


def score_members(members: list[ClanMember], history: WarHistory) -> list[MemberScore]:
    return [score_member(member, history) for member in members]
