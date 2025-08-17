from utils.api import is_real_clan_tag, get_current_clan_members, get_role
from utils.scores import get_member_scores
import discord
from discord import Interaction, ButtonStyle, SelectOption
from discord.ui import View, Button, Select
from commands.stats import handle_stats_command
from utils.helpers import get_clan_tag_by_nickname, sanitize_tag


class InfoButton(Button):
    def __init__(self):
        super().__init__(style=ButtonStyle.primary, label="More Info on Scoring")

    async def callback(self, interaction: Interaction):
        info_embed = discord.Embed(
            title="How the Score is Calculated",
            description=(
                "Score Weights:\n"
                "• Fame: 99.2%\n"
                "• Trend: 0.5%\n"
                "• Commitment: 0.3%\n\n"
                "Fame: Points scored on a linear model determined by average fame during time in clan\n\n"
                "Trend: Points scored on a logarithmic model determined by average rate of change in fame per week\n\n"
                "Commitment: Points scored on a linear model; 0 points for new members, 100 points for members who have been in the clan for at least 10 weeks"
            ),
            color=0x1E133E
        )
        await interaction.response.send_message(embed=info_embed, ephemeral=True)


class PlayerSelectView(View):
    def __init__(self, players):
        super().__init__()
        self.add_item(PlayerSelect(players))
        self.add_item(InfoButton())


class PlayerSelect(Select):
    def __init__(self, players):
        options = [
            SelectOption(
                label=f"{i+1}. {player['name']}",
                value=f"{player['tag']}|{player['weeks']}",
                description=f"Score: {player['score']:.2f}"
            )
            for i, player in enumerate(players)
        ]
        super().__init__(placeholder="Select a player for detailed stats", options=options)

    async def callback(self, interaction: Interaction):
        player_tag, weeks_old = self.values[0].split('|')
        from_war = int(weeks_old)
        to_war = 1
        await handle_stats_command(interaction, player_tag, from_war, to_war)


async def handle_whotopromote_command(bot, interaction: Interaction, input_value: str, n: int, exclude_leadership: bool):
    await interaction.response.defer()

    try:
        # Check if input is a nickname or a clan tag
        if len(input_value) < 5:
            clan_tag = get_clan_tag_by_nickname(input_value, interaction.guild.id)
            if clan_tag is None:
                await interaction.followup.send("Invalid nickname. Please check and try again.", ephemeral=True)
                return
        else:
            clan_tag = sanitize_tag(input_value)

        # Verify the clan tag
        if not await is_real_clan_tag(clan_tag):
            await interaction.followup.send("Invalid clan tag. Please check and try again.", ephemeral=True)
            return

        # Get clan name and members
        clan_name, members = await get_current_clan_members(clan_tag)

        # Get roles for each member
        members_with_roles = []
        for tag, name in members:
            role = await get_role(clan_tag, tag)
            members_with_roles.append((tag, name, role))

        member_scores = await get_member_scores(clan_tag)

        # Filter out members with "N/A" scores
        filtered_scores = [m for m in member_scores if m[2] != "N/A"]

        # If exclude_leadership is True, remove co-leaders and leaders
        if exclude_leadership:
            filtered_scores = [
                m for m in filtered_scores
                if next((role for t, n, role in members_with_roles if t == m[0]), '') not in ['coLeader', 'leader']
            ]

        # Sort the filtered members by score (highest first)
        sorted_members = sorted(filtered_scores, key=lambda x: x[2], reverse=True)

        # Create embed
        embed = discord.Embed(
            title=f"Promotion Recommendations for {clan_name} (#{clan_tag})",
            description=f"Here are the top {min(n, len(sorted_members))} members who might deserve a promotion:",
            color=0x1E133E
        )

        # Role display mapping
        role_display_map = {
            "member": "Member",
            "elder": "Elder",
            "leader": "Leader",
            "coLeader": "Co-leader"
        }

        top_performers = []
        for i, (tag, name, score, fame_split, slope_split, weeks_split) in enumerate(sorted_members[:n], 1):
            # Find the role for this member
            member_role = next((role for t, n, role in members_with_roles if t == tag), "Unknown")
            role_display = role_display_map.get(member_role, member_role)

            embed.add_field(
                name=f"{i}. `{name}` ({tag}) | {role_display}",
                value=f"**Total Score: {score:.2f}/3630**\n"
                      f"-Fame: {fame_split:.2f}/3600\n"
                      f"-Trend: {'📈' if slope_split >= 10 else '📉'} {abs(slope_split):.2f}/20\n"
                      f"-Commitment: {weeks_split}/10",
                inline=False
            )
            top_performers.append({
                'name': name,
                'tag': tag,
                'weeks': weeks_split,
                'score': score,
                'role': role_display
            })

        if len(sorted_members) < n:
            embed.add_field(
                name="Note",
                value=f"Only {len(sorted_members)} members were eligible for promotion recommendations. "
                      f"New members are not included.",
                inline=False
            )

        # Add information about excluded members
        excluded_members = [m for m in member_scores if m[2] == "N/A"]
        if excluded_members:
            excluded_names = ", ".join([m[1] for m in excluded_members])
            embed.add_field(
                name="Excluded Members",
                value=f"The following {len(excluded_members)} new member(s) were not considered: "
                      f"\n`{excluded_names}`",
                inline=False
            )

        # If leadership was excluded, add a note about that
        if exclude_leadership:
            embed.set_footer(text="Co-Leaders and Leaders were excluded from recommendations")

        # Create a View with the PlayerSelect and InfoButton
        view = PlayerSelectView(top_performers)

        await interaction.followup.send(embed=embed, view=view)

    except Exception as e:
        print(f"Error in whotopromote command: {e}")
        await interaction.followup.send("An error occurred while processing your request.")