from discord import Interaction, User, SelectOption
from discord.ui import View, Select


class TagSelect(Select):
    def __init__(self, user_id, current_tags):
        options = [SelectOption(label=tag, value=tag) for tag in current_tags]
        super().__init__(placeholder="Select tags to remove...", min_values=1, max_values=len(options), options=options)
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        selected_tags = self.values
        current_tags = get_all_player_tags(self.user_id)
        updated_tags = [tag for tag in current_tags if tag not in selected_tags]

        success = update_player_tags(self.user_id, ','.join(updated_tags))
        if success:
            await interaction.response.edit_message(content=f"Selected tags removed: {', '.join(selected_tags)}", view=None)
        else:
            await interaction.response.edit_message(content="An error occurred while updating player tags. Please try again later.", view=None)

class TagSelectView(View):
    def __init__(self, user_id, current_tags):
        super().__init__()
        self.add_item(TagSelect(user_id, current_tags))


from utils.helpers import get_privileged_roles, update_player_tags, get_all_player_tags


async def handle_wipelinks_command(interaction: Interaction, someone_else: User = None):
    privileged_roles = get_privileged_roles(interaction.guild.id)
    user_roles = [str(role.id) for role in interaction.user.roles]

    if not any(role in privileged_roles for role in user_roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Existing implementation
    user = someone_else if someone_else else interaction.user
    user_id = str(user.id)

    current_tags = get_all_player_tags(user_id)

    if not current_tags:
        await interaction.response.send_message(f"No player tags found for {user.mention}.")
        return

    await interaction.response.send_message("Select the tags you want to remove:", view=TagSelectView(user_id, current_tags))