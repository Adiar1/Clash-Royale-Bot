import numpy as np
import math

import asyncio

from utils.api import get_current_clan_members, get_weeks_ago_joined, get_fame_n_wars_ago


async def get_member_scores(clan_tag: str):
    # Get the current clan members and weeks ago joined concurrently
    clan_members_task = get_current_clan_members(clan_tag)
    weeks_joined_task = get_weeks_ago_joined(clan_tag)
    _, current_members = await clan_members_task
    member_weeks = await weeks_joined_task

    weeks_dict = {tag: weeks for tag, name, weeks in member_weeks}

    async def process_member(member_tag, member_name):
        weeks_old = weeks_dict.get(member_tag, 0)

        if weeks_old == 0:
            return member_tag, member_name, "N/A", "N/A", "N/A", "N/A"

        # Collect fame data for regression
        fame_tasks = [get_fame_n_wars_ago(clan_tag, member_tag, n) for n in range(1, weeks_old + 1)]
        fame_data = await asyncio.gather(*fame_tasks)

        fame_data = [(n, float(fame)) for n, fame in enumerate(fame_data, 1) if fame is not None]
        total_fame = sum(fame for _, fame in fame_data)

        # Calculate average fame
        average_fame = total_fame / weeks_old if weeks_old > 0 else 0

        # Calculate slope of regression line
        if len(fame_data) > 1:
            x, y = zip(*fame_data)
            slope, _ = -1 * (np.polyfit(x, y, 1))
        else:
            slope = 0

        # Calculate scores for each component
        fame_score = average_fame

        # logarithmic slope scoring
        def slope_score(slope):
            if slope == 0:
                return 10
            elif slope > 0:
                return 10 + 10 * (1 - 1 / (1 + math.log(1 + slope / 3600, 1.03)))
            else:
                return 10 - 10 * (1 - 1 / (1 + math.log(1 - slope / 3600, 1.03)))

        slope_score = slope_score(slope)

        weeks_old_score = weeks_old

        # Calculate total score
        total_score = fame_score + slope_score + weeks_old_score
        fame_breakdown = fame_score
        slope_breakdown = slope_score
        weeks_breakdown = weeks_old_score

        return member_tag, member_name, total_score, fame_breakdown, slope_breakdown, weeks_breakdown

    # Process all members concurrently
    member_scores = await asyncio.gather(*[process_member(tag, name) for tag, name in current_members])

    return member_scores
