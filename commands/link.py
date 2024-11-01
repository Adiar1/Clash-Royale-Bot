import requests
from discord import Interaction
from utils.helpers import CLASH_ROYALE_API_BASE_URL, CLASH_ROYALE_API_KEY
from utils.database import link_player_tag, get_all_player_tags

async def handle_link_command(interaction: Interaction, player_tag: str, alt_account: bool):
    if player_tag.startswith('#'):
        player_tag = player_tag[1:]
    player_tag = player_tag.upper()

    response = requests.get(f"{CLASH_ROYALE_API_BASE_URL}/players/%23{player_tag}", headers={
        "Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"
    })

    if response.status_code != 200:
        await interaction.response.send_message("Tag invalid. Please check the tag and try again.")
        return

    user_id = str(interaction.user.id)
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

    if result == "unlinked":
        await interaction.response.send_message(f"Player tag #{player_tag} unlinked from your Discord account.")
    elif result == "updated":
        await interaction.response.send_message(f"Player tag #{player_tag} updated in your Discord account.")
    elif result == "linked":
        await interaction.response.send_message(f"Player tag #{player_tag} linked to your Discord account.")
    else:
        await interaction.response.send_message("An error occurred while linking your player tag. Please try again later.")