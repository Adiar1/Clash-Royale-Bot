import discord
from discord import Interaction
import asyncio
from utils.helpers import *
from utils.api import *
import statistics
import io
import matplotlib.pyplot as plt


async def handle_average_command(interaction: Interaction, player_tag: str, from_war: int, to_war: int):
    # Clean up player tag - remove '#' if present and capitalize
    player_tag = player_tag.strip('#').upper()

    if from_war <= to_war:
        await interaction.response.send_message(
            "The 'from' must be greater than the 'to' since it represents older wars", ephemeral=True)
        return

    if from_war < 1 or to_war < 1:
        await interaction.response.send_message("War numbers must be positive integers.", ephemeral=True)
        return

    await interaction.response.defer()

    try:
        # First get player info to check if they're in a clan
        player_info = await get_player_info(player_tag)
        if not player_info:
            await interaction.followup.send("Player not found. Please check the tag and try again.")
            return

        clan_info = await get_player_clan_info(player_tag)
        if not clan_info:
            await interaction.followup.send("This player is not currently in a clan.")
            return

        clan_tag = clan_info.get('tag', '').strip('#')

        # Gather fame data for each war in the range
        fame_tasks = []
        for n in range(from_war, to_war - 1, -1):  # Changed range to count down from from_war to to_war
            fame_tasks.append(get_fame_n_wars_ago(clan_tag, f"#{player_tag}", n))

        fame_results = await asyncio.gather(*fame_tasks)

        # Convert fame values to integers, replacing non-numeric values with 0
        fame_values = []
        for fame in fame_results:
            try:
                fame_values.append(int(fame))
            except (ValueError, TypeError):
                fame_values.append(0)

        if not fame_values:
            await interaction.followup.send("No fame data found for the specified range.")
            return

        # Calculate statistics
        average_fame = statistics.mean(fame_values)
        median_fame = statistics.median(fame_values)
        if len(fame_values) > 1:
            stdev_fame = statistics.stdev(fame_values)
            variance = statistics.variance(fame_values)
        else:
            stdev_fame = 0
            variance = 0
        max_fame = max(fame_values)
        min_fame = min(fame_values)

        # Set up dark theme for matplotlib
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#2F3136')  # Discord-like dark background
        ax.set_facecolor('#2F3136')  # Discord-like dark background

        # Create war numbers for x-axis (in chronological order from left to right)
        war_numbers = list(range(from_war, to_war - 1, -1))  # Count down from from_war to to_war

        # Plot with custom colors
        main_line_color = '#1E133E'
        average_line_color = '#9B59B6'

        # Line plot
        plt.plot(war_numbers, fame_values, marker='o', linestyle='-', color=main_line_color, linewidth=2,
                 markersize=8, markeredgecolor='white', markeredgewidth=1)
        plt.axhline(y=average_fame, color=average_line_color, linestyle='--',
                    label=f'Average ({average_fame:.1f})', linewidth=2)

        plt.title(f'Fame History for {player_info.get("name")}', color='white', pad=20)
        plt.xlabel('Wars Ago', color='white')
        plt.ylabel('Fame', color='white')

        # Customize grid
        plt.grid(True, alpha=0.2, color='gray')

        # Customize ticks
        ax.tick_params(colors='white')

        # Invert x-axis to show highest number on the left
        plt.gca().invert_xaxis()

        # Customize legend
        plt.legend(facecolor='#2F3136', edgecolor='gray', labelcolor='white')

        # Add some padding to the plot
        plt.margins(x=0.05)

        # Save plot to buffer
        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='#2F3136', edgecolor='none', bbox_inches='tight')
        buf.seek(0)
        plt.close()

        # Create embed
        embed = discord.Embed(
            title=f"Fame Analysis",
            description=f"Player: {player_info.get('name')} ({player_tag})",
            color=0x1E133E
        )

        embed.add_field(
            name="War Range",
            value=f"From {from_war} to {to_war} wars ago",
            inline=False
        )

        # Statistical analysis fields
        embed.add_field(
            name="Average Fame",
            value=f"{FAME_EMOJI} {average_fame:.1f}",
            inline=True
        )

        embed.add_field(
            name="Median Fame",
            value=f"{FAME_EMOJI} {median_fame:.1f}",
            inline=True
        )

        embed.add_field(
            name="Wars Analyzed",
            value=f"{len(fame_values)} wars",
            inline=True
        )

        embed.add_field(
            name="Highest Fame",
            value=f"{FAME_EMOJI} {max_fame}",
            inline=True
        )

        embed.add_field(
            name="Lowest Fame",
            value=f"{FAME_EMOJI} {min_fame}",
            inline=True
        )

        if len(fame_values) > 1:
            embed.add_field(
                name="Standard Deviation",
                value=f"{stdev_fame:.1f}",
                inline=True
            )

        # Add individual war breakdown
        breakdown = ""
        for war_num, fame in zip(war_numbers, fame_values):  # Using war_numbers directly since we want oldest first
            breakdown += f"{war_num} wars ago: {FAME_EMOJI} {fame}\n"

        embed.add_field(
            name="War Breakdown",
            value=breakdown or "No data available",
            inline=False
        )

        # Send the embed and the graph
        file = discord.File(buf, filename="fame_graph.png")
        embed.set_image(url="attachment://fame_graph.png")

        await interaction.followup.send(file=file, embed=embed)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")