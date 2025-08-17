import requests
from discord import Interaction, User, Embed, ButtonStyle
from discord.ui import Button, View
from utils.helpers import (
    CLASH_ROYALE_API_BASE_URL,
    CLASH_ROYALE_API_KEY,
    get_all_player_tags,
    link_player_tag,
    update_player_tags, link_deckai_id, unlink_deckai_id, sanitize_tag
)


class PlayerTagView(View):
    def __init__(self, player_tag: str, target_user: User = None, deckai_id: str = None):
        super().__init__()
        self.player_tag = player_tag
        self.target_user = target_user or None
        self.deckai_id = deckai_id

        # Update button
        update_btn = Button(label="Update Tag", style=ButtonStyle.primary, custom_id=f"update_{player_tag}")
        update_btn.callback = self.update_callback
        self.add_item(update_btn)

        # Unlink button
        unlink_btn = Button(label="Unlink Tag", style=ButtonStyle.danger, custom_id=f"unlink_{player_tag}")
        unlink_btn.callback = self.unlink_callback
        self.add_item(unlink_btn)

        # Add alt account button
        alt_btn = Button(label="Add as Alt Account", style=ButtonStyle.secondary, custom_id=f"alt_{player_tag}")
        alt_btn.callback = self.alt_callback
        self.add_item(alt_btn)

    async def update_callback(self, interaction: Interaction):
        user_id = str(self.target_user.id if self.target_user else interaction.user.id)
        result = link_player_tag(user_id, self.player_tag, alt=False)

        if result and self.deckai_id:
            link_deckai_id(self.player_tag, self.deckai_id)

        additional_msg = f" and DeckAI ID `{self.deckai_id}`" if self.deckai_id else ""
        user_mention = self.target_user.mention if self.target_user else "your Discord account"
        await interaction.response.send_message(
            f"Player tag `#{self.player_tag}`{additional_msg} updated in {user_mention}.")

    async def unlink_callback(self, interaction: Interaction):
        user_id = str(self.target_user.id if self.target_user else interaction.user.id)
        current_tags = get_all_player_tags(user_id)
        updated_tags = [tag for tag in current_tags if tag != self.player_tag]

        success = update_player_tags(user_id, ','.join(updated_tags))
        if success:
            # Also remove DeckAI ID if it exists
            unlink_deckai_id(self.player_tag)
            user_mention = self.target_user.mention if self.target_user else "your Discord account"
            await interaction.response.send_message(
                f"Player tag `#{self.player_tag}` unlinked from {user_mention}.")
        else:
            await interaction.response.send_message(
                "An error occurred while unlinking the player tag. Please try again later.")

    async def alt_callback(self, interaction: Interaction):
        user_id = str(self.target_user.id if self.target_user else interaction.user.id)
        current_tags = get_all_player_tags(user_id)
        if len(current_tags) >= 20:
            await interaction.response.send_message("You can't link more than 20 tags.")
            return

        result = link_player_tag(user_id, self.player_tag, alt=True)
        if result and self.deckai_id:
            link_deckai_id(self.player_tag, self.deckai_id)

        additional_msg = f" with DeckAI ID `{self.deckai_id}`" if self.deckai_id else ""
        user_mention = self.target_user.mention if self.target_user else "your account"
        await interaction.response.send_message(
            f"Player tag `#{self.player_tag}`{additional_msg} linked as an alt account to {user_mention}.")


async def handle_forcelink_command(interaction: Interaction, target_user: User, player_tag: str, alt_account: bool, deckai_id: str = None):
    player_tag = sanitize_tag(player_tag)

    # Verify tag with Clash Royale API
    response = requests.get(f"{CLASH_ROYALE_API_BASE_URL}/players/%23{player_tag}", headers={
        "Authorization": f"Bearer {CLASH_ROYALE_API_KEY}"
    })

    if response.status_code != 200:
        await interaction.response.send_message("Tag invalid. Please check the tag and try again.")
        return

    player_data = response.json()
    user_id = str(target_user.id)
    current_tags = get_all_player_tags(user_id)

    # Check if tag is already linked
    if player_tag in current_tags:
        embed = Embed(
            title="Tag Already Linked",
            description=f"The player tag `#{player_tag}` is already linked to {target_user.mention}'s account. What would you like to do?",
            color=0x2b2d31
        )

        # Add player info to embed
        embed.add_field(name="Player Name", value=player_data.get('name', 'Unknown'), inline=True)
        embed.add_field(name="Clan", value=player_data.get('clan', {}).get('name', 'No Clan'), inline=True)
        embed.add_field(name="Trophies", value=str(player_data.get('trophies', 0)), inline=True)

        view = PlayerTagView(player_tag, target_user, deckai_id)
        await interaction.response.send_message(embed=embed, view=view)
        return

    # Handle new tag linking
    if alt_account:
        if not current_tags:
            await interaction.response.send_message("You can't have an alternate tag before you put a main one.")
            return
        if len(current_tags) >= 20:
            await interaction.response.send_message("You can't link more than 20 tags.")
            return
        result = link_player_tag(user_id, player_tag, alt=True, deckai_id=deckai_id)
    else:
        result = link_player_tag(user_id, player_tag, alt=False, deckai_id=deckai_id)

    # Handle link results
    if result == "unlinked":
        await interaction.response.send_message(f"Player tag `#{player_tag}` unlinked from {target_user.mention}'s account.")
    elif result == "updated":
        additional_msg = f" and DeckAI ID `{deckai_id}`" if deckai_id else ""
        await interaction.response.send_message(
            f"Player tag `#{player_tag}`{additional_msg} updated in {target_user.mention}'s account.")
    elif result == "linked":
        additional_msg = f" with DeckAI ID `{deckai_id}`" if deckai_id else ""
        embed = Embed(
            title="Tag Linked Successfully",
            description=f"Player tag `#{player_tag}`{additional_msg} has been linked to {target_user.mention}'s account.",
            color=0x57F287
        )
        embed.add_field(name="Player Name", value=player_data.get('name', 'Unknown'), inline=True)
        embed.add_field(name="Clan", value=player_data.get('clan', {}).get('name', 'No Clan'), inline=True)
        embed.add_field(name="Trophies", value=str(player_data.get('trophies', 0)), inline=True)

        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message(
            "An error occurred while linking the player tag. Please try again later.")