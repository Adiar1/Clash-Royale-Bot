import io
import statistics
from dataclasses import dataclass

import discord
import matplotlib
import numpy as np
from discord import Interaction, SelectOption, app_commands
from discord.ext import commands
from discord.ui import Select, View

from cogs.resolvers import resolve_clan_tag, resolve_player_tag
from errors import BotError
from services.clash_royale import former_member_tags, race_participants
from ui.embeds import excel_like_sort_key, make_embed
from ui.emojis import FAME_EMOJI, FORMER_MEMBER_EMOJI, MULTIDECK_EMOJI, NEW_MEMBER_EMOJI
from ui.views import DownloadCSVButton

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


@dataclass
class WarRow:
    tag: str
    name: str
    fame: int
    decks: int
    is_new: bool
    is_former: bool


DATA_ORDERS = {
    "fame_name_decks": ["fame", "name", "decks"],
    "fame_decks_name": ["fame", "decks", "name"],
    "name_fame_decks": ["name", "fame", "decks"],
    "name_decks_fame": ["name", "decks", "fame"],
    "decks_fame_name": ["decks", "fame", "name"],
    "decks_name_fame": ["decks", "name", "fame"],
}

LISTING_SORT_KEYS = {
    "fame_asc": lambda r: r.fame,
    "fame_desc": lambda r: r.fame,
    "decks_asc": lambda r: r.decks,
    "decks_desc": lambda r: r.decks,
    "name_asc": lambda r: excel_like_sort_key(r.name),
    "name_desc": lambda r: excel_like_sort_key(r.name),
    "tag_asc": lambda r: excel_like_sort_key(r.tag),
    "tag_desc": lambda r: excel_like_sort_key(r.tag),
}

WAR_TITLES = {
    "current": "Fame Earned and Decks Used in Current War by Members of {clan_name} #{clan_tag}",
    "last": "Fame Earned and Decks Used in Last War by Members of {clan_name} #{clan_tag}",
    "nth": "Fame Earned and Decks Used {n} Wars Ago by Members of {clan_name} #{clan_tag}",
}


def sort_war_rows(rows: list[WarRow], listing_order: str) -> list[WarRow]:
    key = LISTING_SORT_KEYS.get(listing_order, LISTING_SORT_KEYS["tag_asc"])
    return sorted(rows, key=key, reverse=listing_order.endswith("desc"))


def format_war_row(row: WarRow, order: list[str]) -> str:
    parts = []
    for column in order:
        if column == "fame":
            parts.append(str(row.fame))
        elif column == "decks":
            parts.append(str(row.decks))
        else:
            markers = f"{FORMER_MEMBER_EMOJI if row.is_former else ''}{' ' + NEW_MEMBER_EMOJI if row.is_new else ''}"
            parts.append(f"`{row.name}`{markers}")
    return " - ".join(parts)


def build_war_embed(mode: str, clan_name: str, clan_tag: str, n: int,
                    rows: list[WarRow], listing_order: str, data_order: str) -> discord.Embed:
    order = DATA_ORDERS.get(data_order, DATA_ORDERS["fame_name_decks"])
    sorted_rows = sort_war_rows(rows, listing_order)

    header = " - ".join(
        FAME_EMOJI if key == "fame" else MULTIDECK_EMOJI if key == "decks" else "Player"
        for key in order
    )
    lines = [format_war_row(row, order) for row in sorted_rows]
    title = WAR_TITLES[mode].format(clan_name=clan_name, clan_tag=clan_tag, n=n)

    embed = make_embed(title, "\n".join([header] + lines))
    embed.set_footer(
        text=f"{FORMER_MEMBER_EMOJI} Indicates a former member \n"
             f"{NEW_MEMBER_EMOJI} Indicates a member who joined after last war ended"
    )
    return embed


class WarListingSelect(Select):
    OPTIONS = [
        SelectOption(label="Sort by Fame Ascending", value="fame_asc"),
        SelectOption(label="Sort by Fame Descending", value="fame_desc"),
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Decks Used Ascending", value="decks_asc"),
        SelectOption(label="Sort by Decks Used Descending", value="decks_desc"),
        SelectOption(label="Sort by Tag A-Z", value="tag_asc"),
        SelectOption(label="Sort by Tag Z-A", value="tag_desc"),
    ]

    def __init__(self):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.listing_order = self.values[0]
        await self.view.refresh(interaction)


class WarDataOrderSelect(Select):
    OPTIONS = [
        SelectOption(label=f"Order: [{' - '.join(part.capitalize() for part in key.split('_'))}]", value=key)
        for key in DATA_ORDERS
    ]

    def __init__(self):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.data_order = self.values[0]
        await self.view.refresh(interaction)


class WarNSelect(Select):
    def __init__(self):
        options = [SelectOption(label=f"{i} Wars Ago", value=str(i)) for i in range(1, 11)]
        super().__init__(placeholder="Select War Number", options=options)

    async def callback(self, interaction: Interaction):
        self.view.n = int(self.values[0])
        await self.view.refresh(interaction)


class WarTableView(View):
    """Interactive war table; holds its own state instead of parsing embed titles."""

    def __init__(self, cog: "WarCog", mode: str, clan_tag: str, n: int,
                 listing_order: str = "tag_asc", data_order: str = "fame_name_decks"):
        super().__init__(timeout=600)
        self.cog = cog
        self.mode = mode
        self.clan_tag = clan_tag
        self.n = n
        self.listing_order = listing_order
        self.data_order = data_order
        self.csv_headers: list[str] = []
        self.csv_rows: list[list] = []

        if mode == "nth":
            self.add_item(WarNSelect())
        self.add_item(WarListingSelect())
        self.add_item(WarDataOrderSelect())
        self.add_item(DownloadCSVButton("clan_members.csv"))

    def update_csv(self, rows: list[WarRow]):
        order = DATA_ORDERS.get(self.data_order, DATA_ORDERS["fame_name_decks"])
        sorted_rows = sort_war_rows(rows, self.listing_order)
        self.csv_headers = order
        self.csv_rows = [
            [getattr(row, "name" if key == "name" else key) for key in order]
            for row in sorted_rows
        ]

    async def refresh(self, interaction: Interaction):
        await interaction.response.defer()
        clan_name, rows = await self.cog.fetch_war_rows(self.mode, self.clan_tag, self.n)
        embed = build_war_embed(self.mode, clan_name, self.clan_tag, self.n,
                                rows, self.listing_order, self.data_order)
        self.update_csv(rows)
        await interaction.edit_original_response(embed=embed, view=self)


class WarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def fetch_war_rows(self, mode: str, clan_tag: str, n: int) -> tuple[str, list[WarRow]]:
        clan = await self.bot.cr.clan(clan_tag)
        members = await self.bot.cr.clan_members(clan_tag)
        race = await self.bot.cr.current_river_race(clan_tag)
        history = await self.bot.cr.river_race_log(clan_tag)

        participants = race_participants(race) if mode == "current" else history.participants(n)
        former = former_member_tags(race, members)

        people = [(m.tag, m.name, False) for m in members]
        people += [(tag, name, True) for tag, name in former.items()]

        rows = []
        for tag, name, is_former in people:
            participant = participants.get(tag, {})
            row = WarRow(
                tag=tag,
                name=name,
                fame=int(participant.get("fame", 0)),
                decks=int(participant.get("decksUsed", 0)),
                is_new=history.is_new_member(tag),
                is_former=is_former,
            )
            # Former members who didn't fight in the current/last war are noise.
            if mode in ("current", "last") and is_former and row.decks == 0:
                continue
            rows.append(row)
        return clan["name"], rows

    async def _send_war_table(self, interaction: Interaction, mode: str, clan: str, n: int):
        await interaction.response.defer()
        clan_tag = await resolve_clan_tag(interaction, clan)
        clan_name, rows = await self.fetch_war_rows(mode, clan_tag, n)
        view = WarTableView(self, mode, clan_tag, n)
        embed = build_war_embed(mode, clan_name, clan_tag, n, rows, view.listing_order, view.data_order)
        view.update_csv(rows)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="currentwar",
                          description="Get information about how current members of a clan are performing this war")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)")
    async def currentwar(self, interaction: Interaction, clan_tag: str):
        await self._send_war_table(interaction, "current", clan_tag, 0)

    @app_commands.command(name="lastwar",
                          description="Get information about how current members of a clan performed last war")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)")
    async def lastwar(self, interaction: Interaction, clan_tag: str):
        await self._send_war_table(interaction, "last", clan_tag, 1)

    @app_commands.command(name="nthwar",
                          description="Get information about how current members of a clan performed n wars ago")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)", n="Number of wars ago (1-10)")
    async def nthwar(self, interaction: Interaction, clan_tag: str, n: app_commands.Range[int, 1, 10]):
        await self._send_war_table(interaction, "nth", clan_tag, n)

    @app_commands.command(name="stats", description="Calculate individual stats over a range of wars")
    @app_commands.describe(
        player_tag="The tag of the player (or a Discord @mention)",
        from_war="Starting from how many weeks ago (1-10)",
        to_war="Ending at how many weeks ago (1-10)",
    )
    async def stats(self, interaction: Interaction, player_tag: str,
                    from_war: app_commands.Range[int, 1, 10], to_war: app_commands.Range[int, 1, 10]):
        if from_war < to_war:
            raise BotError("The 'from' war must be greater or equal to the 'to' war, since it represents older wars.")
        tag = await resolve_player_tag(interaction, player_tag)
        await send_fame_stats(interaction, tag, from_war, to_war)


async def send_fame_stats(interaction: Interaction, player_tag: str, from_war: int, to_war: int):
    """Fame history graph + statistics for one player. Also used by the
    who-to-kick/promote player selects, so it must handle fresh interactions."""
    if not interaction.response.is_done():
        await interaction.response.defer()

    bot = interaction.client
    player = await bot.cr.player(player_tag)

    clan_info = player.get("clan")
    if not clan_info:
        raise BotError("This player is not currently in a clan.")

    history = await bot.cr.river_race_log(clan_info["tag"])
    war_numbers = list(range(from_war, to_war - 1, -1))
    fame_values = [history.fame(player_tag, n) for n in war_numbers]

    average_fame = statistics.mean(fame_values)
    median_fame = statistics.median(fame_values)

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 6))
    fig.patch.set_facecolor("#2F3136")
    ax.set_facecolor("#2F3136")

    plt.plot(war_numbers, fame_values, marker="o", linestyle="-" if len(fame_values) > 1 else "None",
             color="#1E133E", linewidth=2, markersize=8, markeredgecolor="white", markeredgewidth=1)

    if len(fame_values) > 1:
        trend_func = np.poly1d(np.polyfit(war_numbers, fame_values, 1))
        plt.plot(war_numbers, [trend_func(x) for x in war_numbers], color="#ff00d6",
                 linestyle="--", label="Regression Line", linewidth=2)
        next_war_prediction = trend_func(war_numbers[-1] - 1)
    else:
        next_war_prediction = fame_values[0]

    plt.axhline(y=average_fame, color="#9B59B6", linestyle="--",
                label=f"Average ({average_fame:.1f})", linewidth=2)
    plt.title(f"Fame History for {player.get('name')}", color="white", pad=20)
    plt.xlabel("Wars Ago", color="white")
    plt.ylabel("Fame", color="white")
    plt.grid(True, alpha=0.2, color="gray")
    ax.tick_params(colors="white")
    plt.gca().invert_xaxis()
    plt.legend(facecolor="#2F3136", edgecolor="gray", labelcolor="white",
               loc="upper left", bbox_to_anchor=(1, 1))
    plt.margins(x=0.05)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", facecolor="#2F3136", edgecolor="none", bbox_inches="tight")
    buf.seek(0)
    plt.close(fig)

    embed = make_embed("Fame Analysis", f"Player: {player.get('name')} (#{player_tag})")
    embed.add_field(
        name="War Range",
        value=f"From {from_war} to {to_war} wars ago \n {len(fame_values)} wars analyzed",
        inline=False,
    )
    embed.add_field(name="Average Fame", value=f"{FAME_EMOJI} {average_fame:.1f}", inline=True)
    embed.add_field(name="Median Fame", value=f"{FAME_EMOJI} {median_fame:.1f}", inline=True)
    embed.add_field(name="Highest Fame", value=f"{FAME_EMOJI} {max(fame_values)}", inline=True)
    embed.add_field(name="Lowest Fame", value=f"{FAME_EMOJI} {min(fame_values)}", inline=True)
    if len(fame_values) > 1:
        embed.add_field(name="Standard Deviation", value=f"{statistics.stdev(fame_values):.1f}", inline=True)
    embed.add_field(
        name=f"Prediction for {'current war' if to_war == 1 else f'{to_war - 1} wars ago'}",
        value=f"{FAME_EMOJI} {next_war_prediction:.1f}",
        inline=True,
    )

    file = discord.File(buf, filename="fame_graph.png")
    embed.set_image(url="attachment://fame_graph.png")
    await interaction.followup.send(file=file, embed=embed)
