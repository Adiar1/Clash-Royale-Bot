from discord import Interaction, TextChannel
from utils.api import get_decks_used_today, get_current_clan_members
from utils.database import get_discord_id_from_tag, get_clan_tag_by_nickname
from prettytable import PrettyTable

DISCORD_MESSAGE_LIMIT = 1800

async def handle_reminders_command(interaction: Interaction, channel: TextChannel, input_value: str):
    await interaction.response.defer(ephemeral=True)

    try:
        # Normalize the input to uppercase to handle case insensitivity
        input_value = input_value.lstrip('#').upper()

        # Determine if input is a clan tag or a nickname
        if len(input_value) < 5:
            # Try to get clan tag from nickname (normalize nickname to uppercase)
            clan_tag = get_clan_tag_by_nickname(input_value, interaction.guild.id)
            if clan_tag is None:
                await interaction.followup.send("Oopsy daisies. Check that tag/nickname real quick.", ephemeral=True)
                return
        else:
            clan_tag = input_value

        # Fetch decks used today
        decks_used_today = await get_decks_used_today(clan_tag)
        if not decks_used_today:
            await interaction.followup.send("No data found for the specified clan.", ephemeral=True)
            return

        # Get the current clan members
        clan_name, current_members = await get_current_clan_members(clan_tag)
        current_member_tags = {tag for tag, _ in current_members}

        # Filter for current members only
        current_decks_used = [
            (tag, name, decks) for tag, name, decks in decks_used_today if tag in current_member_tags
        ]

        # Fetch the number of current members
        num_current_members = len(current_members)

        if not current_decks_used:
            await interaction.followup.send(
                f"No current members have used decks today.\n"
                f"Total Current Members in {clan_name}: {num_current_members}",
                ephemeral=True
            )
            return

        # Send the header message once
        header = (
            f"Player Names with Decks Used Today for Clan #{clan_tag} ({clan_name}):\n"
            f"Total Current Members: {num_current_members}\n\n"
        )
        await channel.send(header)

        # Helper function to create a new table
        def create_table():
            table = PrettyTable()
            table.field_names = ["Player Name", "Decks Used"]
            return table

        table = create_table()
        messages = []  # List to store message parts
        pings = []     # Collect users to ping

        # Add data to the table and split into parts if necessary
        for tag, name, decks in current_decks_used:
            discord_id = get_discord_id_from_tag(tag)  # Check if tag is linked

            # Add row to the table
            table.add_row([name, decks])

            # Ping users with fewer than 4 decks used
            if discord_id and decks < 4:
                pings.append(f"<@{discord_id}>")

            # Check if the current table exceeds the Discord message limit
            table_str = f"```{table}```"
            if len(table_str) >= DISCORD_MESSAGE_LIMIT:
                # Store the current table as a message part and start a new one
                messages.append(table_str)
                table = create_table()  # Reset the table for new data

        # Add the last table if it contains data
        if len(table._rows) > 0:
            messages.append(f"```{table}```")

        # Send all message parts sequentially
        for message in messages:
            await channel.send(message)

        # Send pings if any
        if pings:
            await channel.send(" ".join(pings) + " You have used fewer than 4 decks today!")

        # Send confirmation to the command user
        await interaction.followup.send(f"List sent to {channel.mention}.", ephemeral=True)

    except Exception as e:
        print(f"Error sending decks used today: {e}")
        await interaction.followup.send("An error occurred while processing your request.", ephemeral=True)