"""Contains the LoggingManager class, which handles logging of aura changes and events."""

import discord

from discord.ext import tasks
from collections import defaultdict

from models import *
from config import LOGGING_INTERVAL


class LoggingManager:
    def __init__(self, client: discord.Client, guilds: dict[int, Guild]):
        """Initialise the LoggingManager with the Discord client and guilds."""
        self.client = client
        self.guilds = guilds
        self.log_cache = defaultdict(list)

    def log_aura_change(
        self,
        guild_id: int,
        recipient_id: int,
        user_id: int,
        event: ReactionEvent,
        emoji: str,
        points: int,
        url: str,
    ) -> None:
        """Log the aura change event to the guild's log channel.

        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        recipient_id: `int`
            The ID of the user receiving the aura change.
        user_id: `int`
            The ID of the user giving the aura change.
        event: `ReactionEvent`
            The event type that triggered the aura change.
        emoji: `str`
            The emoji used for the reaction.
        points: `int`
            The number of aura points given or taken away.
        url: `str`
            The URL of the message where the reaction was added or removed."""
        sign = ""
        if points > 0:
            sign = "+"
        elif points < 0:
            sign = "-"

        connective = "to" if event.is_add else "from"
        log_message = f"<@{user_id}> [{event.past}]({url}) {emoji} {connective} <@{recipient_id}> ({sign}{abs(points)} points)"

        self.log_cache[guild_id].append(log_message)

    def log_event(
        self,
        guild_id: int,
        recipient_id: int,
        user_id: int,
        event: LogEvent,
        points: int = None,
    ) -> None:
        """Log the event to the guild's log channel.

        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        recipient_id: `int`
            The ID of the user receiving the event.
        user_id: `int`
            The ID of the user completing the event.
        event: `LogEvent`
            The event type that triggered the log.
        points: `int`, optional
            The number of aura points given or taken away. Required for manual changes.
        """
        match event:
            case LogEvent.MANUAL:
                if points is None:
                    raise ValueError("Points must be provided for manual changes.")
                log_message = f"<@{user_id}> manually changed aura of <@{recipient_id}> ({'+' if points > 0 else ''}{points} points)"
            case LogEvent.SPAMMING:
                log_message = f"<@{user_id}> was temporarily banned for {self.guilds[guild_id].limits.penalty} seconds from giving aura due to spamming reactions."
            case LogEvent.DENY_GIVING | LogEvent.DENY_RECEIVING | LogEvent.DENY_BOTH:
                log_message = (
                    f"<@{user_id}> denied <@{recipient_id}> from {str(event)} aura."
                )
            case LogEvent.ALLOW_GIVING | LogEvent.ALLOW_RECEIVING | LogEvent.ALLOW_BOTH:
                log_message = (
                    f"<@{user_id}> allowed <@{recipient_id}> to {str(event)} aura."
                )
            case _:
                raise ValueError()

        self.log_cache[guild_id].append(log_message)

    @tasks.loop(seconds=LOGGING_INTERVAL)
    async def send_batched_logs(self):
        """Send all batched logs to the respective guild's log channel.

        Runs every `LOGGING_INTERVAL` seconds."""
        for guild_id, logs in list(self.log_cache.items()):
            if logs:
                channel_id = self.guilds[guild_id].log_channel_id
                if channel_id is not None:
                    channel = self.client.get_channel(channel_id)
                    if channel is not None:
                        try:
                            await channel.send(
                                "\n".join(logs),
                                allowed_mentions=discord.AllowedMentions(users=False),
                            )
                        except discord.Forbidden:
                            print(
                                f"Failed to send logs to channel {channel_id} in guild {guild_id}."
                            )
                        except discord.HTTPException as e:
                            print(f"Failed to send logs: HTTPException: {e}")

                self.log_cache[guild_id].clear()
