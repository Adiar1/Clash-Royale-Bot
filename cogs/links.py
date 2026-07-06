import asyncio
import logging

import discord
from discord import ButtonStyle, Interaction, SelectOption, User, app_commands
from discord.ext import commands
from discord.ui import Button, Modal, Select, TextInput, View

from cogs.checks import is_privileged, user_is_privileged
from db.repository import MAX_LINKED_TAGS
from errors import BotError, ClanNotFound
from services.clash_royale import normalize_tag
from ui.embeds import EMBED_COLOR, make_embed
from ui.emojis import TROPHYROAD_EMOJI
from ui.views import ConfirmView

logger = logging.getLogger(__name__)


async def _send_interaction_error(interaction: Interaction, error: Exception) -> None:
    """Mirror bot.on_app_command_error for component/modal interactions,
    which don't go through the command tree's error handler."""
    if isinstance(error, BotError):
        message = error.user_message
    else:
        logger.error("Unhandled error in link manager", exc_info=error)
        message = "An unexpected error occurred while processing your request."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        logger.warning("Could not deliver error message for interaction %s", interaction.id)


class _EphemeralView(View):
    """Short-lived view for follow-up pickers spawned by the link manager."""

    async def on_error(self, interaction: Interaction, error: Exception, item) -> None:
        await _send_interaction_error(interaction, error)


class LinkPanel(View):
    """Interactive manager for the accounts linked to a Discord user.

    One message shows the current links (tags, names, DeckAI IDs) with
    buttons to set the main tag, add alts, edit DeckAI IDs, and remove
    accounts. ``target`` is whose links are edited; only the invoker may
    use the components.
    """

    def __init__(self, invoker_id: int, target: User):
        super().__init__(timeout=600)
        self.invoker_id = invoker_id
        self.target = target
        self.message: discord.Message | None = None
        self.tags: list[str] = []
        self.names: dict[str, str] = {}

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.invoker_id

    async def on_error(self, interaction: Interaction, error: Exception, item) -> None:
        await _send_interaction_error(interaction, error)

    def possessive(self) -> str:
        return f"{self.target.mention}'s account" if self.target.id != self.invoker_id else "your account"

    async def build_embed(self, bot) -> discord.Embed:
        """Rebuild the panel embed from the database and sync button states."""
        self.tags = await bot.repo.player_tags(self.target.id)

        async def fetch(tag: str) -> dict | None:
            try:
                return await bot.cr.player(tag)
            except Exception:
                return None

        players = await asyncio.gather(*[fetch(tag) for tag in self.tags])
        deckai_ids = await asyncio.gather(*[bot.repo.deckai_id(tag) for tag in self.tags])
        self.names = {
            tag: (player or {}).get("name", "Unknown")
            for tag, player in zip(self.tags, players, strict=True)
        }

        embed = discord.Embed(title="🔗 Link Manager", color=EMBED_COLOR)
        embed.set_author(
            name=f"{self.target.display_name} ({self.target.id})",
            icon_url=self.target.avatar.url if self.target.avatar else self.target.default_avatar.url,
        )

        if not self.tags:
            embed.description = "No accounts linked yet. Use **Set Main Tag** below to link the first one."
        else:
            sections = ["__**Main Account**__"]
            rows = zip(self.tags, players, deckai_ids, strict=True)
            for index, (tag, player, deckai_id) in enumerate(rows, 1):
                if index == 2:
                    sections.append(f"__**Alt Accounts ({len(self.tags) - 1})**__")
                name = (player or {}).get("name", "Unknown")
                trophies = (player or {}).get("trophies", "?")
                deckai = f"`{deckai_id}`" if deckai_id else "*not set*"
                sections.append(
                    f"**{index}. [{name}](https://royaleapi.com/player/{tag})** `#{tag}`\n"
                    f"{TROPHYROAD_EMOJI} {trophies} · DeckAI ID: {deckai}"
                )
            embed.description = "\n\n".join(sections)
            if len(self.tags) > 1:
                embed.set_footer(text="Removing the main account promotes the first alt.")

        self.add_alt.disabled = not self.tags or len(self.tags) >= MAX_LINKED_TAGS
        self.set_deckai.disabled = not self.tags
        self.remove_tag.disabled = not self.tags
        return embed

    async def refresh(self, bot) -> None:
        embed = await self.build_embed(bot)
        if self.message is None:
            return
        try:
            await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            logger.warning("Could not refresh link manager message %s", self.message.id)

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Set Main Tag", style=ButtonStyle.primary)
    async def set_main(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(TagModal(self, alt=False))

    @discord.ui.button(label="Add Alt Tag", style=ButtonStyle.secondary)
    async def add_alt(self, interaction: Interaction, button: Button):
        await interaction.response.send_modal(TagModal(self, alt=True))

    @discord.ui.button(label="Set DeckAI ID", style=ButtonStyle.secondary)
    async def set_deckai(self, interaction: Interaction, button: Button):
        if len(self.tags) == 1:
            tag = self.tags[0]
            current = await interaction.client.repo.deckai_id(tag)
            await interaction.response.send_modal(DeckAIModal(self, tag, current))
            return
        view = _EphemeralView(timeout=300)
        view.add_item(AccountSelect(self, mode="deckai"))
        await interaction.response.send_message(
            "Select the account to edit the DeckAI ID for:", view=view, ephemeral=True
        )

    @discord.ui.button(label="Remove Tag", style=ButtonStyle.danger)
    async def remove_tag(self, interaction: Interaction, button: Button):
        view = _EphemeralView(timeout=300)
        view.add_item(AccountSelect(self, mode="remove"))
        await interaction.response.send_message(
            "Select the account(s) to remove:", view=view, ephemeral=True
        )


class AccountSelect(Select):
    """Account picker for the link manager: opens the DeckAI modal for one
    account (mode="deckai") or unlinks the chosen accounts (mode="remove")."""

    def __init__(self, panel: LinkPanel, mode: str):
        self.panel = panel
        self.mode = mode
        options = [
            SelectOption(
                label=f"{index}. {panel.names.get(tag, 'Unknown')}" + (" (main)" if index == 1 else ""),
                description=f"#{tag}",
                value=tag,
            )
            for index, tag in enumerate(panel.tags, 1)
        ]
        super().__init__(
            placeholder="Select accounts to remove..." if mode == "remove" else "Select an account...",
            min_values=1,
            max_values=len(options) if mode == "remove" else 1,
            options=options,
        )

    async def callback(self, interaction: Interaction):
        if self.mode == "deckai":
            tag = self.values[0]
            current = await interaction.client.repo.deckai_id(tag)
            await interaction.response.send_modal(DeckAIModal(self.panel, tag, current))
            return

        await interaction.response.defer()
        repo = interaction.client.repo
        await repo.unlink_player_tags(self.panel.target.id, self.values)
        for tag in self.values:
            await repo.delete_deckai_id(tag)
        await self.panel.refresh(interaction.client)
        removed = ", ".join(f"`#{tag}`" for tag in self.values)
        await interaction.edit_original_response(
            content=f"Removed {removed} from {self.panel.possessive()}.", view=None
        )


class TagModal(Modal):
    player_tag = TextInput(label="Player Tag", placeholder="#2PP8Q0J2Y", min_length=3, max_length=16)
    deckai_id = TextInput(label="DeckAI ID (optional)", required=False, max_length=64,
                          placeholder="Attach a DeckAI ID to this tag")

    def __init__(self, panel: LinkPanel, alt: bool):
        super().__init__(title="Add Alt Tag" if alt else "Set Main Tag", timeout=600)
        self.panel = panel
        self.alt = alt

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await _send_interaction_error(interaction, error)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        bot = interaction.client
        tag = normalize_tag(self.player_tag.value)
        player = await bot.cr.player(tag)  # raises PlayerNotFound -> on_error

        result = await bot.repo.link_player_tag(self.panel.target.id, tag, alt=self.alt)
        if result == "exists":
            await interaction.followup.send(
                f"`#{tag}` is already linked to {self.panel.possessive()}.", ephemeral=True
            )
            return
        if result == "no_main_tag":
            await interaction.followup.send("Set a main tag before adding alts.", ephemeral=True)
            return
        if result == "too_many_tags":
            await interaction.followup.send(
                f"You can't link more than {MAX_LINKED_TAGS} tags.", ephemeral=True
            )
            return

        deckai_note = ""
        deckai_value = self.deckai_id.value.strip()
        if deckai_value:
            await bot.repo.set_deckai_id(tag, deckai_value)
            deckai_note = f" with DeckAI ID `{deckai_value}`"

        await self.panel.refresh(bot)
        kind = "an alt account on" if self.alt else "the main account on"
        await interaction.followup.send(
            f"✅ **{player.get('name', 'Unknown')}** `#{tag}`{deckai_note} is now {kind} "
            f"{self.panel.possessive()}.",
            ephemeral=True,
        )


class DeckAIModal(Modal):
    deckai_id = TextInput(label="DeckAI ID", required=False, max_length=64,
                          placeholder="Leave empty to remove the current ID")

    def __init__(self, panel: LinkPanel, player_tag: str, current: str | None):
        super().__init__(title=f"DeckAI ID for #{player_tag}", timeout=600)
        self.panel = panel
        self.player_tag = player_tag
        self.deckai_id.default = current

    async def on_error(self, interaction: Interaction, error: Exception) -> None:
        await _send_interaction_error(interaction, error)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        repo = interaction.client.repo
        value = self.deckai_id.value.strip()
        if value:
            await repo.set_deckai_id(self.player_tag, value)
            message = f"✅ DeckAI ID for `#{self.player_tag}` set to `{value}`."
        else:
            await repo.delete_deckai_id(self.player_tag)
            message = f"✅ DeckAI ID removed from `#{self.player_tag}`."
        await self.panel.refresh(interaction.client)
        await interaction.followup.send(message, ephemeral=True)


class WipeTagSelect(Select):
    def __init__(self, user_id: int, current_tags: list[str]):
        options = [SelectOption(label=tag, value=tag) for tag in current_tags]
        super().__init__(placeholder="Select tags to remove...", min_values=1, max_values=len(options),
                         options=options)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        await interaction.client.repo.unlink_player_tags(self.user_id, self.values)
        await interaction.response.edit_message(
            content=f"Selected tags removed: {', '.join(self.values)}", view=None
        )


class LinksCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---- /link ----

    @app_commands.command(
        name="link",
        description="Open the link manager to edit linked player tags, alts, and DeckAI IDs",
    )
    @app_commands.describe(user="Manage another user's links instead of your own (requires privileges)")
    async def link(self, interaction: Interaction, user: User | None = None):
        target = user or interaction.user
        if target.id != interaction.user.id and not await user_is_privileged(interaction):
            raise BotError("You need a privileged role to manage another user's links.")

        await interaction.response.defer()
        panel = LinkPanel(interaction.user.id, target)
        embed = await panel.build_embed(self.bot)
        panel.message = await interaction.followup.send(embed=embed, view=panel)

    # ---- /profile ----

    @app_commands.command(name="profile",
                          description="View all player tags linked to your Discord account or someone else's")
    @app_commands.describe(someone_else="Mention another user to see their linked player tags")
    async def profile(self, interaction: Interaction, someone_else: User | None = None):
        await interaction.response.defer()
        user = someone_else or interaction.user
        player_tags = await self.bot.repo.player_tags(user.id)

        if not player_tags:
            await interaction.followup.send("No player tags linked.")
            return

        async def fetch(tag: str) -> dict | None:
            try:
                return await self.bot.cr.player(tag)
            except Exception:
                return None

        players = await asyncio.gather(*[fetch(tag) for tag in player_tags])
        if all(p is None for p in players):
            raise BotError("Failed to fetch player data. Please try again later.")

        embeds = []
        for start in range(0, len(player_tags), 4):
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_author(
                name=f"{user.display_name} ({user.id})",
                icon_url=user.avatar.url if user.avatar else user.default_avatar.url,
            )
            embed.add_field(name="Username", value=user.name, inline=False)

            accounts = ""
            chunk = list(zip(player_tags, players, strict=True))[start:start + 4]
            for index, (tag, player) in enumerate(chunk, start + 1):
                if player is None:
                    continue
                clan = player.get("clan", {})
                clan_tag = clan.get("tag", "").replace("#", "")
                role = _format_role(player.get("role") or "member")
                accounts += (
                    f"**{index}. [{player.get('name', 'Unknown')}](https://royaleapi.com/player/{tag})** #{tag}\n"
                    f"{TROPHYROAD_EMOJI} {player.get('trophies', 0)}\n"
                    f"{role} of [{clan.get('name', 'No Clan')}](https://royaleapi.com/clan/{clan_tag})\n\n"
                )
            if accounts:
                embed.add_field(name=f"Player Accounts ({len(chunk)})", value=accounts.strip(), inline=False)
                embeds.append(embed)

        if not embeds:
            await interaction.followup.send("No player tags linked.")
            return

        view = ProfileView(player_tags, players, embeds)
        await interaction.followup.send(embed=embeds[0], view=view)

    # ---- /wipelinks ----

    @app_commands.command(name="wipelinks",
                          description="Remove specific player tags linked to your Discord account or someone else's")
    @app_commands.describe(someone_else="Mention another user to remove their linked player tags")
    @is_privileged()
    async def wipelinks(self, interaction: Interaction, someone_else: User | None = None):
        user = someone_else or interaction.user
        current_tags = await self.bot.repo.player_tags(user.id)
        if not current_tags:
            await interaction.response.send_message(f"No player tags found for {user.mention}.")
            return

        view = View(timeout=300)
        view.add_item(WipeTagSelect(user.id, current_tags))
        await interaction.response.send_message("Select the tags you want to remove:", view=view)

    # ---- /nicklink ----

    @app_commands.command(
        name="nicklink",
        description="Link a clan tag to a nickname or delete an existing nickname (leave nickname empty to delete)",
    )
    @app_commands.describe(
        clan_tag="The tag of the clan",
        nickname="The nickname to associate with the clan (leave empty to delete existing nickname)",
    )
    @is_privileged()
    async def nicklink(self, interaction: Interaction, clan_tag: str, nickname: str | None = None):
        tag = normalize_tag(clan_tag)
        guild_id = interaction.guild.id

        if not nickname or not nickname.strip():
            await self._delete_nickname(interaction, tag, guild_id)
            return

        nickname = nickname.strip()
        if len(nickname) >= 5:
            raise BotError("Nickname must be less than 5 characters.")

        try:
            await self.bot.cr.clan(tag)
        except ClanNotFound:
            raise BotError("The clan tag is not valid.") from None

        existing = await self.bot.repo.nickname_for_clan(tag, guild_id)
        if existing:
            embed = make_embed(
                "Update Nickname Confirmation",
                f"The clan tag `{tag}` is already linked with the nickname `{existing}` in this server.",
            )
            embed.add_field(name="New Nickname", value=nickname, inline=False)
            confirm = ConfirmView(interaction.user.id)
            await interaction.response.send_message(embed=embed, view=confirm)
            await confirm.wait()

            if confirm.confirmed:
                await self.bot.repo.set_clan_nickname(tag, guild_id, nickname)
                result = make_embed("Nickname Updated",
                                    f"The nickname for clan tag `{tag}` has been updated to `{nickname}`.",
                                    color=0x00FF00)
            elif confirm.confirmed is False:
                result = make_embed("Update Canceled",
                                    f"The nickname update for clan tag `{tag}` has been canceled.",
                                    color=0xFF0000)
            else:
                result = make_embed("Update Timeout", "You did not respond in time. No changes were made.")
            await interaction.followup.send(embed=result)
            return

        await self.bot.repo.set_clan_nickname(tag, guild_id, nickname)
        await interaction.response.send_message(
            f"Clan tag {tag} linked with nickname '{nickname}' in this server."
        )

    async def _delete_nickname(self, interaction: Interaction, clan_tag: str, guild_id: int):
        existing = await self.bot.repo.nickname_for_clan(clan_tag, guild_id)
        if not existing:
            await interaction.response.send_message(
                f"No nickname found for clan tag `{clan_tag}` in this server.", ephemeral=True
            )
            return

        embed = make_embed(
            "Delete Nickname Confirmation",
            f"Are you sure you want to delete the nickname `{existing}` for clan tag `{clan_tag}`?",
            color=0xFF6B6B,
        )
        embed.add_field(name="⚠️ Warning", value="This action cannot be undone.", inline=False)
        confirm = ConfirmView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=confirm)
        await confirm.wait()

        if confirm.confirmed:
            deleted = await self.bot.repo.delete_clan_nickname(clan_tag, guild_id)
            if deleted:
                result = make_embed("Nickname Deleted",
                                    f"The nickname `{existing}` for clan tag `{clan_tag}` has been "
                                    "successfully deleted.", color=0x00FF00)
            else:
                result = make_embed("Deletion Failed",
                                    "An error occurred while deleting the nickname. Please try again later.",
                                    color=0xFF0000)
        elif confirm.confirmed is False:
            result = make_embed("Deletion Canceled",
                                f"The nickname deletion for clan tag `{clan_tag}` has been canceled.")
        else:
            result = make_embed("Deletion Timeout", "You did not respond in time. No changes were made.")
        await interaction.followup.send(embed=result)

    # ---- /viewnicks ----

    @app_commands.command(name="viewnicks", description="View all clan nicknames in this server")
    async def viewnicks(self, interaction: Interaction):
        await interaction.response.defer()
        links = await self.bot.repo.clan_links_for_guild(interaction.guild.id)

        if not links:
            embed = make_embed("No Nicknames Found",
                               "There are no clan nicknames linked in this server.",
                               color=discord.Color.red().value)
            await interaction.followup.send(embed=embed)
            return

        links.sort(key=lambda link: link[1].lower())
        embed = make_embed("Clan Nicknames",
                           "Here are all the clan nicknames linked in this server, sorted alphabetically:")
        for clan_tag, nickname in links:
            try:
                clan = await self.bot.cr.clan(clan_tag)
                embed.add_field(name=f"#{clan_tag} - {clan['name']}", value=f"Nickname: {nickname}", inline=False)
            except Exception:
                embed.add_field(name=f"#{clan_tag}", value=f"Nickname: {nickname}", inline=False)
        await interaction.followup.send(embed=embed)


class ProfileView(View):
    def __init__(self, player_tags: list[str], players: list[dict | None], embeds: list[discord.Embed]):
        super().__init__(timeout=600)
        self.embeds = embeds
        self.page = 0

        options = [
            SelectOption(label=f"{(player or {}).get('name', 'Unknown')} (#{tag})", value=tag)
            for tag, player in zip(player_tags, players, strict=True)
        ]
        select = Select(placeholder="Select an account to view more info", options=options)

        async def on_select(interaction: Interaction):
            from cogs.misc import send_player_embed
            await send_player_embed(interaction, select.values[0])

        select.callback = on_select
        self.add_item(select)

        if len(embeds) > 1:
            self.prev_button = Button(label="Previous", style=ButtonStyle.secondary, disabled=True)
            self.next_button = Button(label="Next", style=ButtonStyle.secondary)
            self.prev_button.callback = self._make_pager(-1)
            self.next_button.callback = self._make_pager(1)
            self.add_item(self.prev_button)
            self.add_item(self.next_button)

    def _make_pager(self, delta: int):
        async def pager(interaction: Interaction):
            self.page = max(0, min(self.page + delta, len(self.embeds) - 1))
            self.prev_button.disabled = self.page == 0
            self.next_button.disabled = self.page == len(self.embeds) - 1
            await interaction.response.edit_message(embed=self.embeds[self.page], view=self)
        return pager


def _format_role(role: str) -> str:
    role = role.lower()
    if role == "coleader":
        return "Co-Leader"
    return role.capitalize()
