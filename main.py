import asyncio
import discord
import json
import time
import os
from discord import app_commands
from discord.ext import tasks
from dataclasses import dataclass, field
from typing import Dict, Literal, Callable, Any
from dotenv import load_dotenv
from emoji import is_emoji
from collections import defaultdict, deque
from enum import Enum

# TODO: fix command permissions 

# TODO: penalise and forgive: if penalised, gain half and lose double
# TODO: implement increasing cooldown if spamming? idk how to do this. probably hard

# TODO: emoji usage stats

# TODO: reset tracking emojis without deleting the leaderboard
# TODO: reset leaderboard without deleting the emojis

# TODO: add pagination to leaderboard and emoji list
# TODO: aura based role rewards
# TODO: customisable leaderboard: top all time / top this week / top this month
# TODO: multi lang support

load_dotenv("token.env")
TOKEN = os.getenv("TOKEN")

# in seconds
UPDATE_INTERVAL = 10 # how often to update the leaderboard
LOGGING_INTERVAL = 10 # how often to send logs

# make constants below configurable in the future
# user can send LIMIT_THRESHOLD and LIMIT_THRESHOLD_SHORT reaction events in the last LIMIT_INTERVAL and LIMIT_INTERVAL_SHORT seconds respectively before being tempbanned for LIMIT_PENALTY seconds
LIMIT_INTERVAL = 60
LIMIT_THRESHOLD = 20
LIMIT_INTERVAL_SHORT = 10
LIMIT_THRESHOLD_SHORT = 10
LIMIT_PENALTY = 300

ADDING_COOLDOWN = 10 # how long to wait before allowing a user to add a new reaction and give aura
REMOVING_COOLDOWN = ADDING_COOLDOWN # how long to wait before allowing a user to remove a reaction and restore aura

with open("help.txt", "r", encoding="utf-8") as help_file:
    HELP_TEXT = help_file.read()

class ReactionEvent(Enum):
    ADD = ("add", "adding", "added", True)
    REMOVE = ("remove", "removing", "removed", False)

    def __init__(self, base: str, present: str, past: str, is_add: bool):
        self.base = base
        self.present = present
        self.past = past
        self.is_add = is_add

    def __bool__(self):
        return self.is_add

class LogEvent(Enum):
    MANUAL = "manual"
    SPAMMING = "spamming"
    DENY_GIVING = "giving"
    DENY_RECEIVING = "receiving"
    DENY_BOTH = "giving and receiving"
    ALLOW_GIVING = "give"
    ALLOW_RECEIVING = "receive"
    ALLOW_BOTH = "give and receive"

    def __str__(self):
        return self.value

@dataclass
class User:
    aura: int = 0
    aura_contribution: int = 0
    num_pos_given: int = 0
    num_pos_received: int = 0
    num_neg_given: int = 0
    num_neg_received: int = 0
    opted_in: bool = True
    giving_allowed: bool = True
    receiving_allowed: bool = True

@dataclass
class UserCooldowns:
    add_cooldown_began: int = 0
    remove_cooldown_began: int = 0

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
                users = {
                    int(user_id): User(
                        aura=data["aura"],
                        aura_contribution=data["aura_contribution"],
                        num_pos_given=data["num_pos_given"],
                        num_pos_received=data["num_pos_received"],
                        num_neg_given=data["num_neg_given"],
                        num_neg_received=data["num_neg_received"],
                        opted_in=data["opted_in"],
                        giving_allowed=data["giving_allowed"],
                        receiving_allowed=data["receiving_allowed"]
                    ) for user_id, data in guild.get("users", {}).items()
                    }
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
            guild_data["users"][str(user_id)] = {
                "aura": user.aura,
                "aura_contribution": user.aura_contribution,
                "num_pos_given": user.num_pos_given,
                "num_pos_received": user.num_pos_received,
                "num_neg_given": user.num_neg_given,
                "num_neg_received": user.num_neg_received,
                "opted_in": user.opted_in,
                "giving_allowed": user.giving_allowed,
                "receiving_allowed": user.receiving_allowed
                }
        
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
intents.members = True # required for client.get_user() and client.fetch_message().author

client = discord.Client(intents=intents)

tree = app_commands.CommandTree(client)
emoji_group = app_commands.Group(name="emoji", description="Commands for managing emojis.", guild_only=True)
opt_group = app_commands.Group(name="opt", description="Commands for managing aura participation.", guild_only=True)
tree.add_command(emoji_group)
tree.add_command(opt_group)

guilds = load_data()
log_cache = defaultdict(list)
rolling_add: defaultdict[tuple, deque] = defaultdict(deque)
rolling_remove: defaultdict[tuple, deque] = defaultdict(deque)
temp_banned_users = defaultdict(list) # {guild_id: [user_id]}

@client.event
async def on_ready():
    await tree.sync()

    await client.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="for aura changes"))
    if not update_leaderboards.is_running():
        print("Starting leaderboard update loop...")
        await update_leaderboards(skip=True)
        update_leaderboards.start()
    if not send_batched_logs.is_running():
        print("Starting logging loop...")
        await send_batched_logs()
        send_batched_logs.start()

    print(f"Logged in as {client.user}")

cooldowns: dict[tuple[int], UserCooldowns] = defaultdict(dict)
# this lives in memory as it is not super important to be persistent
# if the bot restarted we have a bigger problem anyway

def ensure_cooldown(guild_id: int, user_id: int, author_id: int) -> None:
    '''Ensure a cooldown object exists for a cooldown tuple'''
    if (guild_id, user_id, author_id) not in cooldowns:
        cooldowns[(guild_id, user_id, author_id)] = UserCooldowns()

def start_cooldown(guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> None:
    '''Start the cooldown for a user'''
    ensure_cooldown(guild_id, user_id, author_id)
    if event.is_add:
        cooldowns[(guild_id, user_id, author_id)].add_cooldown_began = int(time.time())
    else:
        cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began = int(time.time())

def end_cooldown(guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> None:
    '''End the cooldown early for a user'''
    ensure_cooldown(guild_id, user_id, author_id)
    if event.is_add:
        cooldowns[(guild_id, user_id, author_id)].add_cooldown_began = 0
    else:
        cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began = 0

def is_cooldown_complete(guild_id: int, user_id: int, author_id: int, event: ReactionEvent) -> bool:
    '''Check if the cooldown is complete for a user'''
    ensure_cooldown(guild_id, user_id, author_id)
    # does not need to set it back to 0 because if the user isnt on cooldown anymore it makes no difference when checking: will still be true either way.
    if event.is_add:
        return int(time.time()) - cooldowns[(guild_id, user_id, author_id)].add_cooldown_began >= ADDING_COOLDOWN
    else:
        return int(time.time()) - cooldowns[(guild_id, user_id, author_id)].remove_cooldown_began >= REMOVING_COOLDOWN

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    await parse_payload(payload, ReactionEvent.ADD)

@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    payload.message_author_id = (await client.get_channel(payload.channel_id).fetch_message(payload.message_id)).author.id
    # message_author_id is not in the payload on removal, so we need to fetch the message to get it
    await parse_payload(payload, ReactionEvent.REMOVE)

async def parse_payload(payload: discord.RawReactionActionEvent, event: ReactionEvent) -> None:
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

            # check temp banned
            if user_id in temp_banned_users[guild_id]:
                return

            # check user restrictions
            if not guilds[guild_id].users[user_id].giving_allowed or not guilds[guild_id].users[author_id].receiving_allowed:
                return
            
            # check if the user is opted in
            if not guilds[guild_id].users[user_id].opted_in or not guilds[guild_id].users[author_id].opted_in:
                return

            await update_rolling_timelines(guild_id, user_id, event)

            # check if the user is on cooldown
            if not is_cooldown_complete(guild_id, user_id, author_id, event):
                return
            
            opposite_event = ReactionEvent.REMOVE if event.is_add else ReactionEvent.ADD
            # reset cooldowns and get vals for next step
            if event.is_add:
                start_cooldown(guild_id, user_id, author_id, event)
                end_cooldown(guild_id, user_id, author_id, opposite_event)

                points = guilds[guild_id].reactions[emoji].points
                one = 1
            else:
                start_cooldown(guild_id, user_id, author_id, event)
                end_cooldown(guild_id, user_id, author_id, opposite_event)

                points = -guilds[guild_id].reactions[emoji].points
                one = -1

            guilds[guild_id].users[author_id].aura += points
            guilds[guild_id].users[author_id].aura_contribution += points

            if guilds[guild_id].reactions[emoji].points > 0:
                guilds[guild_id].users[user_id].num_pos_given += one
                guilds[guild_id].users[author_id].num_pos_received += one
            else:
                guilds[guild_id].users[user_id].num_neg_given += one
                guilds[guild_id].users[author_id].num_neg_received += one

            if guilds[guild_id].log_channel_id is not None:
                log_aura_change(guild_id, author_id, user_id, event, emoji, points, f"https://discord.com/channels/{guild_id}/{payload.channel_id}/{payload.message_id}")

            update_time_and_save(guild_id, guilds)

async def update_rolling_timelines(guild_id: int, user_id: int, event: ReactionEvent) -> None:
    current_time = time.time()

    if event.is_add:
        rolling = rolling_add # uses mutability of dict. rolling is just a pointer
    else:
        rolling = rolling_remove

    rolling[(guild_id, user_id)].append(current_time)

    # remove expired timestamps from the deque
    while rolling[(guild_id, user_id)] and rolling[(guild_id, user_id)][0] < current_time - LIMIT_INTERVAL:
        rolling[(guild_id, user_id)].popleft()

    # long interval check
    if len(rolling[(guild_id, user_id)]) > LIMIT_THRESHOLD:
        await handle_spam(guild_id, user_id)
        return

    # short interval check
    short_rolling = [1 for t in rolling[(guild_id, user_id)] if t >= current_time - LIMIT_INTERVAL_SHORT]
    if sum(short_rolling) > LIMIT_THRESHOLD_SHORT:
        await handle_spam(guild_id, user_id)
        return

async def handle_spam(guild_id: int, user_id: int) -> None:
    # deny the user from giving aura for LIMIT_PENALTY seconds
    temp_banned_users[guild_id].append(user_id)
    await client.get_user(user_id).send(f"You have been temporarily banned for {LIMIT_PENALTY} seconds from giving aura in {client.get_guild(guild_id).name} due to spamming reactions.")
    if guilds[guild_id].log_channel_id is not None:
        log_event(guild_id, user_id, user_id, LogEvent.SPAMMING)

    # start a timer to allow the user to give aura again after LIMIT_PENALTY seconds
    await asyncio.sleep(LIMIT_PENALTY)
    temp_banned_users[guild_id].remove(user_id)

def log_aura_change(guild_id: int, recipient_id: int, user_id: int, event: ReactionEvent, emoji: str, points: int, url: str) -> None:
    sign = ""
    if event.is_add:
        if points > 0:
            sign = "+"
        elif points < 0:
            sign = "-"
    else:
        if points > 0:
            sign = "-"
        elif points < 0:
            sign = "+"

    connective = "to" if event.is_add else "from"
    log_message = f"<@{user_id}> [{event.past}]({url}) {emoji} {connective} <@{recipient_id}> ({sign}{abs(points)} points)"

    log_cache[guild_id].append(log_message)

def log_event(guild_id: int, recipient_id: int, user_id: int, event: LogEvent, points: int=None) -> None:
    match event:
        case LogEvent.MANUAL:
            if points is None:
                raise ValueError("Points must be provided for manual changes.")
            log_message = f"<@{user_id}> manually changed aura of <@{recipient_id}> ({'+' if points > 0 else ''}{points} points)"
        case LogEvent.SPAMMING:
            log_message = f"<@{user_id}> was temporarily banned for {LIMIT_PENALTY} seconds from giving aura due to spamming reactions."
        case LogEvent.DENY_GIVING | LogEvent.DENY_RECEIVING | LogEvent.DENY_BOTH:
            log_message = f"<@{user_id}> denied <@{recipient_id}> from {str(event)} aura."
        case LogEvent.ALLOW_GIVING | LogEvent.ALLOW_RECEIVING | LogEvent.ALLOW_BOTH:
            log_message = f"<@{user_id}> allowed <@{recipient_id}> to {str(event)} aura."
        case _:
            raise ValueError()
        
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
    leaderboard = [(user_id, user) for user_id, user in leaderboard if user.opted_in]

    iconurl = client.get_user(leaderboard[0][0]).avatar.url if (len(leaderboard) > 0 and client.get_user(leaderboard[0][0]) is not None) else None
    embed.set_thumbnail(url=iconurl)

    for i, (user_id, user) in enumerate(leaderboard):
        embed.description += f"{i+1}. **{user.aura}** | <@{user_id}>\n"
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

def get_aura_tagline(aura: int):    
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

def get_user_aura(guild_id: int, user_id: int) -> discord.Embed:
    embed = discord.Embed(color=0xb57f94)
    if guild_id not in guilds:
        return embed
    if user_id not in guilds[guild_id].users:
        return embed
    embed.set_author(name=f"Aura Breakdown")
    embed.set_thumbnail(url=client.get_user(user_id).avatar.url)

    user = guilds[guild_id].users[user_id]

    tag = get_aura_tagline(user.aura)

    if user.opted_in:
        embed.description = f"<@{user_id}> has **{user.aura}** aura.\n"
        embed.description += f"*{tag}*\n\n"
        embed.description += f"**{user.aura_contribution}** total aura contribution.\n\n"
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

@tasks.loop(seconds=UPDATE_INTERVAL)
async def update_leaderboards(skip=False):
    for guild_id in guilds:
        guild = guilds[guild_id]
        if skip or int(time.time()) - guild.last_update < UPDATE_INTERVAL + 10: # if the last update was less than LIMIT seconds ago. ie: if there is new data to display
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

async def check_user_permissions(interaction: discord.Interaction, required_permission: str):
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

@tree.command(name="help", description="Display the help text.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(color=0x74327a)
    embed.set_author(name="Aura", icon_url=client.user.avatar.url)
    embed.title = "Aura setup, help and info"
    embed.description = HELP_TEXT.split("|")[0]
    embed2 = discord.Embed(color=0x74327a)
    embed2.description = HELP_TEXT.split("|")[1]
    embed2.set_footer(text="If you have any questions, please contact @engiw.")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await interaction.followup.send(embed=embed2, ephemeral=True)

@tree.command(name="setup", description="Setup the bot. (Optional) Displays the leaderboard in the given channel.")
@app_commands.guild_only()
@app_commands.describe(channel="The channel to display the leaderboard in.")
async def setup(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not await check_user_permissions(interaction, "manage_channels"): return

    guild_id = interaction.guild.id
    if guild_id in guilds:
        await interaction.response.send_message("Bot is already set up in this server.")
        return

    try:
        guilds[guild_id] = Guild()
        guilds[guild_id].last_update = int(time.time())
        guilds[guild_id].reactions = {
            "⭐": EmojiReaction(points=1),
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
@app_commands.guild_only()
@app_commands.describe(channel="The channel to display the leaderboard in.")
async def update_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if not await check_user_permissions(interaction, "manage_channels"): return

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
@app_commands.guild_only()
async def delete(interaction: discord.Interaction):
    if not await check_user_permissions(interaction, "administrator"): return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    await (client.get_user(355938178265251842)).send(f"Guild {guild_id} data was deleted. Data as follows:\n\n```{json.dumps({str(guild_id): guilds[guild_id]}, default=lambda o: o.__dict__, indent=4)}```")
    del guilds[guild_id]

    save_data(guilds)
    await interaction.response.send_message("Data deleted. If this was a mistake, contact `@engiw` to restore data.")

@tree.command(name="leaderboard", description="Show the current leaderboard.")
@app_commands.guild_only()
async def leaderboard(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    await interaction.response.send_message(embed=get_leaderboard(guild_id))

@tree.command(name="logging", description="Enable or disable logging of aura changes.")
@app_commands.guild_only()
@app_commands.describe(channel="The channel to log aura changes in. Leave empty to disable logging.")
async def logging(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    if channel is not None:
        try:
            await channel.send("Aura logging enabled.")
            if guilds[guild_id].log_channel_id is not None:
                await interaction.response.send_message(f"Logging moved to in {channel.mention}. Logs will be sent every 10 seconds.")
            else:
                await interaction.response.send_message(f"Logging enabled in {channel.mention}. Logs will be sent every 10 seconds.")
            guilds[guild_id].log_channel_id = channel.id
        except discord.Forbidden:
            await interaction.response.send_message("I don't have permission to send messages in that channel. Please choose a different channel or update my permissions.")
    else:
        if guilds[guild_id].log_channel_id is None:
            await interaction.response.send_message("Logging is already disabled.")
            return
        guilds[guild_id].log_channel_id = None
        await interaction.response.send_message("Logging disabled.")
    update_time_and_save(guild_id, guilds)

@tree.command(name="aura", description="Check your or another person's aura.")
@app_commands.guild_only()
@app_commands.describe(user="The user to check the aura of. Leave empty to check your own aura.")
async def aura(interaction: discord.Interaction, user: discord.User = None):
    if user is None:
        user = interaction.user
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message("This user has had no interactions yet.")
        return
    await interaction.response.send_message(embed=get_user_aura(guild_id, user.id))

@tree.command(name="changeaura", description="Change a user's aura by this amount. Positive or negative. Admin only.")
@app_commands.guild_only()
@app_commands.describe(user="The user to change the aura of.", amount="The amount to change the aura by. Positive or negative.")
async def change_aura(interaction: discord.Interaction, user: discord.User, amount: int):
    if not await check_user_permissions(interaction, "administrator"): return
    
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message("This user has had no interactions yet.")
        return

    guilds[guild_id].users[user.id].aura += amount
    # add to log
    if guilds[guild_id].log_channel_id is not None:
        log_event(guild_id, user.id, interaction.user.id, LogEvent.MANUAL, amount)
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(f"Changed <@{user.id}>'s aura by {amount}.")

@tree.command(name="deny", description="Deny a user from giving or receiving aura.")
@app_commands.guild_only()
@app_commands.describe(user="The user to deny actions from.", action="The action to deny.")
async def deny(interaction: discord.Interaction, user: discord.User, action: Literal["give", "receive", "both"]):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message("This user has had no interactions yet.")
        return
    
    action = action.lower()
    if action not in ["give", "receive", "both"]:
        await interaction.response.send_message("Invalid action. Must be one of: `give`, `receive`, `both`.")
        return
    
    match action:
        case "give":
            if not guilds[guild_id].users[user.id].giving_allowed:
                await interaction.response.send_message("This user is already denied from giving aura.")
                return
            guilds[guild_id].users[user.id].giving_allowed = False
        case "receive":
            if not guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message("This user is already denied from receiving aura.")
                return
            guilds[guild_id].users[user.id].receiving_allowed = False
        case "both":
            if not guilds[guild_id].users[user.id].giving_allowed and not guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message("This user is already denied from giving and receiving aura.")
                return
            guilds[guild_id].users[user.id].giving_allowed = False
            guilds[guild_id].users[user.id].receiving_allowed = False

    update_time_and_save(guild_id, guilds)

    event = LogEvent.DENY_GIVING if action == "give" else LogEvent.DENY_RECEIVING if action == "receive" else LogEvent.DENY_BOTH
    await interaction.response.send_message(f"Denied <@{user.id}> from {event} aura.")

    if guilds[guild_id].log_channel_id is not None:
        log_event(guild_id, user.id, interaction.user.id, event)

@tree.command(name="allow", description="Allow a user to give or receive aura.")
@app_commands.guild_only()
@app_commands.describe(user="The user to allow actions from.", action="The action to allow.")
async def allow(interaction: discord.Interaction, user: discord.User, action: Literal["give", "receive", "both"]):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message("This user has had no interactions yet.")
        return
    
    action = action.lower()
    if action not in ["give", "receive", "both"]:
        await interaction.response.send_message("Invalid action. Must be one of: `give`, `receive`, `both`.")
        return

    match action:
        case "give":
            if guilds[guild_id].users[user.id].giving_allowed:
                await interaction.response.send_message("This user is already allowed to give aura.")
                return
            guilds[guild_id].users[user.id].giving_allowed = True
        case "receive":
            if guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message("This user is already allowed to receive aura.")
                return
            guilds[guild_id].users[user.id].receiving_allowed = True
        case "both":
            if guilds[guild_id].users[user.id].giving_allowed and guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message("This user is already allowed to give and receive aura.")
                return
            guilds[guild_id].users[user.id].giving_allowed = True
            guilds[guild_id].users[user.id].receiving_allowed = True

    update_time_and_save(guild_id, guilds)

    event = LogEvent.ALLOW_GIVING if action == "give" else LogEvent.ALLOW_RECEIVING if action == "receive" else LogEvent.ALLOW_BOTH
    await interaction.response.send_message(f"Allowed <@{user.id}> to {event} aura.")

    if guilds[guild_id].log_channel_id is not None:
        log_event(guild_id, user.id, interaction.user.id, event)

@opt_group.command(name="in", description="Opt in to aura tracking.")
@app_commands.guild_only()
async def opt_in(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if interaction.user.id not in guilds[guild_id].users:
        guilds[guild_id].users[interaction.user.id] = User()

    if guilds[guild_id].users[interaction.user.id].opted_in:
        await interaction.response.send_message("You are already opted in.")
        return

    guilds[guild_id].users[interaction.user.id].opted_in = True
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message("You are now opted in.")

@opt_group.command(name="out", description="Opt out of aura tracking.")
@app_commands.guild_only()
async def opt_out(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return

    if interaction.user.id not in guilds[guild_id].users:
        guilds[guild_id].users[interaction.user.id] = User()

    if not guilds[guild_id].users[interaction.user.id].opted_in:
        await interaction.response.send_message("You are already opted out.")
        return

    guilds[guild_id].users[interaction.user.id].opted_in = False
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message("You are now opted out.")

@emoji_group.command(name="add", description="Add an emoji to tracking.")
@app_commands.guild_only()
@app_commands.describe(emoji="The emoji to start tracking.", points="The points impact for the emoji. Positive or negative.")
async def add_emoji(interaction: discord.Interaction, emoji: str, points: int):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
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
        if is_emoji(emoji) or discord.utils.get(interaction.guild.emojis, id=int(emoji.split(":")[2][:-1])):
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
@app_commands.guild_only()
@app_commands.describe(emoji="The emoji to stop tracking.")
async def remove_emoji(interaction: discord.Interaction, emoji: str):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
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
@app_commands.guild_only()
@app_commands.describe(emoji="The emoji to update.", points="The new points impact for the emoji. Positive or negative.")
async def update_emoji(interaction: discord.Interaction, emoji: str, points: int):
    if not await check_user_permissions(interaction, "manage_channels"): return
    
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
@app_commands.guild_only()
async def list_emoji(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356179831288758384> first.")
        return
    
    await interaction.response.send_message(embed=get_emoji_list(guild_id))

client.run(TOKEN)