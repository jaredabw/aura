import discord
import json
import time
import os
from discord import app_commands
from discord.ext import tasks
from dataclasses import dataclass, field
from typing import Dict
from dotenv import load_dotenv

load_dotenv("token.env")
TOKEN = os.getenv("TOKEN")

@dataclass
class User:
    aura: int = 0

@dataclass
class EmojiReaction:
    delta: int = 0

@dataclass
class Guild:
    users: Dict[int, User] = field(default_factory=dict)
    reactions: Dict[str, EmojiReaction] = field(default_factory=dict)
    info_msg_id: int = None
    board_msg_id: int = None
    msgs_channel_id: int = None
    last_update: int = None

def load_data(filename="data.json"):
    try:
        with open(filename, "r") as file:
            raw_data: dict[str, dict[int, dict]] = json.load(file)
            guilds: dict[int, Guild] = {}
            for guild_id, guild in raw_data.get("guilds", {}).items():
                users = {user_id: User(aura=data["aura"]) for user_id, data in guild.get("users", {}).items()}
                reactions = {emoji: EmojiReaction(delta=data["delta"]) for emoji, data in guild.get("reactions", {}).items()}
                guilds[int(guild_id)] = Guild(
                    users=users,
                    reactions=reactions,
                    info_msg_id=guild.get("info_msg_id", None),
                    board_msg_id=guild.get("board_msg_id", None),
                    msgs_channel_id=guild.get("msgs_channel_id", None),
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
            "last_update": guild.last_update
        }

        for user_id, user in guild.users.items():
            guild_data["users"][user_id] = {"aura": user.aura}
        
        for emoji, reaction in guild.reactions.items():
            guild_data["reactions"][emoji] = {"delta": reaction.delta}

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
tree.add_command(emoji_group, guild=discord.Object(id=1099224566917767188))

guilds = load_data()

@client.event
async def on_ready():
    await tree.sync(guild=discord.Object(id=1099224566917767188))

    await client.change_presence(status=discord.Status.online, activity=discord.Activity(type=discord.ActivityType.watching, name="for aura changes"))
    update_leaderboards.start()
    print(f"Logged in as {client.user}")

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.guild_id in guilds:
        emoji = str(payload.emoji)
        guild_id = payload.guild_id
        user_id = payload.user_id
        if emoji in guilds[guild_id].reactions:
            if user_id not in guilds[guild_id].users:
                guilds[guild_id].users[user_id] = User()
            guilds[guild_id].users[user_id].aura += guilds[guild_id].reactions[emoji].delta
            update_time_and_save(guild_id, guilds)

# need to add pagination/multiple embeds
def get_leaderboard(guild_id: int) -> discord.Embed:
    embed = discord.Embed(color=0x74327a)
    embed.set_author(name=f"🏆 {client.get_guild(guild_id).name} Aura Leaderboard")
    embed.description = ""

    leaderboard = sorted(guilds[guild_id].users.items(), key=lambda item: item[1].aura, reverse=True)

    for i, (user_id, user) in enumerate(leaderboard):
        member = client.get_user(user_id)
        if member is not None:
            embed.description += f"{i+1}. **{member.name}** | {user.aura}\n"
        else:
            embed.description += f"{i+1}. **{user_id}** | {user.aura}\n"
    return embed

# need to add pagination/multiple embeds
def get_emoji_list(guild_id: int) -> discord.Embed:
    embed = discord.Embed(color=0x74327a)
    embed.set_author(name=f"🔧 {client.get_guild(guild_id).name} Emoji List")
    embed.description = ""

    emojis = sorted(guilds[guild_id].reactions.items(), key=lambda item: item[1].delta, reverse=True)

    for emoji, reaction in emojis:
        embed.description += f"{emoji} **{'+' if reaction.delta > 0 else ''}{reaction.delta}**\n"

    return embed

@tasks.loop(seconds=120)
async def update_leaderboards():
    for guild_id in guilds:
        guild = guilds[guild_id]
        if int(time.time()) - guild.last_update < 130: # if the last update was less than 130 seconds ago. ie: if there is new data to display
            if guild.msgs_channel_id is not None:
                channel = client.get_channel(guild.msgs_channel_id)
                if channel is not None:
                    try:
                        board_msg = await channel.fetch_message(guild.board_msg_id)
                        await board_msg.edit(embed=get_leaderboard(guild_id))
                    except discord.NotFound:
                        pass

async def update_info(guild_id: int):
    guild = guilds[guild_id]
    if guild.msgs_channel_id is not None:
        channel = client.get_channel(guild.msgs_channel_id)
        if channel is not None:
            try:
                info_msg = await channel.fetch_message(guild.info_msg_id)
                await info_msg.edit(embed=get_emoji_list(guild_id))
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
        if channel is not None:
            guilds[guild_id].msgs_channel_id = channel.id
            guilds[guild_id].info_msg_id = (await channel.send(embed=get_emoji_list(guild_id))).id
            guilds[guild_id].board_msg_id = (await channel.send(embed=get_leaderboard(guild_id))).id

            update_time_and_save(guild_id, guilds)
            await interaction.response.send_message(f"Setup complete. Leaderboard will be displayed in {channel.mention} or run </leaderboard:1356146448244146209>. Next, add emojis to track using </emoji add:1356150986422620301>.")
            return
        else:
            await interaction.response.send_message(f"Setup complete. Run </leaderboard:1356146448244146209> to display leaderboard and </emoji list:1356150986422620301> to see tracked emojis. Next, add emojis to track using </emoji add:1356150986422620301>.")
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
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return

    guilds[guild_id].msgs_channel_id = channel.id
    guilds[guild_id].info_msg_id = (await channel.send(embed=get_emoji_list(guild_id))).id
    guilds[guild_id].board_msg_id = (await channel.send(embed=get_leaderboard(guild_id))).id

    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(f"Channel updated. Leaderboard will be displayed in {channel.mention}.")

@tree.command(name="delete", description="Delete the Aura bot data for this server.")
@app_commands.checks.has_permissions(manage_channels=True)
async def delete(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return

    await (client.get_user(355938178265251842)).send(f"Guild {guild_id} data was deleted. Data as follows:\n\n```{json.dumps({str(guild_id): guilds[guild_id]}, default=lambda o: o.__dict__, indent=4)}```")
    del guilds[guild_id]

    save_data(guilds)
    await interaction.response.send_message("Data deleted. If this was a mistake, contact `@engiw` to restore data.")

@tree.command(name="leaderboard", description="Show the leaderboard at this moment.")
async def leaderboard(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return

    await interaction.response.send_message(embed=get_leaderboard(guild_id))

def is_valid_unicode_emoji(emoji: str) -> bool:
    try:
        parsed_emoji = discord.PartialEmoji.from_str(emoji)
        return parsed_emoji.is_unicode_emoji()
    except Exception:
        return False

@emoji_group.command(name="add", description="Add an emoji to tracking.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to start tracking.", delta="The delta value for the emoji.")
async def add_emoji(interaction: discord.Interaction, emoji: str, delta: int):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return

    if emoji in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is already being tracked. Use </emoji update:1356150986422620301> to update the delta or </emoji remove:1356150986422620301> to remove it.")
        return
    
    if is_valid_unicode_emoji(emoji) or discord.utils.get(interaction.guild.emojis, id=int(emoji.split(":")[2][:-1])):
        guilds[guild_id].reactions[emoji] = EmojiReaction(delta=delta)
        update_time_and_save(guild_id, guilds)
        await update_info(guild_id)
        await interaction.response.send_message(f"Emoji {emoji} added to tracking with delta {'+' if delta > 0 else ''}{delta}.")
    else:
        await interaction.response.send_message("This emoji is not from this server.")
        return

@emoji_group.command(name="remove", description="Remove an emoji from tracking.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to stop tracking.")
async def remove_emoji(interaction: discord.Interaction, emoji: str):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return

    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is already not being tracked.")
        return
    
    del guilds[guild_id].reactions[emoji]
    update_time_and_save(guild_id, guilds)
    await update_info(guild_id)
    await interaction.response.send_message(f"Emoji {emoji} removed from tracking.")

@emoji_group.command(name="update", description="Update the delta of an emoji.")
@app_commands.checks.has_permissions(manage_channels=True)
@app_commands.describe(emoji="The emoji to update.", delta="The new delta value.")
async def update_emoji(interaction: discord.Interaction, emoji: str, delta: int):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return
    
    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message("This emoji is not being tracked yet. Use </emoji add:1356150986422620301> to add it.")
        return
    
    guilds[guild_id].reactions[emoji].delta = delta
    update_time_and_save(guild_id, guilds)
    await update_info(guild_id)
    await interaction.response.send_message(f"Emoji {emoji} updated with new delta {delta}.")

@emoji_group.command(name="list", description="List the emojis being tracked in this server.")
async def list_emoji(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message("Please run </setup:1356146448244146206> first.")
        return
    
    await interaction.response.send_message(embed=get_emoji_list(guild_id))

client.run(TOKEN)