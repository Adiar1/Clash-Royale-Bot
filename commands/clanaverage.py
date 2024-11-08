import asyncio
from typing import List, Tuple, Dict
import statistics
from discord import Interaction, Embed
import pandas as pd
from collections import defaultdict

from utils.api import get_current_clan_members, get_fame_n_wars_ago, get_decks_used_n_wars_ago
from utils.helpers import FAME_EMOJI, MULTIDECK_EMOJI


async def handle_clan_average_command(interaction: Interaction, clan_tag: str, from_war: int, to_war: int) -> None:
    clan_tag=clan_tag.strip("#").upper()
    try:
        await interaction.response.defer()

        # Fetch current clan members
        clan_name, current_members = await get_current_clan_members(clan_tag)

        # Initialize data structures
        member_data = defaultdict(lambda: {'fame': [], 'decks': []})
        war_summaries = []

        # Collect data for each war
        for war_num in range(to_war, from_war + 1):
            war_fame = []
            war_decks = []

            for player_tag, player_name in current_members:
                try:
                    # Get fame and deck data and ensure they're integers
                    fame = int(await get_fame_n_wars_ago(clan_tag, player_tag, war_num) or 0)
                    decks = int(await get_decks_used_n_wars_ago(clan_tag, player_tag, war_num) or 0)

                    # Store individual member data
                    member_data[player_name]['fame'].append(fame)
                    member_data[player_name]['decks'].append(decks)

                    war_fame.append(fame)
                    war_decks.append(decks)
                except (ValueError, TypeError):
                    # If conversion fails, use 0 as default
                    member_data[player_name]['fame'].append(0)
                    member_data[player_name]['decks'].append(0)
                    war_fame.append(0)
                    war_decks.append(0)

            # Calculate war summary statistics
            try:
                war_summaries.append({
                    'war_num': war_num,
                    'total_fame': sum(war_fame),
                    'avg_fame': statistics.mean(war_fame) if war_fame else 0,
                    'med_fame': statistics.median(war_fame) if war_fame else 0,
                    'total_decks': sum(war_decks),
                    'avg_decks': statistics.mean(war_decks) if war_decks else 0,
                    'participation': sum(1 for d in war_decks if d > 0) / len(war_decks) * 100 if war_decks else 0
                })
            except statistics.StatisticsError:
                print(f"Statistics error for war {war_num}")
                continue

        # Calculate member averages and consistency
        member_stats = []
        for name, data in member_data.items():
            if not data['fame']:  # Skip if no data
                continue

            try:
                fame_avg = statistics.mean(data['fame'])
                fame_std = statistics.stdev(data['fame']) if len(data['fame']) > 1 else 0
                decks_avg = statistics.mean(data['decks'])
                participation = sum(1 for d in data['decks'] if d > 0) / len(data['decks']) * 100

                member_stats.append({
                    'name': name,
                    'avg_fame': fame_avg,
                    'fame_std': fame_std,
                    'avg_decks': decks_avg,
                    'participation': participation,
                    'consistency_score': (fame_avg / (fame_std + 1)) * (participation / 100)  # Higher is better
                })
            except statistics.StatisticsError:
                print(f"Statistics error for member {name}")
                continue

        # Sort member stats by consistency score
        member_stats.sort(key=lambda x: x['consistency_score'], reverse=True)

        # Create DataFrames for visualization
        war_df = pd.DataFrame(war_summaries)
        member_df = pd.DataFrame(member_stats)

        if war_df.empty or member_df.empty:
            await interaction.followup.send("No data available for analysis.")
            return

        # Create main embed with summary statistics
        embed = create_summary_embed(clan_name, clan_tag, war_df, member_df)

        # Create React component for visualizations
        charts = create_visualization_component(war_df, member_df)

        # Send response
        await interaction.edit_original_response(embed=embed)

    except Exception as e:
        print(f"Error in clan average command: {e}")
        await interaction.followup.send("An error occurred while processing the clan analysis.")


def create_summary_embed(clan_name: str, clan_tag: str, war_df: pd.DataFrame, member_df: pd.DataFrame) -> Embed:
    embed = Embed(
        title=f"Clan Performance Analysis for {clan_name} #{clan_tag}",
        color=0x1E133E
    )

    # War Performance Summary
    embed.add_field(
        name=f"{FAME_EMOJI} Fame Statistics",
        value=f"Average Fame per War: {war_df['total_fame'].mean():,.0f}\n"
              f"Best War Fame: {war_df['total_fame'].max():,.0f}\n"
              f"Average Member Fame: {war_df['avg_fame'].mean():,.0f}",
        inline=False
    )

    # Deck Usage Summary
    embed.add_field(
        name=f"{MULTIDECK_EMOJI} Deck Usage",
        value=f"Average Deck Usage: {war_df['avg_decks'].mean():.1f}/4\n"
              f"Average Participation: {war_df['participation'].mean():.1f}%",
        inline=False
    )

    # Top Performers
    top_performers = member_df.head(3)
    embed.add_field(
        name="🏆 Most Consistent Performers",
        value="\n".join([
            f"{i + 1}. `{row['name']}` - {row['avg_fame']:,.0f} avg fame, "
            f"{row['participation']:.1f}% participation"
            for i, (_, row) in enumerate(top_performers.iterrows())
        ]),
        inline=False
    )

    # Areas for Improvement
    needs_improvement = member_df[member_df['participation'] < 75].shape[0]
    embed.add_field(
        name="📈 Areas for Improvement",
        value=f"• {needs_improvement} members below 75% participation\n"
              f"• {member_df[member_df['avg_decks'] < 3].shape[0]} members averaging <3 decks/war\n"
              f"• {member_df[member_df['fame_std'] > member_df['fame_std'].mean()].shape[0]} members with high fame variance",
        inline=False
    )

    return embed


def create_visualization_component(war_df: pd.DataFrame, member_df: pd.DataFrame) -> str:
    """Creates a React component with multiple charts for clan analysis"""
    return """
import React from 'react';
import {
    LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
    ResponsiveContainer, Legend
} from 'recharts';

const ClanAnalysis = () => {
    const warData = ${JSON.stringify(war_df.to_dict('records'))};
    const memberData = ${JSON.stringify(member_df.to_dict('records'))};

    return (
        <div className="space-y-8 p-4">
            {/* Fame Trend Chart */}
            <div className="h-64">
                <h3 className="text-lg font-semibold mb-2">War Performance Trend</h3>
                <ResponsiveContainer>
                    <LineChart data={warData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="war_num" label="Wars Ago" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="total_fame" stroke="#8884d8" name="Total Fame" />
                        <Line type="monotone" dataKey="participation" stroke="#82ca9d" name="Participation %" />
                    </LineChart>
                </ResponsiveContainer>
            </div>

            {/* Member Performance Distribution */}
            <div className="h-64">
                <h3 className="text-lg font-semibold mb-2">Member Performance Distribution</h3>
                <ResponsiveContainer>
                    <BarChart data={memberData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="name" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="avg_fame" fill="#8884d8" name="Average Fame" />
                        <Bar dataKey="fame_std" fill="#82ca9d" name="Fame Consistency" />
                    </BarChart>
                </ResponsiveContainer>
            </div>

            {/* Deck Usage Analysis */}
            <div className="h-64">
                <h3 className="text-lg font-semibold mb-2">Deck Usage Analysis</h3>
                <ResponsiveContainer>
                    <BarChart data={warData}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="war_num" label="Wars Ago" />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="avg_decks" fill="#8884d8" name="Average Decks Used" />
                    </BarChart>
                </ResponsiveContainer>
            </div>
        </div>
    );
};

export default ClanAnalysis;
    """