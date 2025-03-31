import discord
import json
import time
import os
import emoji as emojilib
from discord import app_commands
from discord.ext import tasks
from dataclasses import dataclass, field
from typing import Dict
from dotenv import load_dotenv
from collections import defaultdict

# TODO: add pagination to leaderboard and emoji list
# TODO: aura based role rewards
# TODO: check a given users aura
# TODO: manual aura changes by admins
# TODO: reset tracking emojis without deleting the leaderboard
# TODO: reset leaderboard without deleting the emojis
# TODO: customisable leaderboard: top all time / top this week / top this month
# TODO: multi lang support
# TODO: opt in/out
# TODO: emoji usage stats

load_dotenv("token.env")
TOKEN = os.getenv("TOKEN")

# in seconds
UPDATE_INTERVAL = 10 # how often to update the leaderboard
LOGGING_INTERVAL = 10 # how often to send logs
ADDING_COOLDOWN = 10 # how long to wait before allowing a user to give a new reaction

@dataclass
class User:
    aura: int = 0
    lastadded: int = 0

@dataclass
class EmojiReaction:
    points: int = 0

@dataclass
class Guild:
    users: Dict[int, User] = field(default_factory=dict)
    reactions: Dict[str, EmojiReaction] = field(default_factory=dict)
    info_msg_id: int = None
    board_msg_id: int = None
    msgs_channel_id: int = None
    log_channel_id: int = None
    last_update: int = None

def load_data(filename="data.json"):
    try:
        with open(filename, "r") as file:
            raw_data: dict[str, dict[int, dict]] = json.load(file)
            guilds: dict[int, Guild] = {}
            for guild_id, guild in raw_data.get("guilds", {}).items():
                users = {int(user_id): User(aura=data["aura"], lastadded=data["lastadded"]) for user_id, data in guild.get("users", {}).items()}
                reactions = {emoji: EmojiReaction(points=data["points"]) for emoji, data in guild.get("reactions", {}).items()}
                guilds[int(guild_id)] = Guild(
                    users=users,
                    reactions=reactions,
                    info_msg_id=guild.get("info_msg_id", None),
                    board_msg_id=guild.get("board_msg_id", None),
                    msgs_channel_id=guild.get("msgs_channel_id", None),
                    log_channel_id=guild.get("log_channel_id", None),
                    last_update=guild.get("last_update", None)
                )

        return guilds
    except (FileNotFoundError, json.JSONDecodeError):
        with open(filename, "w") as file:
            json.dump({"guilds": {}}, file, indent=4)
        print("No data found, created a new data file.")
        return {}

def save_data(guilds: Dict[int, Guild], filename="data.json"):
    # Convert the guilds data back to a dict to save in JSON
    save_data = {"guilds": {}}

    for guild_id, guild in guilds.items():
        guild_data = {
            "users": {},
            "reactions": {},
            "info_msg_id": guild.info_msg_id,
            "board_msg_id": guild.board_msg_id,
            "msgs_channel_id": guild.msgs_channel_id,
            "log_channel_id": guild.log_channel_id,
            "last_update": guild.last_update
        }

        for user_id, user in guild.users.items():
            guild_data["users"][str(user_id)] = {"aura": user.aura, "lastadded": user.lastadded}
        
        for emoji, reaction in guild.reactions.items():
            guild_data["reactions"][emoji] = {"points": reaction.points}

        save_data["guilds"][guild_id] = guild_data
    #

    with open(filename, "w") as file:
        json.dump(save_data, file, indent=4)

def update_time_and_save(guild_id, guilds: Dict[int, Guild]):
    guilds[guild_id].last_update = int(time.time())
    save_data(guilds)

intents = discord.Intents.default()
intents.members = True

client = discord.Client(intents=intents)

tree = app_commands.CommandTree(client)
emoji_group = app_commands.Group(name="emoji", description="Commands for managing emojis.")
tree.add_command(emoji_group)

guilds = load_data()
log_cache = defaultdict(list)

@client.event
async def on_ready():
    await tree.sync()

    await client.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="for aura changes"))
    if not update_leaderboards.is_running():
        print("Starting leaderboard update loop...")
        await update_leaderboards()
        update_leaderboards.start()
    if not send_batched_logs.is_running():
        print("Starting logging loop...")
        await send_batched_logs()
        send_batched_logs.start()

    print(f"Logged in as {client.user}")

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await parse_payload(payload, adding=True)

@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    payload.message_author_id = (await client.get_channel(payload.channel_id).fetch_message(payload.message_id)).author.id
    # message_author_id is not in the payload on removal, so we need to fetch the message to get it
    await parse_payload(payload, adding=False)

async def parse_payload(payload: discord.RawReactionActionEvent, adding: bool) -> None:
    if payload.guild_id in guilds and payload.user_id != payload.message_author_id and not client.get_user(payload.message_author_id).bot:
        emoji = str(payload.emoji)
        guild_id = payload.guild_id
        author_id = payload.message_author_id
        user_id = payload.user_id
        if emoji in guilds[guild_id].reactions:
            if author_id not in guilds[guild_id].users:
                # recipient must be created
                guilds[guild_id].users[author_id] = User()
            if user_id not in guilds[guild_id].users:
                # giver must be created
                guilds[guild_id].users[payload.user_id] = User()

            # users can receive as many reactions as they get, but the user giving the reaction has a cooldown
            if adding and int(time.time()) - guilds[guild_id].users[user_id].lastadded < ADDING_COOLDOWN:
                # if the user is trying to add a reaction too fast, ignore it
                return
            else:
                # update the last added time for the user who is giving the reaction
                guilds[guild_id].users[user_id].lastadded = int(time.time())

            if adding:
                guilds[guild_id].users[author_id].aura += guilds[guild_id].reactions[emoji].points
            else:
                guilds[guild_id].users[author_id].aura -= guilds[guild_id].reactions[emoji].points
            if guilds[guild_id].log_channel_id is not None:
                await log_aura_change(guild_id, author_id, user_id, emoji, guilds[guild_id].reactions[emoji].points, adding, f"https://discord.com/channels/{guild_id}/{payload.channel_id}/{payload.message_id}")
            update_time_and_save(guild_id, guilds)

async def log_aura_change(guild_id: int, author_id: int, user_id: int, emoji: str, points: int, adding: bool, url: str) -> None:
    # i want to batch the messages to avoid spamming the channel
    action = "added" if adding else "removed"

    if points > 0 and adding:
        sign = "+"
    elif points > 0 and not adding:
        sign = "-"
    elif points < 0 and adding:
        sign = "-"
    elif points < 0 and not adding:
        sign = "+"
    else:
        sign = "error"
    points = abs(points)
    log_message = f"<@{user_id}> [{action}]({url}) {emoji} {'to' if adding else 'from'} <@{author_id}> ({sign}{points} points)"

    log_cache[guild_id].append(log_message)

@tasks.loop(seconds=LOGGING_INTERVAL)
async def send_batched_logs():
    for guild_id, logs in list(log_cache.items()):
        if logs:
            channel_id = guilds[guild_id].log_channel_id
            if channel_id is not None:
                channel = client.get_channel(channel_id)
                if channel is not None:
                    try:
                        await channel.send(
                            "\n".join(logs),
                            allowed_mentions=discord.AllowedMentions(users=False)
                        )
                    except discord.Forbidden:
                        print(f"Failed to send logs to channel {channel_id} in guild {guild_id}.")
                    except discord.HTTPException as e:
                        print(f"Failed to send logs: HTTPException: {e}")

            log_cache[guild_id].clear()

# need to add pagination/multiple embeds
def get_leaderboard(guild_id: int, persistent=False) -> discord.Embed:
    embed = discord.Embed(color=0x74327a)
    if persistent:
        mins = UPDATE_INTERVAL // 60
        secs = UPDATE_INTERVAL % 60
        if mins > 0:
            embed.set_footer(text=f"Updates every {mins}m{' ' if secs > 0 else ''}{secs}{'s' if secs > 0 else ''}.")
        else:
            embed.set_footer(text=f"Updates every {secs}s.")
    embed.description = ""

    embed.set_author(name=f"🏆 {client.get_guild(guild_id).name} Aura Leaderboard")

    leaderboard = sorted(guilds[guild_id].users.items(), key=lambda item: item[1].aura, reverse=True)

    iconurl = client.get_user(leaderboard[0][0]).avatar.url if (len(leaderboard) > 0 and client.get_user(leaderboard[0][0]) is not None) else None
    embed.set_thumbnail(url=iconurl)

    for i, (user_id, user) in enumerate(leaderboard):
        member = client.get_user(user_id)
        if member is not None:
            embed.description += f"{i+1}. **{user.aura}** | {member.name}\n"
        else:
            embed.description += f"{i+1}. **{user.aura}** | {user_id}\n"
    return embed

# need to add pagination/multiple embeds
def get_emoji_list(guild_id: int, persistent=False) -> discord.Embed:
    embed = discord.Embed(color=0x74327a)
    if persistent:
        embed.set_footer(text=f"Updates immediately.")
    embed.set_author(name=f"🔧 {client.get_guild(guild_id).name} Emoji List")

    emojis = sorted(guilds[guild_id].reactions.items(), key=lambda item: abs(item[1].points), reverse=True)

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
    iconurl = client.get_guild(guild_id).icon.url if client.get_guild(guild_id).icon else None
    embed.set_thumbnail(url=iconurl)

    return embed

@tasks.loop(seconds=UPDATE_INTERVAL)
async def update_leaderboards():
    for guild_id in guilds:
        guild = guilds[guild_id]
        if int(time.time()) - guild.last_update < UPDATE_INTERVAL + 10: # if the last update was less than LIMIT seconds ago. ie: if there is new data to display
            if guild.msgs_channel_id is not None:
                channel = client.get_channel(guild.msgs_channel_id)
                if channel is not None:
                    try:
                        board_msg = await channel.fetch_message(guild.board_msg_id)
                        await board_msg.edit(embed=get_leaderboard(guild_id, True))
                    except discord.NotFound:
                        pass

async def update_info(guild_id: int):
    guild = guilds[guild_id]
    if guild.msgs_channel_id is not None:
        channel = client.get_channel(guild.msgs_channel_id)
        if channel is not None:
            try:
                info_msg = await channel.fetch_message(guild.info_msg_id)
                await info_msg.edit(embed=get_emoji_list(guild_id, True))
            except Exception:
                pass

@tree.command(name="setup", description="Setup the bot. (Optional) Displays the leaderboard in the given channel.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(channel="The channel to display the leaderboard in.")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild.id
    if guild_id in guilds:
        await interaction.response.send_message("Bot is already set up in this server.")
        return

    try:
        guilds[guild_id] = Guild()
        guilds[guild_id].last_update = int(time.time())
        guilds[guild_id].reactions = {
            "🔥": EmojiReaction(points=1),
            "💀": EmojiReaction(points=-1)
        }

        if channel is not None:
            guilds[guild_id].msgs_channel_id = channel.id
            guilds[guild_id].info_msg_id = (await channel.send(embed=get_emoji_list(guild_id, True))).id
            guilds[guild_id].board_msg_id = (await channel.send(embed=get_leaderboard(guild_id, True))).id

            update_time_and_save(guild_id, guilds)
            await interaction.response.send_message(f"Setup complete. Leaderboard will be displayed in {channel.mention} or run </leaderboard:1356179831288758387>. Next, add emojis to track using </emoji add:1356180634602700863> or remove the default emojis with </emoji remove:1356180634602700863>.")
            return
        else:
            await interaction.response.send_message(f"Setup complete. Run </leaderboard:1356179831288758387> to display leaderboard and </emoji list:1356180634602700863> to see tracked emojis. Next, add emojis to track using </emoji add:1356180634602700863>.")
            return
    except discord.Forbidden:
        await interaction.response.send_message("I don't have permission to send messages in that channel. Please choose a different channel or update my permissions.")
        return

@tree.command(name="updatechannel", description="Update or add the channel to display the leaderboard in. (Also resends the leaderboard)")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(channel="The channel to display the leaderboard in.")
async def update_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    guilds[guild_id].msgs_channel_id = channel.id
    guilds[guild_id].info_msg_id = (await channel.send(embed=get_emoji_list(guild_id, True))).id
    guilds[guild_id].board_msg_id = (await channel.send(embed=get_leaderboard(guild_id, True))).id

    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(f"Channel updated. Leaderboard will be displayed in {channel.mention}.")

@tree.command(name="delete", description="Delete the Aura bot data for this server.")
@app_commands.checks.has_permissions(manage_channels=True)
async def delete(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    await (client.get_user(355938178265251842)).send(f"Guild {guild_id} data was deleted. Data as follows:\n\n```{json.dumps({str(guild_id): guilds[guild_id]}, default=lambda o: o.__dict__, indent=4)}```")
    del guilds[guild_id]

    save_data(guilds)
    await interaction.response.send_message("Data deleted. If this was a mistake, contact `@engiw` to restore data.")

@tree.command(name="leaderboard", description="Show the leaderboard at this moment.")
async def leaderboard(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    await interaction.response.send_message(embed=get_leaderboard(guild_id))

@tree.command(name="logging", description="Enable or disable logging of aura changes.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(channel="The channel to log aura changes in. Leave empty to disable logging.")
async def logging(interaction: discord.Interaction, channel: discord.TextChannel = None):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    if channel is not None:
        try:
            await channel.send("Aura logging enabled.")
            guilds[guild_id].log_channel_id = channel.id
            await interaction.response.send_message(f"Logging enabled in {channel.mention}. Logs will be sent every 10 seconds.")
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to send messages in that channel. Please choose a different channel or update my permissions.")
    else:
        guilds[guild_id].log_channel_id = None
        await interaction.response.send_message("Logging disabled.")

@emoji_group.command(name="add", description="Add an emoji to tracking.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to start tracking.", points="The points impact for the emoji. Positive or negative.")
async def add_emoji(interaction: discord.Interaction, emoji: str, points: int):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if emoji in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is already being tracked. Use </emoji update:1356180634602700863> to update its points or </emoji remove:1356180634602700863> to remove it.")
        return
    
    if points == 0:
        await interaction.response.send_message("Points cannot be 0. Please use a positive or negative number.")
        return

    try:
        if emojilib.is_emoji(emoji) or discord.utils.get(interaction.guild.emojis, id=int(emoji.split(":")[2][:-1])):
            guilds[guild_id].reactions[emoji] = EmojiReaction(points=points)
            update_time_and_save(guild_id, guilds)
            await update_info(guild_id)
            await interaction.response.send_message(f"Emoji {emoji} added: worth {'+' if points > 0 else ''}{points} points.")
        else:
            await interaction.response.send_message("This emoji is not from this server, or is not a valid emoji.")
            return
    except IndexError:
        await interaction.response.send_message("This is not a valid emoji.")
        return

@emoji_group.command(name="remove", description="Remove an emoji from tracking.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to stop tracking.")
async def remove_emoji(interaction: discord.Interaction, emoji: str):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is already not being tracked.")
        return
    
    del guilds[guild_id].reactions[emoji]
    update_time_and_save(guild_id, guilds)
    await update_info(guild_id)
    await interaction.response.send_message(f"Emoji {emoji} removed from tracking.")

@emoji_group.command(name="update", description="Update the points of an emoji.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to update.", points="The new points impact for the emoji. Positive or negative.")
async def update_emoji(interaction: discord.Interaction, emoji: str, points: int):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is not being tracked yet. Use </emoji add:1356180634602700863> to add it.")
        return
    
    if points == 0:
        await interaction.response.send_message("Points cannot be 0. Please use a positive or negative number.")
        return

    guilds[guild_id].reactions[emoji].points = points
    update_time_and_save(guild_id, guilds)
    await update_info(guild_id)
    await interaction.response.send_message(f"Emoji {emoji} updated: worth {points} points.")

@emoji_group.command(name="list", description="List the emojis being tracked in this server.")
async def list_emoji(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    await interaction.response.send_message(embed=get_emoji_list(guild_id))

client.run(TOKEN)