from cogs.admin import AdminCog
from cogs.clan import ClanCog
from cogs.links import LinksCog
from cogs.misc import MiscCog
from cogs.reminders import RemindersCog
from cogs.war import WarCog

ALL_COGS = (WarCog, ClanCog, LinksCog, AdminCog, RemindersCog, MiscCog)


async def setup_all(bot) -> None:
    for cog_class in ALL_COGS:
        await bot.add_cog(cog_class(bot))
