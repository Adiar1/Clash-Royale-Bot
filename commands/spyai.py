import discord
from discord import Interaction, User
from utils.api import get_clan_war_spy_info
from utils.helpers import sanitize_tag, get_all_player_tags, get_deckai_id
import logging
import json

logger = logging.getLogger(__name__)


def format_card_list(cards):
    """Format a list of cards into a readable string"""
    if not cards or not isinstance(cards, list):
        return "No cards found"

    card_strings = []
    for card in cards:
        if isinstance(card, dict):
            name = card.get('name', 'Unknown Card')
            level = card.get('level', '?')
            card_strings.append(f"{name} (Lvl {level})")
        else:
            card_strings.append(str(card))

    return ", ".join(card_strings)


def format_win_rates(win_rates):
    """Format win rates into a readable string"""
    if not win_rates or not isinstance(win_rates, list):
        return "No win rate data"

    try:
        formatted_rates = [f"{float(rate) * 100:.1f}%" for rate in win_rates if rate is not None]
        return " | ".join(formatted_rates) if formatted_rates else "No win rate data"
    except (ValueError, TypeError):
        return "Invalid win rate data"


def format_date(date_str):
    """Format date string into a more readable format"""
    if not date_str:
        return "Unknown Date"

    try:
        from datetime import datetime
        date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return date_obj.strftime('%Y-%m-%d %H:%M UTC')
    except:
        return date_str


def create_spy_text_output(war_data):
    """Create a text-based output of the clan war spy data"""
    if not isinstance(war_data, dict):
        return "❌ **Error:** Invalid data format received from API"

    if not war_data:
        return "❌ **No data found** - The opponent might not have any recent clan war activity"

    output_lines = ["🕵️ **Clan War Spy Report**", ""]

    # Check if we have opponent decks data
    opponent_decks = war_data.get('opponentDecks', [])

    if not opponent_decks:
        output_lines.extend([
            "❌ **No opponent deck data found**",
            "",
            "**Raw API Response:**",
            f"```json\n{json.dumps(war_data, indent=2)}\n```"
        ])
        return "\n".join(output_lines)

    output_lines.append(f"📊 **Found {len(opponent_decks)} deck(s)**")
    output_lines.append("")

    for idx, deck_data in enumerate(opponent_decks, 1):
        if not isinstance(deck_data, dict):
            output_lines.append(f"⚠️ **Deck {idx}:** Invalid data format")
            continue

        # Get deck information
        cards = deck_data.get('deck', [])
        game_mode = deck_data.get('gameMode', 'Unknown Mode')
        date = deck_data.get('date', '')
        win_rates = deck_data.get('winRates', [])

        # Format the deck section
        output_lines.extend([
            f"🃏 **Deck {idx}:**",
            f"   **Game Mode:** {game_mode}",
            f"   **Date:** {format_date(date)}",
            f"   **Win Rates:** {format_win_rates(win_rates)}",
            ""
        ])

        # Format cards
        if cards and isinstance(cards, list):
            # Regular cards (first 8)
            regular_cards = cards[:8]
            if regular_cards:
                output_lines.append("   **Cards:**")
                formatted_cards = format_card_list(regular_cards)
                # Split long card lists into multiple lines
                if len(formatted_cards) > 100:
                    card_chunks = []
                    current_chunk = []
                    current_length = 0

                    for card in regular_cards:
                        card_str = f"{card.get('name', 'Unknown')} (Lvl {card.get('level', '?')})"
                        if current_length + len(card_str) > 80 and current_chunk:
                            card_chunks.append(", ".join(current_chunk))
                            current_chunk = [card_str]
                            current_length = len(card_str)
                        else:
                            current_chunk.append(card_str)
                            current_length += len(card_str) + 2  # +2 for ", "

                    if current_chunk:
                        card_chunks.append(", ".join(current_chunk))

                    for chunk in card_chunks:
                        output_lines.append(f"      {chunk}")
                else:
                    output_lines.append(f"      {formatted_cards}")

                output_lines.append("")

            # Tower card (9th card if exists)
            if len(cards) >= 9:
                tower_card = cards[8]
                if isinstance(tower_card, dict):
                    tower_name = tower_card.get('name', 'Unknown Tower')
                    tower_level = tower_card.get('level', '?')
                    output_lines.extend([
                        f"   **Tower:** {tower_name} (Lvl {tower_level})",
                        ""
                    ])
        else:
            output_lines.extend([
                "   **Cards:** No card data available",
                ""
            ])

        output_lines.append("─" * 50)
        output_lines.append("")

    # Add raw data section for debugging
    output_lines.extend([
        "🔍 **Raw API Response (for debugging):**",
        f"```json\n{json.dumps(war_data, indent=2)[:1500]}{'...' if len(json.dumps(war_data)) > 1500 else ''}\n```"
    ])

    return "\n".join(output_lines)


async def handle_clan_war_spy_command(
        interaction: Interaction,
        opponent_player_tag: str,
        someone_else: User = None,
        player_tag: str = None
):
    await interaction.response.defer()

    try:
        # Validate and sanitize opponent player tag
        if not opponent_player_tag:
            await interaction.followup.send("❌ Please provide a valid opponent player tag.")
            return

        sanitized_opponent_tag = sanitize_tag(opponent_player_tag)
        logger.info(f"Sanitized opponent tag: {sanitized_opponent_tag}")

        # Determine the user to get the DeckAI ID for
        target_user = someone_else or interaction.user
        logger.info(f"Target user: {target_user.id}")

        # First, get the player tag(s) for the target user
        player_tags = get_all_player_tags(target_user.id)
        logger.info(f"Player tags for user {target_user.id}: {player_tags}")

        if not player_tags:
            await interaction.followup.send(
                f"❌ No player tags found for {'the specified user' if someone_else else 'you'}. "
                "Please link your player tag using `/link` first."
            )
            return

        # Determine which player tag to use
        if player_tag:
            # If a specific player tag was provided, validate it belongs to the user
            sanitized_tag = sanitize_tag(player_tag)
            if sanitized_tag not in player_tags:
                await interaction.followup.send(
                    f"❌ The tag `{player_tag}` is not linked to {'the specified user' if someone_else else 'you'}.\n"
                    f"**Available tags:** {', '.join([f'#{tag}' for tag in player_tags])}"
                )
                return
            selected_player_tag = sanitized_tag
        else:
            # Use the main (first) player tag if none specified
            selected_player_tag = player_tags[0]

        logger.info(f"Selected player tag: {selected_player_tag}")

        # Get the DeckAI ID for the selected player tag
        account_id = get_deckai_id(selected_player_tag)
        logger.info(f"DeckAI ID for tag {selected_player_tag}: {account_id}")

        if not account_id:
            await interaction.followup.send(
                f"❌ No DeckAI ID found for player tag `#{selected_player_tag}` "
                f"({'the specified user' if someone_else else 'you'}).\n"
                "Please link your DeckAI ID using the appropriate command first."
            )
            return

        # Fetch the clan war spy information
        logger.info(
            f"Calling get_clan_war_spy_info with account_id: {account_id}, opponent_tag: {sanitized_opponent_tag}")
        war_data = await get_clan_war_spy_info(
            account_id,
            sanitized_opponent_tag
        )

        logger.info(f"War data received: {type(war_data)}")
        if war_data and isinstance(war_data, dict):
            logger.info(f"War data keys: {war_data.keys()}")

        # Create the text output
        spy_output = create_spy_text_output(war_data)

        # Discord has a 2000 character limit for messages
        if len(spy_output) > 2000:
            # Split the message into chunks
            chunks = []
            current_chunk = ""
            lines = spy_output.split('\n')

            for line in lines:
                if len(current_chunk) + len(line) + 1 > 1990:  # Leave some buffer
                    if current_chunk:
                        chunks.append(current_chunk)
                        current_chunk = line
                    else:
                        # Single line is too long, truncate it
                        chunks.append(line[:1990] + "...")
                        current_chunk = ""
                else:
                    current_chunk += line + '\n' if current_chunk else line

            if current_chunk:
                chunks.append(current_chunk)

            # Send the first chunk
            await interaction.followup.send(chunks[0])

            # Send remaining chunks
            for chunk in chunks[1:]:
                await interaction.followup.send(chunk)
        else:
            await interaction.followup.send(spy_output)

    except Exception as e:
        logger.error(f"Error in clan war spy command: {e}")
        logger.error(f"Error type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await interaction.followup.send(
            "❌ An error occurred while processing your request. Check the logs for details.")