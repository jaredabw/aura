'''Aura Bot Functions Module
This module contains the Functions class, which provides various utility functions for the Aura Bot.'''

import discord
import datetime
import sqlite3

from config import UPDATE_INTERVAL, DB
from models import *

class Functions:
    def __init__(self, client: discord.Client, guilds: dict[int, Guild]):
        '''Initialise the Functions class with the Discord client and guilds.

        Parameters
        ----------
        client: `discord.Client`
            The Discord client instance.
        guilds: `dict[int, Guild]`
            A dictionary of guilds, where the key is the guild ID and the value is a `Guild` object.'''

        self.client = client
        self.guilds = guilds

    # need to add pagination/multiple embeds
    def get_leaderboard(self, guild_id: int, timeframe: str, persistent=False) -> discord.Embed:
        '''Get the leaderboard for a guild.
        
        Returns an embed with the leaderboard information.

        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        timeframe: `str`
            The time period for the leaderboard ("all", "week", or "month").
        persistent: `bool`, optional
            Whether the leaderboard is persistent and should be edited in the future or not. Defaults to `False`.
                
        Returns
        -------
        `discord.Embed`
            The embed containing the leaderboard information.'''
        
        # half this code was ai generated ngl

        embed = discord.Embed(color=0x74327a)

        if persistent:
            mins = UPDATE_INTERVAL // 60
            secs = UPDATE_INTERVAL % 60
            if mins > 0:
                embed.set_footer(text=f"Updates every {mins}m{' ' if secs > 0 else ''}{secs}{'s' if secs > 0 else ''}.")
            else:
                embed.set_footer(text=f"Updates every {secs}s.")

        embed.description = ""
        # suffix = " (Week Change)" if timeframe == "week" else " (Month Change)" if timeframe == "month" else ""
        suffix = " (Day Change)" if timeframe == "day" else " (Week Change)" if timeframe == "week" else " (Month Change)" if timeframe == "month" else ""
        embed.set_author(name=f"🏆 {self.client.get_guild(guild_id).name} Aura Leaderboard{suffix}")

        now = datetime.datetime.now()

        if timeframe == "all":
            leaderboard = sorted(self.guilds[guild_id].users.items(), key=lambda item: item[1].aura, reverse=True)
            leaderboard = [(user_id, user.aura) for user_id, user in leaderboard if user.opted_in]

        elif timeframe in ["day", "week", "month"]:
            conn = sqlite3.connect(DB)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if timeframe == "week":
                start_of_period = now - datetime.timedelta(days=7)
            elif timeframe == "month":
                start_of_period = now - datetime.timedelta(days=30)
            else:
                start_of_period = now - datetime.timedelta(days=1)

            cursor.execute('''
                SELECT user_id, aura, snapshot_time
                FROM user_snapshots
                WHERE guild_id = ? AND snapshot_time <= ?
                ORDER BY snapshot_time DESC
            ''', (guild_id, start_of_period))

            leaderboard_data = cursor.fetchall()

            latest_snapshots = {}

            # Loop through the leaderboard data and keep the latest snapshot per user
            for row in leaderboard_data:
                user_id = row['user_id']
                snapshot_time = row['snapshot_time']

                # Check if this user has been added to the dictionary or if this snapshot is later
                if user_id not in latest_snapshots or snapshot_time > latest_snapshots[user_id]['snapshot_time']:
                    latest_snapshots[user_id] = row

            # Now, latest_snapshots contains only the latest snapshot for each user
            leaderboard = [(snapshot['user_id'], snapshot['aura']) for snapshot in latest_snapshots.values()]

            if len(leaderboard_data) == 0:
                # fall back to current leaderboard
                leaderboard = sorted(self.guilds[guild_id].users.items(), key=lambda item: item[1].aura, reverse=True)
                leaderboard = [(user_id, user.aura) for user_id, user in leaderboard if user.opted_in]
            else:
                # else calculate the diff
                leaderboard = []

                current_data = {user_id: user.aura for user_id, user in self.guilds[guild_id].users.items()}

                for snapshot in leaderboard_data:
                    user_id = snapshot['user_id']
                    past_aura = snapshot['aura']
                    current_aura = current_data.get(user_id, 0)  # Default to 0 if no current data
                    gain = current_aura - past_aura

                    if self.guilds[guild_id].users.get(user_id, {}).opted_in:
                        leaderboard.append((user_id, gain))

                leaderboard.sort(key=lambda item: item[1], reverse=True)

        if len(leaderboard) == 0:
            embed.description = "No leaderboard data available."
        else:
            iconurl = self.client.get_user(leaderboard[0][0]).avatar.url if len(leaderboard) > 0 else None
            embed.set_thumbnail(url=iconurl)

            for i, (user_id, gain) in enumerate(leaderboard):
                embed.description += f"{i+1}. **{gain}** | <@{user_id}>\n"

        return embed

    # need to add pagination/multiple embeds
    def get_emoji_list(self, guild_id: int, persistent=False) -> discord.Embed:
        '''Get the emoji list for a guild.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        persistent: `bool`, optional
            Whether the emoji list is persistent and should be edited in the future or not. Defaults to `False`.
            
        Returns
        -------
        `discord.Embed`
            The embed containing the emoji list information.'''

        embed = discord.Embed(color=0x74327a)
        if persistent:
            embed.set_footer(text=f"Updates immediately.")
        embed.set_author(name=f"🔧 {self.client.get_guild(guild_id).name} Emoji List")

        emojis = sorted(self.guilds[guild_id].reactions.items(), key=lambda item: abs(item[1].points), reverse=True)

        positive_reactions = [f"{emoji} **+{reaction.points}**" for emoji, reaction in emojis if reaction.points > 0]
        negative_reactions = [f"{emoji} **{reaction.points}**" for emoji, reaction in emojis if reaction.points < 0]

        if positive_reactions:
            embed.add_field(name="**+**", value="\n".join(positive_reactions))
        else:
            embed.add_field(name="**+**", value="*(empty)*")

        if negative_reactions:
            embed.add_field(name="**-**", value="\n".join(negative_reactions))
        else:
            embed.add_field(name="**-**", value="*(empty)*")

        # Add guild icon as thumbnail
        iconurl = self.client.get_guild(guild_id).icon.url if self.client.get_guild(guild_id).icon else None
        embed.set_thumbnail(url=iconurl)

        return embed

    def get_aura_tagline(self, aura: int):
        '''Get the aura tagline for a given aura value.
        
        Parameters
        ----------
        aura: `int`
            The aura value to get the tagline for.
            
        Returns
        -------
        `str`
            The tagline for the given aura value.'''
        aura_ranges = [
            (-float('inf'), -30, "Actually cooked."),
            (-30, -20, "Forgot to mute their mic."),
            (-20, -10, "Overshared after first date."),
            (-10, 0, "Got up with their backpack open"),
            (0, 10, "Novice aura farmer."),
            (10, 20, "Autographed their own paper for Will Smith."),
            (20, 30, "Could probably pull a goth girl GF."),
            (30, 40, "Got that drip."),
            (40, 50, "W collector."),
            (50, 60, "Mogging everyone else"),
            (60, 70, "The huzz calls him pookie."),
            (70, 80, "Radiates protagonist energy."),
            (80, 90, "Literally goated."),
            (90, 100, "Figured out how to actually mew."),
            (100, 110, "Almost maxed out."),
            (110, float('inf'), "Won at life.")
        ]
        
        for lower, upper, tag in aura_ranges:
            if lower <= aura < upper:
                return tag

    def get_user_aura(self, guild_id: int, user_id: int) -> discord.Embed:
        '''Get the aura breakdown for a user.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.
        user_id: `int`
            The ID of the user.
            
        Returns
        -------
        `discord.Embed`
            The embed containing the user's aura breakdown information.'''
        embed = discord.Embed(color=0xb57f94)
        if guild_id not in self.guilds:
            return embed
        if user_id not in self.guilds[guild_id].users:
            return embed
        embed.set_author(name=f"Aura Breakdown")
        embed.set_thumbnail(url=self.client.get_user(user_id).avatar.url)

        user = self.guilds[guild_id].users[user_id]

        tag = self.get_aura_tagline(user.aura)

        if user.opted_in:
            embed.description = f"<@{user_id}> has **{user.aura}** aura.\n"
            embed.description += f"*{tag}*\n\n"
            embed.description += f"**{user.aura_contribution}** net aura contribution.\n\n"
            embed.description += f"**{user.num_pos_given}** positive reactions given.\n"
            embed.description += f"**{user.num_pos_received}** positive reactions received.\n"
            embed.description += f"**{user.num_neg_given}** negative reactions given.\n"
            embed.description += f"**{user.num_neg_received}** negative reactions received.\n"
        else:
            embed.description = f"<@{user_id}> is opted out of aura tracking."

        give = "Allowed" if user.giving_allowed else "NOT allowed"
        receive = "Allowed" if user.receiving_allowed else "NOT allowed"
        embed.set_footer(text=f"{give} to give aura. {receive} to receive aura.")

        return embed

    async def update_info(self, guild_id: int):
        '''Update the emoji list for a guild.
        
        Parameters
        ----------
        guild_id: `int`
            The ID of the guild.'''
        guild = self.guilds[guild_id]
        if guild.msgs_channel_id is not None:
            channel = self.client.get_channel(guild.msgs_channel_id)
            if channel is not None:
                try:
                    info_msg = channel.get_partial_message(guild.info_msg_id)
                    await info_msg.edit(embed=self.get_emoji_list(guild_id, True))
                except discord.DiscordException:
                    pass
                except AttributeError:
                    pass

    async def check_user_permissions(self, interaction: discord.Interaction, required_permission: str):
        '''Check if the user has the required permissions to run a command.
        
        Parameters
        ----------
        interaction: `discord.Interaction`
            The interaction object that began this request.
        required_permission: `str`
            The permission to check for. Should be a string of the form "manage_channels", "administrator", etc.'''
        if interaction.guild is None:
            await interaction.response.send_message(
                "This command cannot be used in DMs. Please run it in a server.",
                ephemeral=True
            )
            return False

        user_permissions = interaction.channel.permissions_for(interaction.user)
        if not getattr(user_permissions, required_permission, False):
            await interaction.response.send_message(
                f"You are missing {' '.join(word.capitalize() for word in required_permission.split('_'))} permissions to run this command.", 
                ephemeral=True
            )
            return False

        return True
