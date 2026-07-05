import discord

EMBED_COLOR = 0x1E133E
SUCCESS_COLOR = 0x57F287
ERROR_COLOR = 0xFF0000

MAX_DESCRIPTION = 4096


def make_embed(title: str, description: str = "", color: int = EMBED_COLOR) -> discord.Embed:
    if len(description) > MAX_DESCRIPTION:
        description = description[:MAX_DESCRIPTION - 3] + "..."
    return discord.Embed(title=title, description=description, color=color)


def excel_like_sort_key(s: str) -> str:
    """Case/character-insensitive sort key matching spreadsheet ordering."""
    return "".join(f"{ord(c):04}" for c in s.strip().lower())
