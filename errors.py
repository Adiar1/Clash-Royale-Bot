"""Exception hierarchy for the bot.

Command handlers do not catch these; they propagate to the global
``tree.on_error`` handler in bot.py, which shows ``user_message`` to the user
and logs anything unexpected.
"""


class BotError(Exception):
    user_message = "Something went wrong while processing your request."

    def __init__(self, user_message: str | None = None):
        if user_message is not None:
            self.user_message = user_message
        super().__init__(self.user_message)


class InvalidClanTag(BotError):
    user_message = "That clan tag or nickname doesn't look right. Double-check it and try again."


class ClanNotFound(BotError):
    user_message = "No clan found with that tag. Double-check it and try again."


class PlayerNotFound(BotError):
    user_message = "No player found with that tag. Double-check it and try again."


class TournamentNotFound(BotError):
    user_message = "No tournament found with that tag. Double-check it and try again."


class NotLinked(BotError):
    user_message = "No linked Clash Royale account found. Use `/link` to link one first."


class NoDeckAILink(BotError):
    user_message = "No DeckAI ID linked to that account. Link one with `/link` first."


class RateLimited(BotError):
    user_message = "I'm being rate-limited by the Clash Royale API. Please try again in a minute."


class APIUnavailable(BotError):
    user_message = "The Clash Royale API isn't responding right now. Please try again later."
