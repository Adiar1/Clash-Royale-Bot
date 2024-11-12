import discord
from discord import Interaction
import asyncio
from utils.helpers import *
from utils.api import *
import statistics
import io
import matplotlib.pyplot as plt
import numpy as np


async def handle_stats_command(interaction: Interaction, player_tag: str, from_war: int, to_war: int):
    # Clean up player tag - remove '#' if present and capitalize
    player_tag = player_tag.strip('#').upper()

    if from_war < to_war:
        await interaction.response.send_message(
            "The 'from' must be greater or equal than the 'to' since it represents older wars", ephemeral=True)
        return

    if from_war < 1 or to_war < 1:
        await interaction.response.send_message("War numbers must be positive integers.", ephemeral=True)
        return

    if from_war > 10 or to_war > 10:
        await interaction.response.send_message("I can't remember more than 10 weeks ago.", ephemeral=True)
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
        for n in range(from_war, to_war - 1, -1):
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
        max_fame = max(fame_values)
        min_fame = min(fame_values)

        # Set up dark theme for matplotlib
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.patch.set_facecolor('#2F3136')
        ax.set_facecolor('#2F3136')

        # Plot with custom colors
        main_line_color = '#1E133E'
        average_line_color = '#9B59B6'
        trend_line_color = '#ff00d6'

        war_numbers = list(range(from_war, to_war - 1, -1))

        # Line plot
        plt.plot(war_numbers, fame_values, marker='o', linestyle='-' if len(fame_values) > 1 else 'None',
                 color=main_line_color, linewidth=2, markersize=8, markeredgecolor='white', markeredgewidth=1)

        # Only calculate and plot trend line if we have more than one point
        if len(fame_values) > 1:
            trend_line = np.polyfit(war_numbers, fame_values, 1)
            trend_func = np.poly1d(trend_line)
            plt.plot(war_numbers, [trend_func(x) for x in war_numbers], color=trend_line_color,
                     linestyle='--', label=f'Regression Line', linewidth=2)

            # Calculate prediction
            if to_war == 1:
                next_war_prediction = trend_func(0)
            elif to_war == 2:
                next_war_prediction = trend_func(0)
            else:
                next_war_prediction = trend_func(war_numbers[-1] - 1)
        else:
            # For single point, use the point value as prediction
            next_war_prediction = fame_values[0]

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
        plt.legend(facecolor='#2F3136', edgecolor='gray', labelcolor='white',
                   loc='upper left', bbox_to_anchor=(1, 1))

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
            description=f"Player: {player_info.get('name')} (#{player_tag})",
            color=0x1E133E
        )

        embed.add_field(
            name="War Range",
            value=f"From {from_war} to {to_war} wars ago \n {len(fame_values)} wars analyzed",
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
            name="Highest Fame",
            value=f"{FAME_EMOJI} {max_fame}",
            inline=True
        )

        embed.add_field(
            name="Lowest Fame",
            value=f"{FAME_EMOJI} {min_fame}",
            inline=True
        )

        # Only add standard deviation for multiple points
        if len(fame_values) > 1:
            stdev_fame = statistics.stdev(fame_values)
            embed.add_field(
                name="Standard Deviation",
                value=f"{stdev_fame:.1f}",
                inline=True
            )

        embed.add_field(
            name=f'Prediction for {"current war" if to_war == 1 else f"{to_war-1} wars ago"}',
            value=f"{FAME_EMOJI} {next_war_prediction:.1f}",
            inline=True
        )

        # Send the embed and the graph
        file = discord.File(buf, filename="fame_graph.png")
        embed.set_image(url="attachment://fame_graph.png")

        await interaction.followup.send(file=file, embed=embed)

    except Exception as e:
        await interaction.followup.send(f"An error occurred: {str(e)}")