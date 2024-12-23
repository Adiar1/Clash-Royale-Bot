import discord
from discord import Interaction, User
from utils.api import get_clan_war_spy_info
from utils.helpers import get_deckai_id, card_name_to_png
import io
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import logging
import os

logger = logging.getLogger(__name__)


def get_font_path():
    """Get the path to the Clash font."""
    font_path = 'assets/Clash_Regular.otf'
    if not os.path.exists(font_path):
        raise FileNotFoundError(
            f"Font file not found at {font_path}. Please ensure Clash_Regular.otf is in the assets directory.")
    return font_path


def download_image(url, max_size=(120, 120)):
    """
    Download and resize an image from a URL.

    Args:
        url (str): URL of the image to download
        max_size (tuple): Maximum size to resize the image to (width, height)

    Returns:
        PIL.Image or None: Processed image or None if download fails
    """
    try:
        response = requests.get(url)
        if response.status_code == 200:
            img = Image.open(io.BytesIO(response.content))

            # Resize the image while maintaining aspect ratio
            img.thumbnail(max_size, Image.LANCZOS)

            # Create a white background image
            background = Image.new('RGBA', max_size, (255, 255, 255, 255))

            # Calculate position to center the image
            offset = ((max_size[0] - img.width) // 2, (max_size[1] - img.height) // 2)

            # Paste the resized image onto the white background
            background.paste(img, offset, img if img.mode == 'RGBA' else None)

            return background
        return None
    except Exception as e:
        logger.error(f"Error downloading image {url}: {e}")
        return None


def create_clan_war_spy_image(war_data):
    """
    Create a visual representation of the clan war spy data

    Args:
        war_data (dict): Clan war data
    """
    try:
        font_path = get_font_path()

        # Create a white background image
        img_width = 1400
        img_height = 1500  # Increased height
        background_color = (240, 243, 249)
        img = Image.new('RGB', (img_width, img_height), color=background_color)
        draw = ImageDraw.Draw(img)

        # Load fonts
        title_font = ImageFont.truetype(font_path, 48)
        subtitle_font = ImageFont.truetype(font_path, 36)
        level_font = ImageFont.truetype(font_path, 20)
        stats_font = ImageFont.truetype(font_path, 20)

        # Colors
        title_color = (44, 54, 137)
        subtitle_color = (66, 82, 175)
        text_color = (50, 50, 50)
        stats_color = (100, 100, 100)

        # Title with decorative underline
        title_y = 50
        draw.text((img_width // 2, title_y), "Clan War Spy Report",
                  fill=title_color, anchor="mm", font=title_font)

        # Draw underline
        line_y = title_y + 40
        draw.line([(400, line_y), (1000, line_y)], fill=title_color, width=3)

        opponent_decks = war_data.get('opponentDecks', [])

        for idx, deck_data in enumerate(opponent_decks):
            cards = deck_data.get('deck', [])
            game_mode = deck_data.get('gameMode', 'Unknown Mode')
            date = deck_data.get('date', '')
            win_rates = deck_data.get('winRates', [])

            # Format date
            try:
                from datetime import datetime
                date_obj = datetime.fromisoformat(date.replace('Z', '+00:00'))
                formatted_date = date_obj.strftime('%Y-%m-%d %H:%M')
            except:
                formatted_date = date

            # Position calculation with more spacing
            column = idx % 2
            row = idx // 2
            base_x = 120 + column * (img_width // 2)
            base_y = 180 + row * 450  # Increased vertical spacing between rows

            # Section background
            section_padding = 20
            section_width = 550
            section_height = 400  # Increased height
            section_x = base_x - section_padding
            section_y = base_y - section_padding

            # Draw rounded rectangle background
            draw.rectangle(
                [section_x, section_y,
                 section_x + section_width, section_y + section_height],
                fill=(255, 255, 255),
                outline=subtitle_color,
                width=2
            )

            # Game Mode header
            mode_bg_height = 50
            draw.rectangle(
                [section_x, section_y,
                 section_x + section_width, section_y + mode_bg_height],
                fill=subtitle_color
            )

            # Draw game mode and date
            draw.text((section_x + section_width // 2, section_y + mode_bg_height // 2),
                      game_mode,
                      fill=(255, 255, 255), anchor="mm", font=subtitle_font)

            draw.text((section_x + section_width // 2, section_y + mode_bg_height + 25),
                      formatted_date,
                      fill=stats_color, anchor="mm", font=stats_font)

            # Draw cards in a grid layout
            for card_idx, card in enumerate(cards[:8]):  # Limit to 8 cards
                row = card_idx // 2
                col = card_idx % 2

                # Get card image URL
                card_image_url = card_name_to_png(card['name'])
                card_image = download_image(card_image_url)

                if card_image:
                    # Calculate card image position
                    card_x = section_x + 50 + col * 250
                    card_y = section_y + mode_bg_height + 60 + row * 150  # More vertical space

                    # Paste card image
                    img.paste(card_image, (card_x, card_y), card_image)

                    # Draw card level underneath
                    level_text = f"Lvl {card['level']}"
                    draw.text((card_x + 60, card_y + 130),  # Position level text
                              level_text,
                              fill=text_color, anchor="ms", font=level_font)

            # Draw Tower Princess separately at the bottom
            if len(cards) >= 9:  # If there's a Tower Princess
                tower_card = cards[8]
                tower_image_url = card_name_to_png(tower_card['name'])
                tower_image = download_image(tower_image_url)

                if tower_image:
                    tower_y = section_y + section_height - 120
                    tower_x = section_x + (section_width - tower_image.width) // 2
                    img.paste(tower_image, (tower_x, tower_y), tower_image)

                    # Draw tower level
                    draw.text((tower_x + 60, tower_y + 130),
                              f"Lvl {tower_card['level']}",
                              fill=text_color, anchor="ms", font=level_font)

            # Draw win rates
            if win_rates:
                win_rates_y = section_y + section_height - 60

                # Draw individual win rates
                win_rates_text = " | ".join([f"{rate * 100:.1f}%" for rate in win_rates])
                draw.text((section_x + section_width // 2, win_rates_y),
                          win_rates_text,
                          fill=text_color, anchor="mm", font=stats_font)

        # Convert to bytes
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        return img_byte_arr

    except Exception as e:
        logger.error(f"Error creating clan war spy image: {e}")
        return None


async def handle_clan_war_spy_command(
        interaction: Interaction,
        opponent_player_tag: str,
        someone_else: User = None
):
    await interaction.response.defer()

    try:
        # Determine the user to get the DeckAI ID for
        target_user = someone_else or interaction.user

        # Get the DeckAI ID for the target user
        account_id = get_deckai_id(target_user.id)

        if not account_id:
            await interaction.followup.send(
                f"No DeckAI ID found for {'the specified user' if someone_else else 'you'}. "
                "Please link your DeckAI ID using /link first."
            )
            return

        # Fetch the clan war spy information
        war_data = await get_clan_war_spy_info(
            account_id,
            opponent_player_tag
        )

        if not war_data:
            await interaction.followup.send("Could not retrieve clan war spy information.")
            return

        # Create the image
        img_byte_arr = create_clan_war_spy_image(war_data)

        if img_byte_arr is None:
            await interaction.followup.send("Failed to create clan war spy image.")
            return

        # Send the image
        await interaction.followup.send(
            file=discord.File(img_byte_arr, filename='clan_war_spy.png')
        )

    except Exception as e:
        logger.error(f"Error in clan war spy command: {e}")
        await interaction.followup.send("An error occurred while processing your request.")