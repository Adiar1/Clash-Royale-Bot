from datetime import datetime

import discord
from discord import ButtonStyle, Interaction, SelectOption, User, app_commands
from discord.ext import commands
from discord.ui import Select, View

from cogs.resolvers import resolve_player_tag
from errors import NoDeckAILink, NotLinked
from services.clash_royale import normalize_tag, race_participants
from services.deck_ai import DeckRecommendation, recommend_deck, split_available_decks
from ui.embeds import excel_like_sort_key, make_embed
from ui.emojis import (
    CC_EMOJI,
    CW2_EMOJI,
    EVOLUTION_EMOJI,
    FAME_EMOJI,
    FORMER_MEMBER_EMOJI,
    GC_EMOJI,
    LEAGUE_IMAGES,
    LEVEL_14_EMOJI,
    LEVEL_15_EMOJI,
    LEVEL_16_EMOJI,
    LEVEL_EMOJIS,
    MULTIDECK_EMOJI,
    NEW_MEMBER_EMOJI,
    RANKED_MEDAL_EMOJI,
    TROPHYROAD_EMOJI,
)
from ui.views import DownloadCSVButton

DEVELOPER_ID = 880093108153495563


# ---- /player ----

async def send_player_embed(interaction: Interaction, player_tag: str):
    """Detailed player embed; shared by /player and the /profile account select."""
    if not interaction.response.is_done():
        await interaction.response.defer()

    bot = interaction.client
    tag = normalize_tag(player_tag)
    player = await bot.cr.player(tag)

    clan_info = player.get("clan")
    current_fame = last_fame = current_decks = last_decks = 0
    if clan_info:
        clan_tag = clan_info["tag"]
        race = await bot.cr.current_river_race(clan_tag)
        history = await bot.cr.river_race_log(clan_tag)
        participant = race_participants(race).get(tag, {})
        current_fame = int(participant.get("fame", 0))
        current_decks = int(participant.get("decksUsed", 0))
        last_fame = history.fame(tag, 1)
        last_decks = history.decks_used(tag, 1)

    embed = make_embed(
        f"{player.get('name', '')} #{tag} {LEVEL_EMOJIS.get(player.get('expLevel', 0), '')}"
    )
    embed.url = f"https://royaleapi.com/player/{tag}"

    if clan_info:
        nohash_clan_tag = clan_info["tag"].strip("#")
        role = (player.get("role") or "").capitalize()
        embed.add_field(
            name="**__Clan__**",
            value=f"[{clan_info.get('name', 'No Clan')}](<https://royaleapi.com/clan/{nohash_clan_tag}>) "
                  f"#{nohash_clan_tag} ({role})",
            inline=True,
        )
    else:
        embed.add_field(name="**__Clan__**", value="No Clan", inline=True)

    embed.add_field(
        name="**__Trophy Road__**",
        value=f"Current: {TROPHYROAD_EMOJI} {player.get('trophies', 0)}\n"
              f"Best: {TROPHYROAD_EMOJI} {player.get('bestTrophies', 0)}",
        inline=False,
    )

    cards = player.get("cards", [])
    evolution_cards = [c for c in cards if c.get("evolutionLevel", 0) == 1]
    max_cards = [c for c in cards if c.get("level") == c.get("maxLevel", 0)]
    max_minus_1 = [c for c in cards if c.get("level") == c.get("maxLevel", 0) - 1]
    max_minus_2 = [c for c in cards if c.get("level") == c.get("maxLevel", 0) - 2]
    embed.add_field(
        name="**__Card Levels__**",
        value=(
            f"{EVOLUTION_EMOJI}: {len(evolution_cards)}\n"
            f"{LEVEL_16_EMOJI}: {len(max_cards)}\n"
            f"{LEVEL_15_EMOJI}: {len(max_minus_1)}\n"
            f"{LEVEL_14_EMOJI}: {len(max_minus_2)}"
        ),
        inline=False,
    )

    ranked_current = player.get("currentPathOfLegendSeasonResult", {})
    ranked_best = player.get("bestPathOfLegendSeasonResult", {})
    if ranked_current or ranked_best:
        embed.add_field(
            name="**__Ranked__**",
            value=f"Current: {_format_ranked_entry(ranked_current)}\nBest: {_format_ranked_entry(ranked_best)}",
            inline=False,
        )
        league = _league_number(ranked_current)
        if league and league in LEAGUE_IMAGES:
            embed.set_thumbnail(url=LEAGUE_IMAGES[league])

    badges = player.get("badges", [])

    def badge_progress(badge_name: str) -> str:
        return str(next((b.get("progress", "0") for b in badges if b.get("name") == badge_name), "0"))

    embed.add_field(name="**__CW2 Wins__**", value=f"{CW2_EMOJI} {badge_progress('ClanWarWins')}", inline=True)
    embed.add_field(name="**__CC Wins__**", value=f"{CC_EMOJI} {badge_progress('Classic12Wins')}", inline=True)
    embed.add_field(name="**__GC Wins__**", value=f"{GC_EMOJI} {badge_progress('Grand12Wins')}", inline=True)

    embed.add_field(
        name="**__Current War Stats__**",
        value=f"{FAME_EMOJI} {current_fame}\n{MULTIDECK_EMOJI} {current_decks}",
        inline=True,
    )
    embed.add_field(
        name="**__Last War Stats__**",
        value=f"{FAME_EMOJI} {last_fame}\n{MULTIDECK_EMOJI} {last_decks}",
        inline=True,
    )

    await interaction.followup.send(embed=embed)


def _league_number(ranked_entry: dict) -> int | None:
    try:
        league = ranked_entry.get("leagueNumber")
        return int(league) if league is not None else None
    except (ValueError, TypeError):
        return None


def _format_ranked_entry(ranked_entry: dict) -> str:
    league = _league_number(ranked_entry)
    if league is not None and league >= 7:
        display = f"{RANKED_MEDAL_EMOJI} {ranked_entry.get('trophies', 0)}"
        rank = ranked_entry.get("rank")
        if rank is not None:
            display += f" (Rank: #{rank})"
        return display
    if league is None:
        return "League ---"
    return f"League {league}"


# ---- /rankings ----

RANKINGS_DATA_ORDERS = {
    "score_name_rank": ["score", "name", "rank"],
    "score_rank_name": ["score", "rank", "name"],
    "name_score_rank": ["name", "score", "rank"],
    "name_rank_score": ["name", "rank", "score"],
    "rank_score_name": ["rank", "score", "name"],
    "rank_name_score": ["rank", "name", "score"],
}


class RankingsListingSelect(Select):
    OPTIONS = [
        SelectOption(label="Sort by Name A-Z", value="name_asc"),
        SelectOption(label="Sort by Name Z-A", value="name_desc"),
        SelectOption(label="Sort by Rank Ascending", value="rank_asc"),
        SelectOption(label="Sort by Rank Descending", value="rank_desc"),
    ]

    def __init__(self):
        super().__init__(placeholder="Select Listing Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.listing_order = self.values[0]
        await self.view.refresh(interaction)


class RankingsDataOrderSelect(Select):
    OPTIONS = [
        SelectOption(label=f"Order: [{' - '.join(part.capitalize() for part in key.split('_'))}]", value=key)
        for key in RANKINGS_DATA_ORDERS
    ]

    def __init__(self):
        super().__init__(placeholder="Select Data Order", options=self.OPTIONS)

    async def callback(self, interaction: Interaction):
        self.view.data_order = self.values[0]
        await self.view.refresh(interaction)


class RankingsView(View):
    def __init__(self, cog: "MiscCog", tourny_tag: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.tourny_tag = tourny_tag
        self.listing_order = "name_asc"
        self.data_order = "score_name_rank"
        self.csv_headers: list[str] = []
        self.csv_rows: list[list] = []

        self.add_item(RankingsListingSelect())
        self.add_item(RankingsDataOrderSelect())
        self.add_item(DownloadCSVButton("tournament_rankings.csv"))

    def render(self, name: str, players) -> discord.Embed:
        order = RANKINGS_DATA_ORDERS.get(self.data_order, RANKINGS_DATA_ORDERS["score_name_rank"])

        if self.listing_order.startswith("name"):
            players = sorted(players, key=lambda p: excel_like_sort_key(p.name),
                             reverse=self.listing_order.endswith("desc"))
        else:
            players = sorted(players, key=lambda p: p.rank, reverse=self.listing_order.endswith("desc"))

        def format_player(p) -> str:
            values = {"score": str(p.score), "rank": str(p.rank), "name": f"`{p.name}`"}
            return " - ".join(values[key] for key in order)

        header = " - ".join(key.capitalize() for key in order)
        lines = [format_player(p) for p in players]
        description = "\n".join([header] + lines)
        if len(description) > 4096:
            description = description[:4060] + "\n \n Download CSV to see more"

        self.csv_headers = order
        self.csv_rows = [[getattr(p, key) for key in order] for p in players]
        return make_embed(f"{name} - Tournament #{self.tourny_tag}", description)

    async def refresh(self, interaction: Interaction):
        await interaction.response.defer()
        name, players = await interaction.client.cr.tournament(self.tourny_tag)
        embed = self.render(name, players)
        await interaction.edit_original_response(embed=embed, view=self)


# ---- /spy_ai output formatting ----

def format_spy_report(war_data: dict | None) -> str:
    if not war_data:
        return "❌ **No data found** - The opponent might not have any recent clan war activity"

    opponent_decks = war_data.get("opponentDecks", [])
    player_decks = war_data.get("playerDecks", [])
    if not opponent_decks:
        return "🕵️ **Clan War Spy Report**\n\n❌ **No opponent deck data found**"

    available, used_today = split_available_decks(opponent_decks)

    lines = ["🕵️ **Clan War Spy Report**", ""]

    if player_decks:
        lines.append("**Your Decks Today**")
        for idx, deck in enumerate(player_decks, 1):
            lines.append(f"**Your Deck {idx}:** {_format_deck_cards(deck)}")
        lines.append("")

    availability_note = f" ({len(used_today)} already used today)" if used_today else ""
    lines.append(f"📊 **Opponent has {len(available)} deck(s) available for their next duel**{availability_note}")
    lines.append("")

    for idx, deck in enumerate(available, 1):
        if not isinstance(deck, dict):
            lines.append(f"⚠️ **Opponent Deck {idx}:** Invalid data format")
            continue
        lines.extend([
            f"🃏 **Opponent Deck {idx}:** {_format_deck_cards(deck.get('deck', []))}",
            f"   **Game Mode:** {deck.get('gameMode', 'Unknown Mode')} | "
            f"**Last Used:** {_format_spy_date(deck.get('date', ''))}",
            f"   **Win Rate vs Your Decks:** {_format_win_rates_labeled(deck.get('winRates', []))}",
            "",
        ])

    if player_decks and available:
        recommendation = recommend_deck(player_decks, available)
        if recommendation is not None:
            lines.append(
                f"💡 **Suggested opening deck:** Your Deck {recommendation.player_deck_index + 1} "
                f"(avg {recommendation.average_win_rate * 100:.1f}% across their available decks)"
            )
            lines.append("")

    if used_today:
        lines.append("🔒 **Already used today (unavailable for a new duel):**")
        for deck in used_today:
            if not isinstance(deck, dict):
                continue
            lines.append(
                f"   {_format_deck_cards(deck.get('deck', []))} — used {_format_spy_date(deck.get('date', ''))}"
            )
        lines.append("")

    return "\n".join(lines)


def _format_deck_cards(cards: list) -> str:
    if not cards:
        return "No card data available"
    body = _format_card_list(cards[:8])
    if len(cards) >= 9 and isinstance(cards[8], dict):
        tower = cards[8]
        body += f" (Tower: {tower.get('name', 'Unknown Tower')} Lvl {tower.get('level', '?')})"
    return body


def _format_card_list(cards: list) -> str:
    parts = []
    for card in cards:
        if isinstance(card, dict):
            parts.append(f"{card.get('name', 'Unknown Card')} (Lvl {card.get('level', '?')})")
        else:
            parts.append(str(card))
    return ", ".join(parts) if parts else "No cards found"


def _format_win_rates_labeled(win_rates: list) -> str:
    if not win_rates or not isinstance(win_rates, list):
        return "No win rate data"
    parts = []
    for idx, rate in enumerate(win_rates, 1):
        try:
            parts.append(f"Deck {idx}: {float(rate) * 100:.1f}%")
        except (ValueError, TypeError):
            continue
    return " | ".join(parts) if parts else "No win rate data"


def _format_spy_date(date_str: str) -> str:
    if not date_str:
        return "Unknown Date"
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return date_str


def chunk_message(text: str, limit: int = 1990) -> list[str]:
    chunks = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
                current = line
            else:
                chunks.append(line[:limit] + "...")
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)
    return chunks


def _deck_option_label(prefix: str, cards: list, max_names: int = 3) -> str:
    names = [c.get("name", "?") for c in cards[:8] if isinstance(c, dict)] if cards else []
    shown = ", ".join(names[:max_names])
    extra = len(names) - max_names
    summary = f"{shown} +{extra} more" if extra > 0 else shown
    return f"{prefix}: {summary}"[:100]


class _DeckPlayedSelect(Select):
    """Records which deck (opponent's or the user's) was played in the current match."""

    def __init__(self, placeholder: str, options: list[SelectOption], kind: str):
        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)
        self.kind = kind

    async def callback(self, interaction: Interaction):
        view: SpyDuelView = self.view
        if self.kind == "opponent":
            view.opponent_choice = int(self.values[0])
        else:
            view.player_choice = int(self.values[0])
        await view.maybe_advance(interaction)


class SpyDuelView(View):
    """Interactive duel tracker: after each match, records which deck each side played
    and recommends the player's best remaining deck for the next one.

    A duel is best-of-3, so at most 2 rounds of "what got played" are needed:
    match 1's result informs the match-2 pick, and match 2's result informs match 3's.
    """

    ROUNDS = 2

    def __init__(self, author_id: int, player_decks: list, available_opponent_decks: list[dict]):
        super().__init__(timeout=1800)
        self.author_id = author_id
        self.player_decks = player_decks
        # (original index, deck) so numbering stays stable across rounds as decks are removed.
        self.remaining_opponent_decks: list[tuple[int, dict]] = list(enumerate(available_opponent_decks))
        self.remaining_player_indices = list(range(len(player_decks)))
        self.rounds_completed = 0
        self.opponent_choice: int | None = None
        self.player_choice: int | None = None
        self._build_round()

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.author_id

    def _build_round(self):
        self.clear_items()
        match_n = self.rounds_completed + 1
        opponent_options = [
            SelectOption(
                label=_deck_option_label(f"Opponent Deck {original_i + 1}", deck.get("deck", [])), value=str(pos)
            )
            for pos, (original_i, deck) in enumerate(self.remaining_opponent_decks)
        ]
        player_options = [
            SelectOption(label=_deck_option_label(f"Your Deck {i + 1}", self.player_decks[i]), value=str(i))
            for i in self.remaining_player_indices
        ]
        self.add_item(_DeckPlayedSelect(f"Which deck did THEY play in Match {match_n}?", opponent_options, "opponent"))
        self.add_item(_DeckPlayedSelect(f"Which deck did YOU play in Match {match_n}?", player_options, "player"))

    async def maybe_advance(self, interaction: Interaction):
        if self.opponent_choice is None or self.player_choice is None:
            await interaction.response.defer()
            return

        match_n = self.rounds_completed + 1
        played_player_deck = self.player_choice
        self.remaining_opponent_decks.pop(self.opponent_choice)
        self.remaining_player_indices.remove(played_player_deck)
        self.rounds_completed += 1
        self.opponent_choice = self.player_choice = None

        lines = [f"✅ **Match {match_n} recorded** (you played Your Deck {played_player_deck + 1})."]

        has_data_left = bool(self.remaining_opponent_decks and self.remaining_player_indices)
        if has_data_left:
            excluded = frozenset(range(len(self.player_decks))) - set(self.remaining_player_indices)
            remaining_decks_only = [deck for _, deck in self.remaining_opponent_decks]
            recommendation: DeckRecommendation | None = recommend_deck(
                self.player_decks, remaining_decks_only, excluded
            )
            if recommendation is not None:
                lines.append(
                    f"💡 **Suggested pick for Match {match_n + 1}:** Your Deck {recommendation.player_deck_index + 1} "
                    f"(avg {recommendation.average_win_rate * 100:.1f}% against their remaining "
                    f"{len(self.remaining_opponent_decks)} deck(s))"
                )
            else:
                lines.append("⚠️ Not enough data to recommend a next deck.")
        else:
            lines.append("🏁 No more opponent deck data to predict against.")

        can_continue = self.rounds_completed < self.ROUNDS and has_data_left
        if can_continue:
            self._build_round()
        else:
            self.stop()
            self.clear_items()

        await interaction.response.edit_message(content="\n".join(lines), view=self)


class MiscCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="player", description="Get detailed information about a Clash Royale player")
    @app_commands.describe(player_tag="The tag of the player (or a Discord @mention)")
    async def player(self, interaction: Interaction, player_tag: str):
        tag = await resolve_player_tag(interaction, player_tag)
        await send_player_embed(interaction, tag)

    @app_commands.command(name="rankings", description="List members' names, scores, and ranks")
    @app_commands.describe(tourny_tag="The tag of the tournament")
    async def rankings(self, interaction: Interaction, tourny_tag: str):
        await interaction.response.defer()
        tag = normalize_tag(tourny_tag)
        name, players = await self.bot.cr.tournament(tag)
        view = RankingsView(self, tag)
        embed = view.render(name, players)
        await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(
        name="spy_ai",
        description="Scout an opponent's available war-duel decks and your win rate against each",
    )
    @app_commands.describe(
        opponent_player_tag="The player tag of who you're dueling",
        someone_else="Optionally mention the user actually dueling them, if not you",
    )
    async def spy_ai(self, interaction: Interaction, opponent_player_tag: str, someone_else: User | None = None):
        await interaction.response.defer()

        opponent_tag = normalize_tag(opponent_player_tag)
        target_user = someone_else or interaction.user

        player_tags = await self.bot.repo.player_tags(target_user.id)
        if not player_tags:
            raise NotLinked(
                f"No player tags found for {'the specified user' if someone_else else 'you'}. "
                "Please link your player tag using `/link` first."
            )

        account_id = None
        for tag in player_tags:
            account_id = await self.bot.repo.deckai_id(tag)
            if account_id:
                break
        if not account_id:
            raise NoDeckAILink(
                f"No DeckAI ID found for {'the specified user' if someone_else else 'you'}. "
                "Please link your DeckAI ID using `/link` first."
            )

        war_data = await self.bot.deckai.clan_war_spy(account_id, opponent_tag)
        report = format_spy_report(war_data)
        for chunk in chunk_message(report):
            await interaction.followup.send(chunk)

        if war_data:
            player_decks = war_data.get("playerDecks", [])
            available, _ = split_available_decks(war_data.get("opponentDecks", []))
            if player_decks and available:
                view = SpyDuelView(interaction.user.id, player_decks, available)
                await interaction.followup.send(
                    "🎮 **Track the duel** — after each match, log who played what "
                    "and I'll suggest your next pick.",
                    view=view,
                )

    @app_commands.command(name="info", description="Display information about the bot")
    async def info(self, interaction: Interaction):
        embed = make_embed(
            "Clash Royale Clan Management Bot 🗣️🗣️🔥🔥🔥",
            "Your ultimate tool for managing and tracking your Clash Royale clan's performance!",
        )

        embed.add_field(
            name="📊 War Commands",
            value="""
- `/currentwar [clan_tag]` - Get current war stats
- `/lastwar [clan_tag]` - Get last war stats
- `/nthwar [clan_tag] [n]` - Get stats from n wars ago (1-10)
            """,
            inline=False,
        )
        embed.add_field(
            name="👥 Player & Clan Commands",
            value="""
- `/members [clan_tag]` - View current clan members
- `/player [player_tag]` - View detailed player stats
- `/clan [clan_tag]` - List clan members and join dates
- `/viewlinks [clan_tag]` - List clan members with their linked Discord accounts
- `/rankings [tourny_tag]` - List tournament rankings
- `/stats [player_tag] [from_war] [to_war]` - Calculate player stats over war range
            """,
            inline=False,
        )
        embed.add_field(
            name="🔗 Account Linking",
            value="""
- `/link [@user]` - Open the link manager to set a main tag, add alts, edit DeckAI IDs, or remove accounts (managing another user requires privileges; non server specific)
- `/profile [@user]` - View linked accounts
- `/wipelinks [@user]` - Remove linked accounts
            """,
            inline=False,
        )
        embed.add_field(
            name="⚙️ Server Management",
            value="""
- `/nicklink [clan_tag] [nickname]` - Link clan tag to nickname, or leave nickname empty to delete it (server specific)
- `/viewnicks` - View clan nicknames in this server
- `/reminders [clan_tag]` - Set up or edit automated attack reminders sent on war days (server specific)
- `/editperms` - Edit privileged roles (server specific)
- `/viewperms` - View privileged roles
- `/editmemberroles` - Edit roles for clan roles (server specific)
- `/viewmemberroles` - View roles for clan roles (server specific)
            """,
            inline=False,
        )
        embed.add_field(
            name="📊 Advanced Features",
            value="""
- `/whotokick [clan_tag] [n] [exclude_leadership]` - Get recommendations for kicking members (n is by default 5 but can be from 1 to 24)
- `/whotopromote [clan_tag] [n] [exclude_leadership]` - Get recommendations for promoting members (n is by default 5 but can be from 1 to 24)
- `/spy_ai [opponent_player_tag] [@someone_else]` - Scout an opponent's available war-duel decks via DeckAI, see your win rate against each, and get live pick suggestions as the duel plays out (requires a linked DeckAI ID)
            """,
            inline=False,
        )
        embed.add_field(
            name="🔄 Sorting & Customization",
            value="""
- Use dropdown menus to sort and order results in war and member commands
- Sort by: Fame, Name, Decks Used, Tag, Rank (options vary by command)
- Order data: Customize the display order of all data
            """,
            inline=False,
        )
        embed.add_field(
            name="💡 Pro Tips",
            value=f"""
- Hashtags (#) are optional in clan or player tags
- Tags are not case-sensitive
- Use clan nicknames instead of tags for convenience
- Player commands also accept a Discord @mention in place of a tag (uses their linked account)
- Download CSV files for detailed data analysis
- {FAME_EMOJI} Fame earned | {MULTIDECK_EMOJI} Decks used
- {FORMER_MEMBER_EMOJI} Former members | {NEW_MEMBER_EMOJI} New members (joined after last war ended)
- Privileged commands require proper server permissions (All command can be used by anyone before permissions are set up with `/editperms`. Once privileges are set up, only those roles can use them)
            """,
            inline=False,
        )

        developer = await interaction.client.fetch_user(DEVELOPER_ID)
        embed.set_footer(
            text="For support or suggestions, contact @adiar.",
            icon_url=developer.display_avatar.url,
        )
        view = View()
        view.add_item(discord.ui.Button(
            label="Contact Developer",
            style=ButtonStyle.link,
            url=f"https://discord.com/users/{DEVELOPER_ID}",
        ))
        await interaction.response.send_message(embed=embed, view=view)
