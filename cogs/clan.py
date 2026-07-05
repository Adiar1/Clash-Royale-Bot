import discord
from discord import Interaction, SelectOption, app_commands
from discord.ext import commands
from discord.ui import Button, Select, View

from cogs.resolvers import resolve_clan_tag
from cogs.war import send_fame_stats
from services.clash_royale import ROLE_DISPLAY, former_member_tags
from services.scoring import MemberScore, score_members
from ui.embeds import make_embed
from ui.emojis import FAME_EMOJI, NEW_MEMBER_EMOJI
from ui.views import DownloadCSVButton

ROLE_ORDER = {"leader": 4, "coLeader": 3, "elder": 2, "member": 1, "former": 0}


# ---- /clan ----

CLAN_DATA_ORDERS = {
    "name_weeks_fame": ["name", "weeks", "fame"],
    "name_fame_weeks": ["name", "fame", "weeks"],
    "weeks_name_fame": ["weeks", "name", "fame"],
    "weeks_fame_name": ["weeks", "fame", "name"],
    "fame_name_weeks": ["fame", "name", "weeks"],
    "fame_weeks_name": ["fame", "weeks", "name"],
}

CLAN_SORT_KEYS = {
    "name_asc": lambda r: r["name"].lower(),
    "name_desc": lambda r: r["name"].lower(),
    "oldest_newest": lambda r: r["weeks"],
    "newest_oldest": lambda r: r["weeks"],
    "fame_asc": lambda r: r["fame"],
    "fame_desc": lambda r: r["fame"],
}


class ClanListingSelect(Select):
    OPTIONS = [
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Oldest to Newest", value="oldest_newest"),
        SelectOption(label="Sort by Newest to Oldest", value="newest_oldest"),
        SelectOption(label="Sort by Fame Descending", value="fame_desc"),
        SelectOption(label="Sort by Fame Ascending", value="fame_asc"),
    ]

    def __init__(self):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.listing_order = self.values[0]
        await self.view.refresh(interaction)


class ClanDataOrderSelect(Select):
    OPTIONS = [
        SelectOption(label=f"Order: [{' - '.join(part.capitalize() for part in key.split('_'))}]", value=key)
        for key in CLAN_DATA_ORDERS
    ]

    def __init__(self):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.data_order = self.values[0]
        await self.view.refresh(interaction)


class ClanTableView(View):
    def __init__(self, cog: "ClanCog", clan_tag: str,
                 listing_order: str = "name_asc", data_order: str = "name_weeks_fame"):
        super().__init__(timeout=600)
        self.cog = cog
        self.clan_tag = clan_tag
        self.listing_order = listing_order
        self.data_order = data_order
        self.csv_headers = ["Player", "Weeks Joined", "Avg Fame"]
        self.csv_rows: list[list] = []

        self.add_item(ClanListingSelect())
        self.add_item(ClanDataOrderSelect())
        self.add_item(DownloadCSVButton("clan_members.csv"))

    def update_csv(self, rows: list[dict]):
        self.csv_rows = [[r["name"], r["weeks"], r["fame"]] for r in self.cog.sort_clan_rows(rows, self.listing_order)]

    async def refresh(self, interaction: Interaction):
        await interaction.response.defer()
        rows = await self.cog.fetch_clan_rows(self.clan_tag)
        embed = self.cog.build_clan_embed(self.clan_tag, rows, self.listing_order, self.data_order)
        self.update_csv(rows)
        await interaction.edit_original_response(embed=embed, view=self)


# ---- /whotokick & /whotopromote ----

class ScoreInfoButton(Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="More Info on Scoring")

    async def callback(self, interaction: Interaction):
        embed = make_embed(
            "How the Score is Calculated",
            "Score Weights:\n"
            "• Fame: 99.2%\n"
            "• Trend: 0.5%\n"
            "• Commitment: 0.3%\n\n"
            "Fame: Points scored on a linear model determined by average fame during time in clan\n\n"
            "Trend: Points scored on a logarithmic model determined by average rate of change in fame per week\n\n"
            "Commitment: Points scored on a linear model; 0 points for new members, 100 points for members "
            "who have been in the clan for at least 10 weeks",
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ScoredPlayerSelect(Select):
    def __init__(self, scores: list[MemberScore]):
        options = [
            SelectOption(
                label=f"{i}. {score.name}",
                value=f"{score.tag}|{score.weeks}",
                description=f"Score: {score.total:.2f}",
            )
            for i, score in enumerate(scores, 1)
        ]
        super().__init__(placeholder="Select a player for detailed stats", options=options)

    async def callback(self, interaction: Interaction):
        player_tag, weeks = self.values[0].split("|")
        await send_fame_stats(interaction, player_tag, from_war=int(weeks), to_war=1)


class ScoreView(View):
    def __init__(self, scores: list[MemberScore]):
        super().__init__(timeout=600)
        if scores:
            self.add_item(ScoredPlayerSelect(scores))
        self.add_item(ScoreInfoButton())


class ClanCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---- /clan ----

    async def fetch_clan_rows(self, clan_tag: str) -> list[dict]:
        members = await self.bot.cr.clan_members(clan_tag)
        history = await self.bot.cr.river_race_log(clan_tag)
        rows = []
        for member in members:
            rows.append({
                "name": member.name,
                "weeks": history.weeks_in_clan(member.tag),
                "fame": history.average_fame(member.tag),
                "discord_id": await self.bot.repo.discord_id_for_tag(member.tag),
            })
        return rows

    @staticmethod
    def sort_clan_rows(rows: list[dict], listing_order: str) -> list[dict]:
        key = CLAN_SORT_KEYS.get(listing_order, CLAN_SORT_KEYS["name_asc"])
        return sorted(rows, key=key, reverse=listing_order in ("name_desc", "newest_oldest", "fame_desc"))

    def build_clan_embed(self, clan_tag: str, rows: list[dict], listing_order: str, data_order: str) -> discord.Embed:
        order = CLAN_DATA_ORDERS.get(data_order, CLAN_DATA_ORDERS["name_weeks_fame"])
        headers = {"name": "Player", "weeks": "Weeks Ago Joined", "fame": f"Avg {FAME_EMOJI}"}

        def format_row(row: dict) -> str:
            parts = []
            for key in order:
                if key == "name":
                    mention = f" <@{row['discord_id']}>" if row["discord_id"] else ""
                    parts.append(f"`{row['name']}`{mention}")
                elif key == "weeks":
                    parts.append(str(row["weeks"]))
                else:
                    parts.append(f"{int(row['fame']):,}")
            return " - ".join(parts)

        lines = [format_row(row) for row in self.sort_clan_rows(rows, listing_order)]
        header_line = " - ".join(headers[key] for key in order)
        embed = make_embed(
            f"Average Fame and Weeks Ago Joined Members of Clan #{clan_tag}",
            "\n".join([header_line] + lines),
        )
        embed.set_footer(
            text="Average fame is calculated individually for each member throughout that member's time "
                 "with the clan. Maximum memory of 10 weeks"
        )
        return embed

    @app_commands.command(name="clan", description="List current clan members and how many weeks ago they joined")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)")
    async def clan(self, interaction: Interaction, clan_tag: str):
        await interaction.response.defer()
        tag = await resolve_clan_tag(interaction, clan_tag)
        rows = await self.fetch_clan_rows(tag)
        view = ClanTableView(self, tag)
        embed = self.build_clan_embed(tag, rows, view.listing_order, view.data_order)
        view.update_csv(rows)
        await interaction.followup.send(embed=embed, view=view)

    # ---- /members ----

    async def fetch_member_rows(self, clan_tag: str, view_mode: str) -> tuple[str, list[dict]]:
        if view_mode == "former":
            race = await self.bot.cr.current_river_race(clan_tag)
            members = await self.bot.cr.clan_members(clan_tag)
            former = former_member_tags(race, members)
            return "Former Members", [
                {"tag": tag, "name": name, "role": "former", "is_new": False}
                for tag, name in former.items()
            ]

        clan = await self.bot.cr.clan(clan_tag)
        members = await self.bot.cr.clan_members(clan_tag)
        history = await self.bot.cr.river_race_log(clan_tag)
        rows = [
            {"tag": m.tag, "name": m.name, "role": m.role, "is_new": history.is_new_member(m.tag)}
            for m in members
        ]
        if view_mode == "new":
            rows = [r for r in rows if r["is_new"]]
        elif view_mode == "none":
            rows = [r for r in rows if not r["is_new"]]
        return clan["name"], rows

    @app_commands.command(name="members", description="Get information about the current members of a clan")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)")
    async def members(self, interaction: Interaction, clan_tag: str):
        await interaction.response.defer()
        tag = await resolve_clan_tag(interaction, clan_tag)
        view = MembersTableView(self, tag)
        clan_name, rows = await self.fetch_member_rows(tag, view.view_mode)
        embed = view.build_embed(clan_name, rows)
        view.update_csv(rows)
        await interaction.followup.send(embed=embed, view=view)

    # ---- /whotokick & /whotopromote ----

    async def _send_recommendations(self, interaction: Interaction, clan: str, n: int,
                                    exclude_leadership: bool, promote: bool):
        await interaction.response.defer()
        clan_tag = await resolve_clan_tag(interaction, clan)

        clan_info = await self.bot.cr.clan(clan_tag)
        members = await self.bot.cr.clan_members(clan_tag)
        history = await self.bot.cr.river_race_log(clan_tag)

        roles = {m.tag: m.role for m in members}
        scores = score_members(members, history)
        eligible = [s for s in scores if s.total is not None]
        if exclude_leadership:
            eligible = [s for s in eligible if roles.get(s.tag) not in ("coLeader", "leader")]
        eligible.sort(key=lambda s: s.total, reverse=promote)
        top = eligible[:n]

        kind = "promotion" if promote else "kick"
        embed = make_embed(
            f"{'Promotion' if promote else 'Kick'} Recommendations for {clan_info['name']} (#{clan_tag})",
            f"Here are the top {min(n, len(eligible))} members "
            f"{'who might deserve a promotion' if promote else 'recommended for removal'}:",
        )

        for i, score in enumerate(top, 1):
            role_display = ROLE_DISPLAY.get(roles.get(score.tag), "Unknown")
            embed.add_field(
                name=f"{i}. `{score.name}` ({score.tag}) | {role_display}",
                value=f"**Total Score: {score.total:.2f}/3630**\n"
                      f"-Fame: {score.fame_score:.2f}/3600\n"
                      f"-Trend: {'📈' if score.slope_score >= 10 else '📉'} {abs(score.slope_score):.2f}/20\n"
                      f"-Commitment: {score.weeks}/10",
                inline=False,
            )

        if len(eligible) < n:
            embed.add_field(
                name="Note",
                value=f"Only {len(eligible)} members were eligible for {kind} recommendations. "
                      f"New members are not included.",
                inline=False,
            )

        new_members = [s for s in scores if s.total is None]
        if new_members:
            embed.add_field(
                name="Excluded Members",
                value=f"The following {len(new_members)} new member(s) were not considered: "
                      f"\n`{', '.join(s.name for s in new_members)}`",
                inline=False,
            )

        if exclude_leadership:
            embed.set_footer(text="Co-Leaders and Leaders were excluded from recommendations")

        await interaction.followup.send(embed=embed, view=ScoreView(top))

    @app_commands.command(name="whotokick", description="Get recommendations for members to kick from the clan")
    @app_commands.describe(
        clan_tag="Enter either a clan tag or a nickname",
        n="Number of members to list (1-24)",
        exclude_leadership="Exclude Co-Leaders and Leaders from kick recommendations",
    )
    async def whotokick(self, interaction: Interaction, clan_tag: str,
                        n: app_commands.Range[int, 1, 24] = 5, exclude_leadership: bool = False):
        await self._send_recommendations(interaction, clan_tag, n, exclude_leadership, promote=False)

    @app_commands.command(name="whotopromote",
                          description="Get recommendations for members who might deserve a promotion")
    @app_commands.describe(
        clan_tag="Enter either a clan tag or a nickname",
        n="Number of members to list (1-24)",
        exclude_leadership="Exclude Co-Leaders and Leaders from promotion recommendations",
    )
    async def whotopromote(self, interaction: Interaction, clan_tag: str,
                           n: app_commands.Range[int, 1, 24] = 5, exclude_leadership: bool = False):
        await self._send_recommendations(interaction, clan_tag, n, exclude_leadership, promote=True)

    # ---- /viewlinks ----

    @app_commands.command(name="viewlinks", description="List all players in a clan")
    @app_commands.describe(clan_tag="Enter either a clan tag or nickname")
    async def viewlinks(self, interaction: Interaction, clan_tag: str):
        await interaction.response.defer()
        tag = await resolve_clan_tag(interaction, clan_tag)
        clan = await self.bot.cr.clan(tag)
        members = await self.bot.cr.clan_members(tag)

        lines = []
        for member in members:
            discord_id = await self.bot.repo.discord_id_for_tag(member.tag)
            lines.append(f"<@{discord_id}>" if discord_id else f"`{member.name}`")

        message = f"**Members of {clan['name']} (#{tag}):**\n\n" + "\n".join(lines)
        await interaction.followup.send(
            message[:2000],
            allowed_mentions=discord.AllowedMentions(users=[]),
        )


# ---- /members view (needs ClanCog defined for type hints in callbacks) ----

MEMBER_DATA_ORDERS = {
    "tag_name_role": "Tag - Name - Rank",
    "tag_role_name": "Tag - Rank - Name",
    "name_tag_role": "Name - Tag - Rank",
    "name_role_tag": "Name - Rank - Tag",
    "role_tag_name": "Rank - Tag - Name",
    "role_name_tag": "Rank - Name - Tag",
}

VIEW_MODES = [
    ("all", "View: All Members", "Members:"),
    ("new", "View: Only New Members", "New members:"),
    ("former", "View: Only Former Members", "Former members:"),
    ("none", "View: No New Members", "Everyone but the new members:"),
]


class MembersListingSelect(Select):
    OPTIONS = [
        SelectOption(label="Sort Name A-Z", value="name_asc"),
        SelectOption(label="Sort Name Z-A", value="name_desc"),
        SelectOption(label="Sort Tag A-Z", value="tag_asc"),
        SelectOption(label="Sort Tag Z-A", value="tag_desc"),
        SelectOption(label="Sort by Rank Descending", value="role_desc"),
        SelectOption(label="Sort by Rank Ascending", value="role_asc"),
    ]

    def __init__(self):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.listing_order = self.values[0]
        await self.view.refresh(interaction)


class MembersDataOrderSelect(Select):
    OPTIONS = [
        SelectOption(label=f"Order: [{label.replace(' - ', ', ')}]", value=key)
        for key, label in MEMBER_DATA_ORDERS.items()
    ]

    def __init__(self):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.data_order = self.values[0]
        await self.view.refresh(interaction)


class ToggleMemberViewButton(Button):
    def __init__(self):
        super().__init__(label=VIEW_MODES[0][1], style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: Interaction):
        current = next(i for i, (mode, _, _) in enumerate(VIEW_MODES) if mode == self.view.view_mode)
        self.view.view_mode = VIEW_MODES[(current + 1) % len(VIEW_MODES)][0]
        self.label = VIEW_MODES[(current + 1) % len(VIEW_MODES)][1]
        await self.view.refresh(interaction)


class MembersTableView(View):
    def __init__(self, cog: ClanCog, clan_tag: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.clan_tag = clan_tag
        self.listing_order = "name_asc"
        self.data_order = "name_tag_role"
        self.view_mode = "all"
        self.csv_headers = ["Tag", "Name", "Rank", "New Member"]
        self.csv_rows: list[list] = []

        self.add_item(MembersListingSelect())
        self.add_item(MembersDataOrderSelect())
        self.add_item(DownloadCSVButton("clan_members.csv"))
        self.add_item(ToggleMemberViewButton())

    def sort_rows(self, rows: list[dict]) -> list[dict]:
        order = self.listing_order
        if order.startswith("tag"):
            rows = sorted(rows, key=lambda r: r["tag"], reverse=order.endswith("desc"))
        elif order.startswith("name"):
            rows = sorted(rows, key=lambda r: r["name"], reverse=order.endswith("desc"))
        elif order == "role_desc":
            rows = sorted(rows, key=lambda r: (ROLE_ORDER.get(r["role"], 5), not r["is_new"], r["name"]), reverse=True)
        elif order == "role_asc":
            rows = sorted(rows, key=lambda r: (not r["is_new"], ROLE_ORDER.get(r["role"], 5), r["name"]))
        return rows

    def build_embed(self, clan_name: str, rows: list[dict]) -> discord.Embed:
        rows = self.sort_rows(rows)
        text = next(t for mode, _, t in VIEW_MODES if mode == self.view_mode)

        def format_row(row: dict) -> str:
            name = f"`{row['name']}`{NEW_MEMBER_EMOJI if row['is_new'] else ''}"
            values = {"tag": row["tag"], "name": name, "role": ROLE_DISPLAY.get(row["role"], row["role"])}
            return " - ".join(values[key] for key in self.data_order.split("_"))

        header = MEMBER_DATA_ORDERS[self.data_order]
        description = f"** {text} {len(rows)}**\n\n{header}\n" + "\n".join(format_row(r) for r in rows)
        return make_embed(f"Members of {clan_name} #{self.clan_tag}", description)

    def update_csv(self, rows: list[dict]):
        self.csv_rows = [
            [r["tag"], r["name"], r["role"], "Yes" if r["is_new"] else "No"]
            for r in self.sort_rows(rows)
        ]

    async def refresh(self, interaction: Interaction):
        await interaction.response.defer()
        clan_name, rows = await self.cog.fetch_member_rows(self.clan_tag, self.view_mode)
        embed = self.build_embed(clan_name, rows)
        self.update_csv(rows)
        await interaction.edit_original_response(embed=embed, view=self)
