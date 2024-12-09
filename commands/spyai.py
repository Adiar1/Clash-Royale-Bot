import discord
from discord import Interaction
from utils.api import get_clan_war_spy_info
import io
from PIL import Image, ImageDraw, ImageFont
import requests


def download_font():
    try:
        import os
        if not os.path.exists('assets/Roboto-Medium.ttf'):
            os.makedirs('assets', exist_ok=True)
            response = requests.get('https://github.com/google/fonts/raw/main/apache/roboto/static/Roboto-Medium.ttf')
            with open('assets/Roboto-Medium.ttf', 'wb') as f:
                f.write(response.content)
        return 'assets/Roboto-Medium.ttf'
    except:
        return None


def create_clan_war_spy_image(war_data):
    """Create a visual representation of the clan war spy data"""
    font_path = download_font() or None

    # Create a white background image
    img_width = 1200
    img_height = 800
    background_color = (255, 255, 255)
    img = Image.new('RGB', (img_width, img_height), color=background_color)
    draw = ImageDraw.Draw(img)

    # Load fonts
    title_font = ImageFont.truetype(font_path, 30) if font_path else None
    card_font = ImageFont.truetype(font_path, 20) if font_path else None

    # Title
    draw.text((img_width // 2, 50), "Clan War Spy Report",
              fill=(0, 0, 0), anchor="mm", font=title_font)

    # Opponent Decks Section
    opponent_decks = war_data.get('opponentDecks', [])
    player_winrates = war_data.get('winRates', [])

    for idx, deck in enumerate(opponent_decks):
        # Deck cards
        cards = deck.get('deck', [])
        game_mode = deck.get('gameMode', 'Unknown Mode')

        # Position calculation
        column = idx % 2
        row = idx // 2
        base_x = 50 + column * (img_width // 2)
        base_y = 150 + row * 300

        # Game Mode
        draw.text((base_x, base_y - 30), game_mode,
                  fill=(0, 0, 0), font=title_font)

        # Draw cards
        for card_idx, card in enumerate(cards):
            card_x = base_x + (card_idx % 3) * 100
            card_y = base_y + (card_idx // 3) * 50

            card_text = f"{card['name']} (Lvl {card['level']})"
            draw.text((card_x, card_y), card_text,
                      fill=(0, 0, 0), font=card_font)

        # Winrates
        if idx < len(player_winrates):
            win_text = f"Player Win Rate: {player_winrates[idx] * 100:.2f}%"
            draw.text((base_x, base_y + 200), win_text,
                      fill=(0, 0, 0), font=title_font)

    # Convert to bytes
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr


async def handle_clan_war_spy_command(interaction: Interaction, account_id: str, opponent_player_tag: str):
    await interaction.response.defer()

    try:
        # Fetch the clan war spy information
        war_data = await get_clan_war_spy_info(
            account_id,  # Explicitly pass the account ID
            opponent_player_tag
        )

        if not war_data:
            await interaction.followup.send("Could not retrieve clan war spy information.")
            return

        # Create the image
        img_byte_arr = create_clan_war_spy_image(war_data)

        # Send the image
        await interaction.followup.send(
            file=discord.File(img_byte_arr, filename='clan_war_spy.png')
        )

    except Exception as e:
        print(f"Error in clan war spy command: {e}")
        await interaction.followup.send("An error occurred while processing your request.")