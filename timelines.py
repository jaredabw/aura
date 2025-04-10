"""Contains the TimelinesManager class, which manages the rolling timelines for each guild and user."""

import discord
import time
import asyncio

from collections import defaultdict, deque

from models import Guild, ReactionEvent, LogEvent
from logging_aura import LoggingManager


class TimelinesManager:
    def __init__(
        self,
        client: discord.Client,
        guilds: dict[int, Guild],
        logging_manager: LoggingManager,
    ):
        self.client = client
        self.guilds = guilds
        self.logging_manager = logging_manager
        self.rolling_add = defaultdict(deque)
        self.rolling_remove = defaultdict(deque)
        self.temp_banned_users = defaultdict(list)

    async def update_rolling_timelines(
        self, guild_id: int, user_id: int, event: ReactionEvent
    ) -> None:
        """Update the rolling timelines for a guild-user pair based on the reaction event.

        Used to check for spamming reactions and apply temporary bans.

        Checks both a short and long interval.

        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user giving or removing the reaction.
        event: `ReactionEvent`
            The event type that triggered the reaction."""
        current_time = time.time()

        if event.is_add:
            rolling = (
                self.rolling_add
            )  # uses mutability of dict. rolling is just a pointer
        else:
            rolling = self.rolling_remove

        rolling[(guild_id, user_id)].append(current_time)

        # remove expired timestamps from the deque
        while (
            rolling[(guild_id, user_id)]
            and rolling[(guild_id, user_id)][0]
            < current_time - self.guilds[guild_id].limits.interval_long
        ):
            rolling[(guild_id, user_id)].popleft()

        # long interval check
        if (
            len(rolling[(guild_id, user_id)])
            > self.guilds[guild_id].limits.threshold_long
        ):
            await self.handle_spam(guild_id, user_id)
            return

        # short interval check
        short_rolling = [
            1
            for t in rolling[(guild_id, user_id)]
            if t >= current_time - self.guilds[guild_id].limits.interval_short
        ]
        if sum(short_rolling) > self.guilds[guild_id].limits.threshold_short:
            await self.handle_spam(guild_id, user_id)
            return

    async def handle_spam(self, guild_id: int, user_id: int) -> None:
        """Handle spamming reactions by temporarily banning a user from giving aura.

        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user to tempban."""
        self.temp_banned_users[guild_id].append(user_id)
        await (await self.client.fetch_user(user_id)).send(
            f"<@{user_id}\nYou have been temporarily banned for {self.guilds[guild_id].limits.penalty} seconds from giving aura in {self.client.get_guild(guild_id).name} due to spamming reactions."
        )
        print(f"Fetched user {user_id}. Reason: Temp ban direct message.")
        if self.guilds[guild_id].log_channel_id is not None:
            self.logging_manager.log_event(
                guild_id, user_id, user_id, LogEvent.SPAMMING
            )

        # start a timer to allow the user to give aura again after LIMIT_PENALTY seconds
        await asyncio.sleep(self.guilds[guild_id].limits.penalty)
        self.temp_banned_users[guild_id].remove(user_id)
