"""Clan-family recruiting: keep each clan's "recruits needed" number fresh with
as little leader effort as possible.

The number is auto-derived from the Clash Royale API (open slots = 50 - current
members) and kept current by a background poll. When the poll notices a clan lost
members, it posts a prompt in that clan's recruiting thread and @-mentions the
assigned manager(s), who refine the number with one tap:

    [Use suggested] [+1] [-1] [Set exact...] [We're full]

"Use suggested" keeps the clan auto-tracked; the other buttons pin a manual value
that the poll won't overwrite (it only re-prompts on further membership drops).

Setup is three privileged commands: /setrecruitchannel (once, guild-wide),
/setclanmanager (per clan), and optionally /editneeds to pin a number by hand.
/viewneeds shows the whole family's needs at a glance.
"""

import asyncio
import logging

import discord
from discord import ButtonStyle, Interaction, app_commands
from discord.ext import commands, tasks
from discord.ui import Button, Modal, TextInput, View

from cogs.checks import is_privileged
from cogs.resolvers import resolve_clan_tag
from ui.embeds import EMBED_COLOR, ERROR_COLOR, MAX_DESCRIPTION, SUCCESS_COLOR, make_embed

logger = logging.getLogger(__name__)

CLAN_MAX_MEMBERS = 50
POLL_INTERVAL_SECONDS = 300  # 5 minutes


def _recruits(n: int) -> str:
    return "recruit" if n == 1 else "recruits"


def _paginate(lines: list[str]) -> list[str]:
    """Pack lines into as few embed-description-sized pages as possible."""
    pages: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > MAX_DESCRIPTION:
            pages.append(current)
            current = line
        else:
            current = candidate
    if current:
        pages.append(current)
    return pages


def build_needs_embed(name: str, clan_tag: str, count: int | None, needed: int,
                      manual: bool, open_slots: int | None, note: str | None = None) -> discord.Embed:
    parts: list[str] = []
    if note:
        parts += [note, ""]
    parts.append(f"**Recruits needed: {needed}**")
    if count is not None:
        parts.append(f"Members: {count}/{CLAN_MAX_MEMBERS} ({open_slots} open)")
    parts.append(f"Source: {'📌 pinned by a leader' if manual else '🔄 auto-tracked (open slots)'}")
    parts += ["", "Tap a button to adjust. **Use suggested** keeps it auto-tracked."]
    return make_embed(f"Recruiting — {name} (#{clan_tag})", "\n".join(parts), color=EMBED_COLOR)


async def render_needs_message(interaction: Interaction, guild_id: int, clan_tag: str,
                               needed: int | None, manual: bool, view: View) -> None:
    """Set the need, rebuild the embed from live clan data, and edit the prompt message.

    ``needed=None`` means auto-track: use the current open-slot count.
    """
    try:
        clan = await interaction.client.cr.clan(clan_tag)
        name = clan.get("name") or f"#{clan_tag}"
        count = clan.get("members")
    except Exception:
        name, count = f"#{clan_tag}", None

    open_slots = max(0, CLAN_MAX_MEMBERS - count) if count is not None else None
    if needed is None:
        needed = open_slots if open_slots is not None else 0
    needed = max(0, min(int(needed), CLAN_MAX_MEMBERS))

    await interaction.client.repo.set_clan_needs(clan_tag, guild_id, needed, manual=manual)

    source = "📌 pinned" if manual else "🔄 auto-tracked"
    note = f"Set to **{needed}** by {interaction.user.mention} · {source}."
    embed = build_needs_embed(name, clan_tag, count, needed, manual, open_slots, note)
    await interaction.response.edit_message(embed=embed, view=view)


class SetNeedModal(Modal, title="Set recruits needed"):
    number = TextInput(label="How many recruits?", placeholder="0-50", max_length=2, required=True)

    async def on_submit(self, interaction: Interaction):
        resolved = await interaction.client.repo.clan_by_thread(interaction.channel.id)
        if resolved is None:
            await interaction.response.send_message(
                "This thread is no longer linked to a clan.", ephemeral=True)
            return
        raw = self.number.value.strip()
        if not raw.isdigit() or not (0 <= int(raw) <= CLAN_MAX_MEMBERS):
            await interaction.response.send_message(
                f"Please enter a whole number from 0 to {CLAN_MAX_MEMBERS}.", ephemeral=True)
            return
        guild_id, clan_tag = resolved
        await render_needs_message(interaction, guild_id, clan_tag, int(raw), manual=True,
                                   view=NeedsPromptView())


class NeedsPromptView(View):
    """Persistent button row on a recruiting prompt. One registered instance handles
    every prompt message; the target clan is resolved from the thread it lives in."""

    def __init__(self):
        super().__init__(timeout=None)

    async def _resolve(self, interaction: Interaction) -> tuple[int, str] | None:
        resolved = await interaction.client.repo.clan_by_thread(interaction.channel.id)
        if resolved is None:
            await interaction.response.send_message(
                "This thread is no longer linked to a clan.", ephemeral=True)
        return resolved

    @discord.ui.button(label="Use suggested", style=ButtonStyle.success, custom_id="recruitneeds:auto")
    async def use_suggested(self, interaction: Interaction, button: Button):
        resolved = await self._resolve(interaction)
        if resolved is None:
            return
        guild_id, clan_tag = resolved
        await render_needs_message(interaction, guild_id, clan_tag, None, manual=False, view=self)

    @discord.ui.button(label="+1", style=ButtonStyle.secondary, custom_id="recruitneeds:inc")
    async def increment(self, interaction: Interaction, button: Button):
        resolved = await self._resolve(interaction)
        if resolved is None:
            return
        guild_id, clan_tag = resolved
        current = await interaction.client.repo.clan_needs(clan_tag, guild_id) or 0
        await render_needs_message(interaction, guild_id, clan_tag, current + 1, manual=True, view=self)

    @discord.ui.button(label="−1", style=ButtonStyle.secondary, custom_id="recruitneeds:dec")
    async def decrement(self, interaction: Interaction, button: Button):
        resolved = await self._resolve(interaction)
        if resolved is None:
            return
        guild_id, clan_tag = resolved
        current = await interaction.client.repo.clan_needs(clan_tag, guild_id) or 0
        await render_needs_message(interaction, guild_id, clan_tag, current - 1, manual=True, view=self)

    @discord.ui.button(label="Set exact…", style=ButtonStyle.primary, custom_id="recruitneeds:set")
    async def set_exact(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(SetNeedModal())

    @discord.ui.button(label="We're full", style=ButtonStyle.danger, custom_id="recruitneeds:full")
    async def full(self, interaction: Interaction, button: Button):
        resolved = await self._resolve(interaction)
        if resolved is None:
            return
        guild_id, clan_tag = resolved
        await render_needs_message(interaction, guild_id, clan_tag, 0, manual=True, view=self)


class RecruitCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(NeedsPromptView())  # keep buttons working across restarts
        self.poll_clans.start()

    async def cog_unload(self):
        self.poll_clans.cancel()

    # ---- /setrecruitchannel ----

    @app_commands.command(
        name="setrecruitchannel",
        description="Set the channel where per-clan recruiting threads are created",
    )
    @app_commands.describe(channel="The text channel to host recruiting threads")
    @is_privileged()
    async def setrecruitchannel(self, interaction: Interaction, channel: discord.TextChannel):
        perms = channel.permissions_for(interaction.guild.me)
        missing = [
            label for label, allowed in (
                ("View Channel", perms.view_channel),
                ("Send Messages", perms.send_messages),
                ("Create Public Threads", perms.create_public_threads),
                ("Send Messages in Threads", perms.send_messages_in_threads),
            ) if not allowed
        ]
        if missing:
            await interaction.response.send_message(
                embed=make_embed(
                    "Missing Permissions",
                    f"I need **{', '.join(missing)}** in {channel.mention} to post recruiting prompts there.",
                    color=ERROR_COLOR,
                ),
                ephemeral=True,
            )
            return
        await self.bot.repo.set_recruit_channel(interaction.guild.id, channel.id)
        await interaction.response.send_message(embed=make_embed(
            "Recruiting Channel Set",
            f"Recruiting threads will be created in {channel.mention}. Assign clan managers with "
            "`/setclanmanager` so I know who to prompt.",
            color=SUCCESS_COLOR,
        ))

    # ---- /setclanmanager ----

    @app_commands.command(
        name="setclanmanager",
        description="Assign or unassign someone to manage a clan's recruiting (toggles)",
    )
    @app_commands.describe(
        tag="The clan tag or its server nickname",
        user="The member to assign (or unassign, if already assigned)",
    )
    @is_privileged()
    async def setclanmanager(self, interaction: Interaction, tag: str, user: discord.Member):
        await interaction.response.defer()
        clan_tag = await resolve_clan_tag(interaction, tag)
        clan = await self.bot.cr.clan(clan_tag)
        name = clan.get("name") or f"#{clan_tag}"
        guild_id = interaction.guild.id

        existing = await self.bot.repo.clan_managers(guild_id, clan_tag)
        if user.id in existing:
            await self.bot.repo.remove_clan_manager(guild_id, clan_tag, user.id)
            verb = "is no longer managing"
        else:
            await self.bot.repo.add_clan_manager(guild_id, clan_tag, user.id)
            verb = "is now managing"

        managers = await self.bot.repo.clan_managers(guild_id, clan_tag)
        mentions = ", ".join(f"<@{uid}>" for uid in managers) or "None"
        embed = make_embed(
            "Clan Managers Updated",
            f"{user.mention} {verb} recruiting for **{name}** (#{clan_tag}).",
            color=SUCCESS_COLOR,
        )
        embed.add_field(name="Current managers", value=mentions, inline=False)
        if managers and await self.bot.repo.recruit_channel(guild_id) is None:
            embed.add_field(
                name="⚠️ No recruiting channel set",
                value="Run `/setrecruitchannel` so I can post recruiting prompts.",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    # ---- /viewclanmanagers ----

    @app_commands.command(name="viewclanmanagers", description="View who manages recruiting for each clan")
    @is_privileged()
    async def viewclanmanagers(self, interaction: Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild.id
        tags = await self.bot.repo.managed_clans(guild_id)
        if not tags:
            await interaction.followup.send(embed=make_embed(
                "No Clan Managers",
                "No clans have managers yet. Use `/setclanmanager` to assign someone.",
            ))
            return

        async def _name(clan_tag: str) -> str | None:
            try:
                return (await self.bot.cr.clan(clan_tag)).get("name")
            except Exception:
                return None

        names = await asyncio.gather(*(_name(tag) for tag in tags))
        rows = [
            (tag, name, await self.bot.repo.clan_managers(guild_id, tag))
            for tag, name in zip(tags, names, strict=True)
        ]
        rows.sort(key=lambda r: (r[1] or r[0]).lower())

        channel_id = await self.bot.repo.recruit_channel(guild_id)
        header = f"Recruiting prompts post in <#{channel_id}>." if channel_id \
            else "⚠️ No recruiting channel set — run `/setrecruitchannel`."
        lines = [header, ""]
        for tag, name, managers in rows:
            label = f"{name} (#{tag})" if name else f"#{tag}"
            mentions = ", ".join(f"<@{uid}>" for uid in managers) or "None"
            lines.append(f"**{label}** — {mentions}")

        for index, page in enumerate(_paginate(lines)):
            title = "Clan Managers" if index == 0 else "Clan Managers (continued)"
            await interaction.followup.send(embed=make_embed(title, page))

    # ---- /editneeds ----

    @app_commands.command(
        name="editneeds",
        description="Pin how many recruits a clan needs in this server (set 0 to clear)",
    )
    @app_commands.describe(
        tag="The clan tag or its server nickname",
        number="How many recruits the clan needs (0 clears it from the needs list)",
    )
    @is_privileged()
    async def editneeds(self, interaction: Interaction, tag: str, number: app_commands.Range[int, 0, 50]):
        await interaction.response.defer()
        clan_tag = await resolve_clan_tag(interaction, tag)
        clan = await self.bot.cr.clan(clan_tag)
        name = clan.get("name") or f"#{clan_tag}"

        await self.bot.repo.set_clan_needs(clan_tag, interaction.guild.id, number, manual=True)
        if number == 0:
            desc = f"**{name}** (#{clan_tag}) is marked as **not** currently needing recruits."
        else:
            desc = f"**{name}** (#{clan_tag}) now needs **{number}** {_recruits(number)} (pinned)."
        await interaction.followup.send(embed=make_embed("Recruitment Need Updated", desc, color=SUCCESS_COLOR))

    # ---- /viewneeds ----

    @app_commands.command(name="viewneeds", description="View which clans need recruits and how many")
    @is_privileged()
    async def viewneeds(self, interaction: Interaction):
        await interaction.response.defer()
        needs = await self.bot.repo.clan_needs_for_guild(interaction.guild.id)

        if not needs:
            await interaction.followup.send(embed=make_embed(
                "No Recruitment Needs",
                "No clans in this server are marked as needing recruits. Use `/editneeds` to pin one, "
                "or `/setclanmanager` to have me track them automatically.",
            ))
            return

        async def _clan(clan_tag: str) -> dict | None:
            try:
                return await self.bot.cr.clan(clan_tag)
            except Exception:
                return None

        clans = await asyncio.gather(*(_clan(tag) for tag, _ in needs))
        rows = [
            (clan_tag, needed, (clan or {}).get("name"), (clan or {}).get("members"))
            for (clan_tag, needed), clan in zip(needs, clans, strict=True)
        ]
        # Most-needy clans first, then alphabetically by name (falling back to tag).
        rows.sort(key=lambda r: (-r[1], (r[2] or r[0]).lower()))

        total = sum(needed for _, needed, _, _ in rows)
        lines = [f"Clans needing recruits in this server (**{total}** total):"]
        for clan_tag, needed, name, count in rows:
            label = name or f"#{clan_tag}"
            tag_suffix = f" (#{clan_tag})" if name else ""
            count_suffix = f" · {count}/{CLAN_MAX_MEMBERS} in clan" if count is not None else ""
            lines.append(f"**{needed}** needed — {label}{tag_suffix}{count_suffix}")

        for index, page in enumerate(_paginate(lines)):
            title = "Clan Recruitment Needs" if index == 0 else "Clan Recruitment Needs (continued)"
            await interaction.followup.send(embed=make_embed(title, page))

    # ---- background poll: keep numbers fresh, prompt on member drops ----

    @tasks.loop(seconds=POLL_INTERVAL_SECONDS)
    async def poll_clans(self):
        for guild_id, clan_tag in await self.bot.repo.all_managed_clans():
            try:
                await self._process_clan(guild_id, clan_tag)
            except Exception:
                logger.exception("Failed to process recruiting for clan %s in guild %s", clan_tag, guild_id)

    @poll_clans.before_loop
    async def _wait_until_ready(self):
        await self.bot.wait_until_ready()

    async def _process_clan(self, guild_id: int, clan_tag: str) -> None:
        managers = await self.bot.repo.clan_managers(guild_id, clan_tag)
        if not managers:
            return
        try:
            clan = await self.bot.cr.clan(clan_tag)
        except Exception:
            return
        count = clan.get("members")
        if count is None:
            return
        clan_name = clan.get("name") or f"#{clan_tag}"
        open_slots = max(0, CLAN_MAX_MEMBERS - count)

        state = await self.bot.repo.clan_need(clan_tag, guild_id)
        prev_count = state.last_count if state else None
        manual = state.manual if state else False

        # Keep the auto baseline honest (a no-op for manually pinned clans).
        if not manual and (state is None or state.needed != open_slots):
            await self.bot.repo.set_clan_needs(clan_tag, guild_id, open_slots, manual=False)

        # First observation: record the count, never alert (there's no prior state to diff).
        if prev_count is None:
            await self.bot.repo.set_clan_last_count(clan_tag, guild_id, count)
            return

        if count == prev_count:
            return

        await self.bot.repo.set_clan_last_count(clan_tag, guild_id, count)

        # Members left → prompt the managers to confirm/adjust. Joins self-resolve silently.
        if count < prev_count:
            await self._prompt_managers(guild_id, clan_tag, clan_name, count, open_slots,
                                        managers, prev_count - count, manual, state)

    async def _prompt_managers(self, guild_id: int, clan_tag: str, clan_name: str, count: int,
                               open_slots: int, managers: list[int], left: int,
                               manual: bool, state) -> None:
        channel_id = await self.bot.repo.recruit_channel(guild_id)
        guild = self.bot.get_guild(guild_id)
        if channel_id is None or guild is None:
            return
        thread = await self._ensure_thread(guild, clan_tag, clan_name, channel_id,
                                           state.thread_id if state else None)
        if thread is None:
            return

        current_need = await self.bot.repo.clan_needs(clan_tag, guild_id) or 0
        mentions = " ".join(f"<@{uid}>" for uid in managers)
        note = f"👋 {left} member{'s' if left != 1 else ''} left **{clan_name}** — is the number below right?"
        embed = build_needs_embed(clan_name, clan_tag, count, current_need, manual, open_slots, note)
        try:
            await thread.send(content=mentions, embed=embed, view=NeedsPromptView())
        except discord.Forbidden:
            logger.warning("Missing permission to post recruiting prompt in thread %s (clan %s, guild %s)",
                           thread.id, clan_tag, guild_id)

    async def _ensure_thread(self, guild: discord.Guild, clan_tag: str, clan_name: str,
                             channel_id: int, existing_thread_id: int | None):
        """Return the clan's recruiting thread, reusing or (re)creating it as needed."""
        if existing_thread_id:
            thread = guild.get_thread(existing_thread_id)
            if thread is None:
                try:
                    thread = await self.bot.fetch_channel(existing_thread_id)  # may be archived
                except (discord.NotFound, discord.Forbidden):
                    thread = None
            if thread is not None:
                return thread

        parent = guild.get_channel(channel_id)
        if parent is None:
            return None
        try:
            thread = await parent.create_thread(
                name=f"Recruiting — {clan_name}"[:100],
                type=discord.ChannelType.public_thread,
            )
        except discord.Forbidden:
            logger.warning("Missing permission to create recruiting thread in channel %s (guild %s)",
                           channel_id, guild.id)
            return None
        await self.bot.repo.set_clan_thread(clan_tag, guild.id, thread.id)
        return thread
