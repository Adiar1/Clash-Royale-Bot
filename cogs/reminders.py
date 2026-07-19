"""Automated war-attack reminders.

/reminders walks a privileged user through an ephemeral setup wizard
(channel -> timezone -> times) or, when the clan is already configured,
opens an edit menu. A minutely background loop delivers reminders on the
war days that start Thursday-Sunday.

Each war day runs 10:00 UTC to 10:00 UTC, so the selectable times are the
hours of that window (11:00 through 09:00 UTC, skipping the reset hour)
and are stored in UTC; the configured IANA timezone is only used to show
those hours as local wall-clock times in the menus.
"""

import logging
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import ButtonStyle, ChannelType, Interaction, SelectOption, app_commands
from discord.ext import commands, tasks
from discord.ui import Button, ChannelSelect, Select, View

from cogs.checks import is_privileged
from cogs.misc import chunk_message
from cogs.resolvers import resolve_clan_tag
from db.repository import Reminder
from services.clash_royale import ClanMember, race_participants
from ui.embeds import make_embed

logger = logging.getLogger(__name__)

WAR_DAYS = {3, 4, 5, 6}  # datetime.weekday(): war days start Thursday through Sunday

WAR_DAY_RESET_UTC_HOUR = 10  # each war day runs 10:00 UTC to 10:00 UTC

MAX_DECKS_PER_DAY = 200  # 50 slots x 4 decks each
MAX_SLOTS_PER_DAY = 50   # distinct players who may battle on one war day

TIMEZONES = [
    ("US Eastern", "America/New_York"),
    ("US Central", "America/Chicago"),
    ("US Mountain", "America/Denver"),
    ("US Arizona", "America/Phoenix"),
    ("US Pacific", "America/Los_Angeles"),
    ("US Alaska", "America/Anchorage"),
    ("US Hawaii", "Pacific/Honolulu"),
    ("Brazil - São Paulo", "America/Sao_Paulo"),
    ("UK & Ireland", "Europe/London"),
    ("Central Europe", "Europe/Berlin"),
    ("Eastern Europe", "Europe/Bucharest"),
    ("Turkey & Middle East", "Europe/Istanbul"),
    ("India", "Asia/Kolkata"),
    ("China & Singapore", "Asia/Shanghai"),
    ("Japan & Korea", "Asia/Tokyo"),
    ("Australia East", "Australia/Sydney"),
    ("Australia West", "Australia/Perth"),
    ("UTC", "UTC"),
]


def timezone_label(zone: str) -> str:
    return next((label for label, z in TIMEZONES if z == zone), zone)


def war_day_utc_hours() -> list[int]:
    """UTC hours of one war day in order (11:00 ... 09:00), skipping the reset hour."""
    return [(WAR_DAY_RESET_UTC_HOUR + offset) % 24 for offset in range(1, 24)]


def war_day_sort_key(utc_time: str) -> int:
    """Orders "HH:MM" UTC times by position within the war day."""
    return (int(utc_time[:2]) - WAR_DAY_RESET_UTC_HOUR) % 24


def local_label(utc_time: str, zone: str) -> str:
    """Today's local wall-clock time for a stored "HH:MM" UTC time."""
    hour, minute = map(int, utc_time.split(":"))
    now = datetime.now(UTC).replace(hour=hour, minute=minute)
    return now.astimezone(ZoneInfo(zone)).strftime("%H:%M")


def war_day_totals(participants: dict[str, dict]) -> tuple[int, int]:
    """(decks remaining, slots remaining) for today across the whole clan.

    Each war day at most 50 participants may battle (anyone who used at
    least one deck consumes a slot) and each of them gets 4 decks.
    """
    used = [int(p.get("decksUsedToday", 0)) for p in participants.values()]
    decks_remaining = max(0, MAX_DECKS_PER_DAY - sum(used))
    slots_remaining = max(0, MAX_SLOTS_PER_DAY - sum(1 for decks in used if decks > 0))
    return decks_remaining, slots_remaining


def format_reminder(clan_name: str, decks_remaining: int, slots_remaining: int,
                    by_attacks_left: dict[int, list[str]]) -> str:
    lines = [
        "## __Reminder!__",
        "",
        "Please finish your hits ASAP",
        "",
        f"**{clan_name}**",
        f"Decks Remaining: **{decks_remaining}**",
        f"Slots Remaining: **{slots_remaining}**",
    ]
    for attacks_left in (4, 3, 2, 1):
        entries = by_attacks_left.get(attacks_left, [])
        if not entries:
            continue
        lines += ["", f"**__{attacks_left} Attack{'s' if attacks_left > 1 else ''}__**"]
        lines += [f"- {entry}" for entry in entries]
    return "\n".join(lines)


# ---- /reminders configuration flow ----

class ReminderChannelSelect(ChannelSelect):
    def __init__(self):
        super().__init__(channel_types=[ChannelType.text], placeholder="Select the reminder channel")

    async def callback(self, interaction: Interaction):
        await self.view.channel_chosen(interaction, self.values[0].id)


class ReminderTimezoneSelect(Select):
    def __init__(self):
        now_utc = datetime.now(UTC)
        options = [
            SelectOption(label=label, value=zone,
                         description=f"Current time there: {now_utc.astimezone(ZoneInfo(zone)).strftime('%H:%M')}")
            for label, zone in TIMEZONES
        ]
        super().__init__(placeholder="Select a timezone", options=options)

    async def callback(self, interaction: Interaction):
        await self.view.timezone_chosen(interaction, self.values[0])


class ReminderTimeSelect(Select):
    """Hours of the war day (11:00 through 09:00 UTC), labeled in the chosen timezone."""

    def __init__(self, zone: str):
        options = [
            SelectOption(label=local_label(f"{hour:02d}:00", zone), value=f"{hour:02d}:00",
                         description=f"{hour:02d}:00 UTC")
            for hour in war_day_utc_hours()
        ]
        super().__init__(placeholder="Select one or more reminder times",
                         options=options, min_values=1, max_values=len(options))

    async def callback(self, interaction: Interaction):
        await self.view.times_chosen(interaction, sorted(self.values, key=war_day_sort_key))


class ReminderFlowView(View):
    """Single ephemeral message that walks through setup or editing.

    The view swaps its own components between steps: unconfigured clans go
    through channel -> timezone -> times, configured clans start at the
    edit menu (send now / edit times / change channel / delete).
    """

    def __init__(self, cog: "RemindersCog", guild_id: int, clan_tag: str, clan_name: str,
                 reminder: Reminder | None):
        super().__init__(timeout=300)
        self.cog = cog
        self.bot = cog.bot
        self.guild_id = guild_id
        self.clan_tag = clan_tag
        self.clan_name = clan_name
        self.reminder = reminder
        self.channel_id = reminder.channel_id if reminder else None
        self.timezone = reminder.timezone if reminder else None

    def start(self) -> discord.Embed:
        return self._menu_step() if self.reminder else self._channel_step()

    # ---- step builders (set this view's items, return the embed) ----

    def _swap_items(self, *items) -> None:
        self.clear_items()
        for item in items:
            self.add_item(item)

    def _button(self, label: str, style: ButtonStyle, callback) -> Button:
        button = Button(label=label, style=style)
        button.callback = callback
        return button

    def _channel_step(self) -> discord.Embed:
        self._swap_items(ReminderChannelSelect())
        return make_embed(
            f"Reminders: {self.clan_name}",
            "Which channel should the automated reminders be sent to?",
        )

    def _timezone_step(self) -> discord.Embed:
        self._swap_items(ReminderTimezoneSelect())
        return make_embed(
            f"Reminders: {self.clan_name}",
            "Which timezone should the reminder times be shown in?",
        )

    def _times_step(self) -> discord.Embed:
        self._swap_items(ReminderTimeSelect(self.timezone))
        return make_embed(
            f"Reminders: {self.clan_name}",
            f"At what times ({timezone_label(self.timezone)}) should the reminders go out?\n"
            "Each war day runs 10:00 UTC to 10:00 UTC, so the options cover that window in "
            "order, from the first hour of the war day to its last.",
        )

    def _menu_step(self, note: str | None = None) -> discord.Embed:
        self._swap_items(
            self._button("Send Reminder Now", ButtonStyle.success, self._send_now_pressed),
            self._button("Edit Times", ButtonStyle.primary, self._edit_times_pressed),
            self._button("Change Channel", ButtonStyle.secondary, self._change_channel_pressed),
            self._button("Delete Reminders", ButtonStyle.danger, self._delete_pressed),
        )
        embed = make_embed(
            f"Reminders: {self.clan_name} (#{self.clan_tag})",
            note or "Reminders are sent at the times below on war days (Thursday-Sunday).",
        )
        embed.add_field(name="Channel", value=f"<#{self.reminder.channel_id}>", inline=False)
        ordered = sorted(self.reminder.times, key=war_day_sort_key)
        embed.add_field(
            name="Times",
            value=f"{', '.join(local_label(t, self.reminder.timezone) for t in ordered)} "
                  f"({timezone_label(self.reminder.timezone)})",
            inline=False,
        )
        return embed

    # ---- step transitions ----

    async def channel_chosen(self, interaction: Interaction, channel_id: int):
        channel = interaction.guild.get_channel(channel_id)
        permissions = channel.permissions_for(interaction.guild.me) if channel else None
        missing = [
            label for label, allowed in
            (("View Channel", permissions and permissions.view_channel),
             ("Send Messages", permissions and permissions.send_messages))
            if not allowed
        ]
        if missing:
            self._swap_items(ReminderChannelSelect())
            embed = make_embed(
                f"Reminders: {self.clan_name}",
                f"⚠️ I'm missing **{' and '.join(missing)}** in <#{channel_id}>.\n"
                "Slash commands work even in channels I can't access, but reminders are regular "
                "messages, so I need those permissions there. Add me (or my role) to that "
                "channel's permissions, or pick a different channel.",
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        self.channel_id = channel_id
        if self.reminder is None:
            await interaction.response.edit_message(embed=self._timezone_step(), view=self)
            return
        await self.bot.repo.set_reminder_channel(self.clan_tag, self.guild_id, channel_id)
        await self._refresh_reminder()
        await interaction.response.edit_message(
            embed=self._menu_step(f"✅ Reminders will now be sent to <#{channel_id}>."), view=self
        )

    async def timezone_chosen(self, interaction: Interaction, zone: str):
        self.timezone = zone
        await interaction.response.edit_message(embed=self._times_step(), view=self)

    async def times_chosen(self, interaction: Interaction, times: list[str]):
        first_setup = self.reminder is None
        await self.bot.repo.set_reminder(self.clan_tag, self.guild_id, self.channel_id, self.timezone, times)
        await self._refresh_reminder()
        note = "✅ Reminders are set up! Run the command again anytime to edit them." if first_setup \
            else "✅ Reminder times updated."
        await interaction.response.edit_message(embed=self._menu_step(note), view=self)

    async def _refresh_reminder(self):
        self.reminder = await self.bot.repo.reminder(self.clan_tag, self.guild_id)

    async def _send_now_pressed(self, interaction: Interaction):
        await interaction.response.defer()
        result = await self.cog.deliver_reminder(self.reminder)
        notes = {
            "sent": f"✅ Reminder sent to <#{self.reminder.channel_id}>.",
            "nothing_due": "ℹ️ Nothing to send right now. It's a training day or everyone "
                           "has finished their attacks.",
            "no_channel": "⚠️ The configured channel no longer exists. Pick a new one with Change Channel.",
            "forbidden": f"⚠️ I don't have permission to post in <#{self.reminder.channel_id}>. Slash "
                         "commands work without channel access, but reminders are regular messages. "
                         "I need **View Channel** and **Send Messages** there.",
        }
        await interaction.edit_original_response(embed=self._menu_step(notes[result]), view=self)

    async def _edit_times_pressed(self, interaction: Interaction):
        await interaction.response.edit_message(embed=self._timezone_step(), view=self)

    async def _change_channel_pressed(self, interaction: Interaction):
        await interaction.response.edit_message(embed=self._channel_step(), view=self)

    async def _delete_pressed(self, interaction: Interaction):
        self._swap_items(
            self._button("Yes, delete", ButtonStyle.danger, self._delete_confirmed),
            self._button("Cancel", ButtonStyle.secondary, self._delete_cancelled),
        )
        embed = make_embed("Delete Reminders", f"Turn off and delete all reminders for **{self.clan_name}**?")
        await interaction.response.edit_message(embed=embed, view=self)

    async def _delete_confirmed(self, interaction: Interaction):
        await self.bot.repo.delete_reminder(self.clan_tag, self.guild_id)
        self.stop()
        await interaction.response.edit_message(
            embed=make_embed("Reminders Deleted", f"Reminders for **{self.clan_name}** have been turned off."),
            view=None,
        )

    async def _delete_cancelled(self, interaction: Interaction):
        await interaction.response.edit_message(embed=self._menu_step(), view=self)


class RemindersCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_sent: dict[tuple[str, int], str] = {}  # (clan_tag, guild_id) -> local "YYYY-MM-DD HH:MM"

    async def cog_load(self):
        self.deliver_due_reminders.start()

    async def cog_unload(self):
        self.deliver_due_reminders.cancel()

    @app_commands.command(name="reminders",
                          description="Set up or edit automated attack reminders sent on war days")
    @app_commands.describe(clan_tag="The tag of the clan (or a server nickname)")
    @is_privileged()
    async def reminders(self, interaction: Interaction, clan_tag: str):
        await interaction.response.defer(ephemeral=True)
        tag = await resolve_clan_tag(interaction, clan_tag)
        clan = await self.bot.cr.clan(tag)
        existing = await self.bot.repo.reminder(tag, interaction.guild.id)
        view = ReminderFlowView(self, interaction.guild.id, tag, clan["name"], existing)
        await interaction.followup.send(embed=view.start(), view=view, ephemeral=True)

    # ---- scheduled delivery ----

    @tasks.loop(seconds=60)
    async def deliver_due_reminders(self):
        now_utc = datetime.now(UTC)
        for reminder in await self.bot.repo.all_reminders():
            try:
                await self._deliver_if_due(reminder, now_utc)
            except Exception:
                logger.exception("Failed to deliver reminder for clan %s in guild %s",
                                 reminder.clan_tag, reminder.guild_id)

    @deliver_due_reminders.before_loop
    async def _wait_until_ready(self):
        await self.bot.wait_until_ready()

    async def _deliver_if_due(self, reminder: Reminder, now_utc: datetime):
        if now_utc.strftime("%H:%M") not in reminder.times:
            return
        # Hours before the 10:00 UTC reset belong to the war day that started the
        # previous day (e.g. Monday 05:00 UTC is still Sunday's war day).
        war_day_start = now_utc if now_utc.hour >= WAR_DAY_RESET_UTC_HOUR else now_utc - timedelta(days=1)
        if war_day_start.weekday() not in WAR_DAYS:
            return

        # The loop can tick twice within one minute (e.g. after a reconnect); send once.
        minute = now_utc.strftime("%Y-%m-%d %H:%M")
        key = (reminder.clan_tag, reminder.guild_id)
        if self._last_sent.get(key) == minute:
            return
        self._last_sent[key] = minute

        result = await self.deliver_reminder(reminder)
        if result in ("no_channel", "forbidden"):
            logger.warning("Reminder for clan %s in guild %s not sent: %s",
                           reminder.clan_tag, reminder.guild_id, result)

    async def deliver_reminder(self, reminder: Reminder) -> str:
        """Build and send the reminder immediately.

        Returns "sent", or why nothing was sent: "nothing_due" (training day
        or everyone finished), "no_channel", or "forbidden".
        """
        channel = self.bot.get_channel(reminder.channel_id)
        if channel is None:
            return "no_channel"
        message = await self.build_reminder_message(reminder.clan_tag)
        if message is None:
            return "nothing_due"
        try:
            for chunk in chunk_message(message):
                await channel.send(chunk)
        except discord.Forbidden:
            return "forbidden"
        return "sent"

    # ---- message building ----

    async def build_reminder_message(self, clan_tag: str) -> str | None:
        """Full reminder text, or None when there is nothing to remind about
        (no race, still a training day, or everyone finished their attacks)."""
        race = await self.bot.cr.current_river_race(clan_tag)
        if race is None or race.get("periodType") == "training":
            return None

        clan = await self.bot.cr.clan(clan_tag)
        members = await self.bot.cr.clan_members(clan_tag)
        participants = race_participants(race)
        decks_remaining, slots_remaining = war_day_totals(participants)

        by_attacks_left: dict[int, list[str]] = {}
        for member in members:
            used = int(participants.get(member.tag, {}).get("decksUsedToday", 0))
            attacks_left = 4 - used
            if attacks_left <= 0:
                continue
            by_attacks_left.setdefault(attacks_left, []).append(await self._format_member(member))
        if not by_attacks_left:
            return None

        return format_reminder(clan["name"], decks_remaining, slots_remaining, by_attacks_left)

    async def _format_member(self, member: ClanMember) -> str:
        """Linked members get pinged; the account name is appended when the
        Discord user has more than one linked account."""
        discord_id = await self.bot.repo.discord_id_for_tag(member.tag)
        if discord_id is None:
            return member.name
        if len(await self.bot.repo.player_tags(discord_id)) > 1:
            return f"<@{discord_id}> ({member.name})"
        return f"<@{discord_id}>"
