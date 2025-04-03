'''Contains the CooldownManager class, which manages the cooldowns for reactions across all guilds.'''

import time

from collections import defaultdict
from models import *

class CooldownManager:
    '''Class that manages the cooldowns for reactions across all guilds.
    
    This class is responsible for tracking the cooldowns for adding and removing reactions, ensuring that users cannot spam reactions within the specified cooldown periods.
    
    Parameters
    ----------
    guilds: `dict[int, Guild]`
        A dictionary mapping guild IDs to their respective Guild objects.
    '''
    def __init__(self, guilds: dict[int, Guild]) -> None:
        '''Initialize the CooldownManager with specified cooldowns.'''
        self._cooldowns: defaultdict[tuple[int], UserCooldowns] = defaultdict(dict)
        self._adding_cooldowns: dict[int, int] = {}
        self._removing_cooldowns: dict[int, int] = {}

        for guild_id, guild in guilds.items():
            self._adding_cooldowns[guild_id] = guild.limits.adding_cooldown
            self._removing_cooldowns[guild_id] = guild.limits.removing_cooldown

    def edit_guild_cooldown_values(self, guild_id: int, adding_cooldown: int, removing_cooldown: int) -> None:
        '''Edit the cooldown values for adding and removing reactions.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        adding_cooldown: `int`
            The new cooldown for adding reactions.
        removing_cooldown: `int`
            The new cooldown for removing reactions.'''
        self._adding_cooldowns[guild_id] = adding_cooldown
        self._removing_cooldowns[guild_id] = removing_cooldown

    def ensure_cooldown(self, guild_id: int, user_id: int, author_id: int) -> None:
        '''Ensure a cooldown object exists for a guild-user-author group.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user giving or removing the reaction.
        author_id: `int`
            The ID of the user receiving the reaction.'''
        if (guild_id, user_id, author_id) not in self._cooldowns:
            self._cooldowns[(guild_id, user_id, author_id)] = UserCooldowns()

    def start_cooldown(self, guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> None:
        '''Start the event cooldown for a guild-user-author.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user giving or removing the reaction.
        author_id: `int`
            The ID of the user receiving the reaction.
        event: `ReactionEvent`
            The event type that triggered the cooldown.'''
        self.ensure_cooldown(guild_id, user_id, author_id)
        if event.is_add:
            self._cooldowns[(guild_id, user_id, author_id)].add_cooldown_began = int(time.time())
        else:
            self._cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began = int(time.time())

    def end_cooldown(self, guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> None:
        '''End the event cooldown early for a guild-user-author.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user giving or removing the reaction.
        author_id: `int`
            The ID of the user receiving the reaction.
        event: `ReactionEvent`
            The event type that triggered the cooldown.'''
        self.ensure_cooldown(guild_id, user_id, author_id)
        if event.is_add:
            self._cooldowns[(guild_id, user_id, author_id)].add_cooldown_began = 0
        else:
            self._cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began = 0

    def is_cooldown_complete(self, guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> bool:
        '''Check if the event cooldown is complete for a guild-user-author.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user giving or removing the reaction.
        author_id: `int`
            The ID of the user receiving the reaction.
        event: `ReactionEvent`
            The event type that triggered the cooldown.'''
        self.ensure_cooldown(guild_id, user_id, author_id)
        # does not need to set it back to 0 because if the user isnt on cooldown anymore it makes no difference when checking: will still be true either way.
        if event.is_add:
            return int(time.time()) - self._cooldowns[(guild_id, user_id, author_id)].add_cooldown_began >= self._adding_cooldowns[guild_id]
        else:
            return int(time.time()) - self._cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began >= self._removing_cooldowns[guild_id]
