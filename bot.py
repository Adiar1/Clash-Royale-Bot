import logging

import aiohttp
import discord
from discord import Interaction, app_commands
from discord.ext import commands

from config import Config
from db.database import Database
from db.repository import Repository
from errors import BotError
from services.clash_royale import ClashRoyaleClient
from services.deck_ai import DeckAIClient

logger = logging.getLogger(__name__)


class ClashBot(commands.Bot):
    """Bot with shared service clients and repository attached

    Cogs reach these through ``interaction.client`` / ``self.bot``:
    ``bot.cr`` (Clash Royale API), ``bot.deckai`` (DeckAI API),
    ``bot.repo`` (database).
    """

    def __init__(self, config: Config):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="/", intents=intents)
        self.config = config
        self.session: aiohttp.ClientSession | None = None
        self.db: Database | None = None
        self.repo: Repository | None = None
        self.cr: ClashRoyaleClient | None = None
        self.deckai: DeckAIClient | None = None
        self._synced = False

    async def setup_hook(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        self.db = Database(self.config.database_path)
        connection = await self.db.connect()
        self.repo = Repository(connection)
        self.cr = ClashRoyaleClient(self.session, self.config.clash_royale_api_key)
        self.deckai = DeckAIClient(self.session, self.config.deckai_api_key)

        self.tree.on_error = self.on_app_command_error

        from cogs import setup_all
        await setup_all(self)

    async def on_ready(self) -> None:
        logger.info("%s is now running!", self.user)

        num_servers = len(self.guilds)
        num_users = sum(guild.member_count or 0 for guild in self.guilds)
        await self.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{num_servers} server{'s' if num_servers != 1 else ''} | {num_users} users",
        ))

        # Sync once per process, not on every reconnect.
        if not self._synced:
            await self.tree.sync()
            self._synced = True
            logger.info("Application commands synced")

    async def close(self) -> None:
        await super().close()
        if self.session is not None:
            await self.session.close()
        if self.db is not None:
            await self.db.close()

    async def on_app_command_error(self, interaction: Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original

        if isinstance(error, app_commands.CheckFailure):
            message = "You don't have permission to use this command."
        elif isinstance(error, BotError):
            message = error.user_message
        else:
            command = interaction.command.qualified_name if interaction.command else "unknown"
            logger.error("Unhandled error in /%s", command, exc_info=error)
            message = "An unexpected error occurred while processing your request."

        try:
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            logger.warning("Could not deliver error message for interaction %s", interaction.id)
