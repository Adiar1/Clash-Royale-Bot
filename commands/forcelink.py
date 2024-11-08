from discord import Interaction, User
from utils.helpers import get_all_player_tags, link_player_tag


async def handle_forcelink_command(interaction: Interaction, target_user: User, player_tag: str, alt_account: bool):
    if player_tag.startswith('#'):
        player_tag = player_tag[1:]
    player_tag = player_tag.upper()

    user_id = str(target_user.id)
    current_tags = get_all_player_tags(user_id)

    if alt_account:
        if not current_tags:
            await interaction.response.send_message("You can't have an alternate tag before you put a main one.")
            return
        if len(current_tags) >= 20:
            await interaction.response.send_message("You can't link more than 20 tags.")
            return
        if player_tag in current_tags:
            await interaction.response.send_message("This player tag is already linked.")
            return
        result = link_player_tag(user_id, player_tag, alt=True)
    else:
        result = link_player_tag(user_id, player_tag, alt=False)

    if result == "updated":
        await interaction.response.send_message(f"Player tag #{player_tag} updated in {target_user.mention}'s account.")
    elif result == "linked":
        await interaction.response.send_message(f"Player tag #{player_tag} linked to {target_user.mention}'s account.")
    else:
        await interaction.response.send_message("An error occurred while linking the player tag. Please try again later.")