import asyncio

import discord
from discord import ButtonStyle, Interaction, SelectOption, User, app_commands
from discord.ext import commands
from discord.ui import Button, Select, View

from cogs.checks import is_privileged
from errors import BotError, ClanNotFound, PlayerNotFound
from services.clash_royale import normalize_tag
from ui.embeds import EMBED_COLOR, SUCCESS_COLOR, make_embed
from ui.emojis import TROPHYROAD_EMOJI
from ui.views import ConfirmView


def _add_player_fields(embed: discord.Embed, player: dict) -> None:
    embed.add_field(name="Player Name", value=player.get("name", "Unknown"), inline=True)
    embed.add_field(name="Clan", value=player.get("clan", {}).get("name", "No Clan"), inline=True)
    embed.add_field(name="Trophies", value=str(player.get("trophies", 0)), inline=True)


class PlayerTagView(View):
    """Update / unlink / add-as-alt actions for an already-linked tag."""

    def __init__(self, player_tag: str, target_user: User | None = None, deckai_id: str | None = None):
        super().__init__(timeout=300)
        self.player_tag = player_tag
        self.target_user = target_user
        self.deckai_id = deckai_id

    def _user_id(self, interaction: Interaction) -> int:
        return self.target_user.id if self.target_user else interaction.user.id

    def _mention(self, interaction: Interaction) -> str:
        return self.target_user.mention if self.target_user else "your Discord account"

    async def _store_deckai(self, interaction: Interaction):
        if self.deckai_id:
            await interaction.client.repo.set_deckai_id(self.player_tag, self.deckai_id)

    @discord.ui.button(label="Update Tag", style=ButtonStyle.primary)
    async def update(self, interaction: Interaction, button: Button):
        repo = interaction.client.repo
        await repo.link_player_tag(self._user_id(interaction), self.player_tag, alt=False)
        await self._store_deckai(interaction)
        extra = f" and DeckAI ID `{self.deckai_id}`" if self.deckai_id else ""
        await interaction.response.send_message(
            f"Player tag `#{self.player_tag}`{extra} updated in {self._mention(interaction)}."
        )

    @discord.ui.button(label="Unlink Tag", style=ButtonStyle.danger)
    async def unlink(self, interaction: Interaction, button: Button):
        repo = interaction.client.repo
        await repo.unlink_player_tags(self._user_id(interaction), [self.player_tag])
        await repo.delete_deckai_id(self.player_tag)
        await interaction.response.send_message(
            f"Player tag `#{self.player_tag}` unlinked from {self._mention(interaction)}."
        )

    @discord.ui.button(label="Add as Alt Account", style=ButtonStyle.secondary)
    async def add_alt(self, interaction: Interaction, button: Button):
        repo = interaction.client.repo
        result = await repo.link_player_tag(self._user_id(interaction), self.player_tag, alt=True)
        if result == "too_many_tags":
            await interaction.response.send_message("You can't link more than 20 tags.")
            return
        await self._store_deckai(interaction)
        extra = f" with DeckAI ID `{self.deckai_id}`" if self.deckai_id else ""
        await interaction.response.send_message(
            f"Player tag `#{self.player_tag}`{extra} linked as an alt account to {self._mention(interaction)}."
        )


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

    # ---- /link & /forcelink ----

    async def _link_flow(self, interaction: Interaction, target_user: User | None,
                         player_tag: str, alt_account: bool, deckai_id: str | None):
        tag = normalize_tag(player_tag)
        try:
            player = await self.bot.cr.player(tag)
        except PlayerNotFound:
            raise BotError("Tag invalid. Please check the tag and try again.") from None

        user = target_user or interaction.user
        current_tags = await self.bot.repo.player_tags(user.id)
        possessive = f"{user.mention}'s account" if target_user else "your Discord account"

        if tag in current_tags:
            embed = discord.Embed(
                title="Tag Already Linked",
                description=f"The player tag `#{tag}` is already linked to {possessive}. "
                            "What would you like to do?",
                color=0x2B2D31,
            )
            _add_player_fields(embed, player)
            await interaction.response.send_message(embed=embed, view=PlayerTagView(tag, target_user, deckai_id))
            return

        result = await self.bot.repo.link_player_tag(user.id, tag, alt=alt_account)
        if result == "no_main_tag":
            await interaction.response.send_message("You can't have an alternate tag before you put a main one.")
            return
        if result == "too_many_tags":
            await interaction.response.send_message("You can't link more than 20 tags.")
            return

        if deckai_id:
            await self.bot.repo.set_deckai_id(tag, deckai_id)

        extra = f" with DeckAI ID `{deckai_id}`" if deckai_id else ""
        embed = discord.Embed(
            title="Tag Linked Successfully",
            description=f"Player tag `#{tag}`{extra} has been linked to {possessive}.",
            color=SUCCESS_COLOR,
        )
        _add_player_fields(embed, player)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="link",
                          description="Link, unlink, or update your Discord account with a Clash Royale player tag")
    @app_commands.describe(
        player_tag="The tag of the player",
        deckai_id="Optional DeckAI ID to link",
        alt_account="Is this an alternate account?",
    )
    async def link(self, interaction: Interaction, player_tag: str,
                   alt_account: bool = False, deckai_id: str | None = None):
        await self._link_flow(interaction, None, player_tag, alt_account, deckai_id)

    @app_commands.command(name="forcelink",
                          description="Forcefully link a player tag to another user's Discord account")
    @app_commands.describe(
        target_user="Mention the user to link the player tag to",
        player_tag="The tag of the player",
        deckai_id="Optional DeckAI ID to link",
        alt_account="Is this an alternate account?",
    )
    @is_privileged()
    async def forcelink(self, interaction: Interaction, target_user: User, player_tag: str,
                        alt_account: bool = False, deckai_id: str | None = None):
        await self._link_flow(interaction, target_user, player_tag, alt_account, deckai_id)

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
