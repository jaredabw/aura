'''Contains the TasksManager class, which handles the periodic tasks for the bot.'''

import discord
import time
import datetime
import sqlite3

from discord.ext import tasks

from models import Guild
from funcs import Functions
from config import UPDATE_INTERVAL, DB

class TasksManager:
    def __init__(self, client: discord.Client, guilds: dict[int, Guild], funcs: Functions):
        '''Initialise the TasksManager with the Discord client and guilds.

        Parameters
        ----------
        client: `discord.Client`
            The Discord client instance.
        guilds: `dict[int, Guild]`
            A dictionary of guilds, where the key is the guild ID and the value is a `Guild` object.'''
        self.client = client
        self.guilds = guilds
        self.funcs = funcs

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def update_leaderboards(self, skip=False):
        '''Update the leaderboard and emoji list for all guilds.

        Runs every `UPDATE_INTERVAL` seconds.
        
        Parameters
        ----------
        skip: `bool`, optional
            Whether to ignore the update interval and force an update. Defaults to `False`. Is True when the bot is first started.'''
        for guild_id in self.guilds:
            guild = self.guilds[guild_id]
            if skip or int(time.time()) - guild.last_update < UPDATE_INTERVAL + 10:
                if guild.msgs_channel_id is not None:
                    channel = self.client.get_channel(guild.msgs_channel_id)
                    if channel is not None:
                        try:
                            board_msg = await channel.fetch_message(guild.board_msg_id)
                            await board_msg.edit(embed=self.funcs.get_leaderboard(guild_id, "all", True))
                        except discord.NotFound:
                            pass
                        except discord.Forbidden:
                            print(f"Forbidden to send leaderboard to channel {guild.msgs_channel_id} in guild {guild_id}.")

    @tasks.loop(time=[datetime.time(hour=0, minute=0), datetime.time(hour=12, minute=0)])
    async def take_snapshots_and_cleanup():
        now = datetime.datetime.now()

        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO user_snapshots (
                guild_id, user_id, aura, aura_contribution, 
                num_pos_given, num_pos_received, num_neg_given, num_neg_received
            )
            SELECT 
                guild_id, user_id, aura, aura_contribution, 
                num_pos_given, num_pos_received, num_neg_given, num_neg_received
            FROM users
        ''')

        cursor.execute('''
            DELETE FROM user_snapshots 
            WHERE snapshot_time < DATETIME('now', '-30 days')
        ''')

        conn.commit()
        conn.close()

        print(f"Snapshots taken and old data cleaned up at {now.strftime('%Y-%m-%d %H:%M:%S')}")
