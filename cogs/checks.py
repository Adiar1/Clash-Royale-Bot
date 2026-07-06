from discord import Interaction, app_commands


async def user_is_privileged(interaction: Interaction) -> bool:
    """Whether the user holds one of the guild's configured privileged roles.

    If a guild has not configured any privileged roles yet, everyone is
    allowed (matches the behavior documented in /info; also guarantees
    /editperms can't lock a server out).
    """
    role_ids = await interaction.client.repo.privileged_role_ids(interaction.guild.id)
    if not role_ids:
        return True
    user_role_ids = {role.id for role in interaction.user.roles}
    return any(role_id in user_role_ids for role_id in role_ids)


def is_privileged():
    """Restrict a command to the guild's configured privileged roles."""
    return app_commands.check(user_is_privileged)
