import csv
import io

import discord
from discord import Interaction
from discord.ui import Button, View


def csv_file(headers: list[str], rows: list[list], filename: str) -> discord.File:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    buffer.seek(0)
    return discord.File(buffer, filename=filename)


class DownloadCSVButton(Button):
    """Sends the view's current table as a CSV. The parent view must expose
    ``csv_headers`` and ``csv_rows`` attributes (kept up to date on re-render)."""

    def __init__(self, filename: str = "data.csv"):
        super().__init__(label="Download CSV", style=discord.ButtonStyle.primary)
        self.filename = filename

    async def callback(self, interaction: Interaction):
        file = csv_file(self.view.csv_headers, self.view.csv_rows, self.filename)
        await interaction.response.send_message(file=file, ephemeral=True)


class ConfirmView(View):
    """Confirm/Cancel button pair; only the invoking user may respond."""

    def __init__(self, author_id: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: Interaction, button: Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: Interaction, button: Button):
        self.confirmed = False
        await interaction.response.defer()
        self.stop()
