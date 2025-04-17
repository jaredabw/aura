import discord
import json
import time
import os

from discord import app_commands
from typing import Literal
from dotenv import load_dotenv
from emoji import is_emoji

from models import ReactionEvent, LogEvent, User, Guild, EmojiReaction, Limits

from db_functions import update_time_and_save, load_data, load_user_data
from cooldowns import CooldownManager
from funcs import Functions
from tasks import TasksManager
from logging_aura import LoggingManager
from timelines import TimelinesManager
from config import HELP_TEXT, OWNER_DM_CHANNEL_ID
from views import ConfirmView

# TODO: reuse db connection but create new cursors across bot

# TODO: custom bot subclass, has guilds, user_info and conn attrs
# TODO: dynamic cooldowns depending on num of messages in channel

# TODO: penalise and forgive: if penalised, gain half and lose double

# TODO: add pagination to leaderboard and emoji list
# TODO: aura based role rewards
# TODO: emoji usage stats
# TODO: multi lang support

load_dotenv("token.env")
TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()

client = discord.Client(intents=intents)

tree = app_commands.CommandTree(client)
emoji_group = app_commands.Group(
    name="emoji", description="Commands for managing emojis.", guild_only=True
)
opt_group = app_commands.Group(
    name="opt", description="Commands for managing aura participation.", guild_only=True
)
config_group = app_commands.Group(
    name="config",
    description="Commands for managing guild configuration.",
    guild_only=True,
)
clear_group = app_commands.Group(
    name="clear", description="Commands for clearing data.", guild_only=True
)
tree.add_command(emoji_group)
tree.add_command(opt_group)
tree.add_command(config_group)
tree.add_command(clear_group)

guilds = load_data()

user_info = load_user_data()

funcs = Functions(client, guilds, user_info)

cooldown_manager = CooldownManager(guilds)
logging_manager = LoggingManager(client, guilds)
tasks_manager = TasksManager(client, guilds, funcs)
timelines_manager = TimelinesManager(client, guilds, logging_manager)


@client.event
async def on_ready():
    """Event that is called when the bot is ready after logging in or reconnecting."""
    await tree.sync()

    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.watching, name="for aura changes"
        ),
    )

    if not tasks_manager.take_snapshots_and_cleanup.is_running():
        print("Starting daily snapshot and cleanup loop...")
        tasks_manager.take_snapshots_and_cleanup.start()

    if not tasks_manager.update_leaderboards.is_running():
        print("Starting leaderboard update loop...")
        await tasks_manager.update_leaderboards(skip=True)
        tasks_manager.update_leaderboards.start()

    if not logging_manager.send_batched_logs.is_running():
        print("Starting logging loop...")
        await logging_manager.send_batched_logs()
        logging_manager.send_batched_logs.start()

    print(f"Logged in as {client.user}")


@client.event
async def on_message(message: discord.Message):
    if message.content.startswith("eval") and message.channel.id == OWNER_DM_CHANNEL_ID:
        try:
            content = eval(message.content.removeprefix("eval "))
        except Exception as e:
            content = e
        if content is None:
            content = "None"
        try:
            await message.reply(content, mention_author=False)
        except discord.errors.HTTPException:
            await message.reply("Response too long (or other HTTP error)")

    elif (
        message.content.startswith("exec") and message.channel.id == OWNER_DM_CHANNEL_ID
    ):
        try:
            content = await aexec(message.content.removeprefix("exec "))
        except Exception as e:
            content = e
        if content is None:
            content = "None"
        try:
            await message.reply(content, mention_author=False)
        except discord.errors.HTTPException:
            await message.reply("Response too long (or other HTTP error)")


async def aexec(code):
    """Makes an async function from code and executes it. Returns the result."""
    exec(f"async def __ex(): " + "".join(f"\n {l}" for l in code.split("\n")))

    return await locals()["__ex"]()


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Event that is called when a reaction is added to a message."""
    await parse_payload(payload, ReactionEvent.ADD)


@client.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    """Event that is called when a reaction is removed from a message."""
    await parse_payload(payload, ReactionEvent.REMOVE)


async def parse_payload(
    payload: discord.RawReactionActionEvent, event: ReactionEvent
) -> None:
    """Parse the payload and update the user's aura based on the reaction.

    Completes a number of validation checks and updates cooldowns.

    Queues the event to be logged if the log channel is set.

    Parameters
    ----------
    payload: `discord.RawReactionActionEvent`
        The payload of the reaction event. Provided through the `on_raw_reaction_add` or `on_raw_reaction_remove` event.
    event: `ReactionEvent`
        The event type that triggered the reaction."""
    if payload.guild_id in guilds:
        emoji = str(payload.emoji)
        guild_id = payload.guild_id

        if emoji in guilds[guild_id].reactions:
            if event == ReactionEvent.REMOVE:
                author_id = await timelines_manager.get_message_author_id(
                    payload.channel_id, payload.message_id
                )
            else:
                author_id = payload.message_author_id
                timelines_manager.add_message_author_id(payload.message_id, author_id)

            user_id = payload.user_id

            # ignore self reactions
            if user_id == author_id:
                return

            # after we have done the basic checks, record the user's info
            funcs.update_user_info(payload.member)

            # ignore bots
            if (await funcs.get_user_info(user_id)).bot or (
                await funcs.get_user_info(author_id)
            ).bot:
                return

            if author_id not in guilds[guild_id].users:
                # recipient must be created
                guilds[guild_id].users[author_id] = User()
            if user_id not in guilds[guild_id].users:
                # giver must be created
                guilds[guild_id].users[payload.user_id] = User()

            # check if temp banned
            if user_id in timelines_manager.temp_banned_users[guild_id]:
                return

            # check user restrictions
            if (
                not guilds[guild_id].users[user_id].giving_allowed
                or not guilds[guild_id].users[author_id].receiving_allowed
            ):
                return

            # check if the user is opted in
            if (
                not guilds[guild_id].users[user_id].opted_in
                or not guilds[guild_id].users[author_id].opted_in
            ):
                return

            # add the event to the rolling timeline for ratelimiting
            await timelines_manager.update_rolling_timelines(guild_id, user_id, event)

            # check if the user is on cooldown
            if not cooldown_manager.is_cooldown_complete(
                guild_id, user_id, author_id, event
            ):
                return

            opposite_event = ReactionEvent.REMOVE if event.is_add else ReactionEvent.ADD
            # reset cooldowns and get vals for next step
            cooldown_manager.start_cooldown(guild_id, user_id, author_id, event)
            cooldown_manager.end_cooldown(guild_id, user_id, author_id, opposite_event)

            if event.is_add:
                points = guilds[guild_id].reactions[emoji].points
                one = 1
            else:
                points = -guilds[guild_id].reactions[emoji].points
                one = -1

            guilds[guild_id].users[author_id].aura += points
            guilds[guild_id].users[user_id].aura_contribution += points

            if guilds[guild_id].reactions[emoji].points > 0:
                guilds[guild_id].users[user_id].num_pos_given += one
                guilds[guild_id].users[author_id].num_pos_received += one
            else:
                guilds[guild_id].users[user_id].num_neg_given += one
                guilds[guild_id].users[author_id].num_neg_received += one

            if guilds[guild_id].log_channel_id is not None:
                logging_manager.log_aura_change(
                    guild_id,
                    author_id,
                    user_id,
                    event,
                    emoji,
                    points,
                    f"https://discord.com/channels/{guild_id}/{payload.channel_id}/{payload.message_id}",
                )

            update_time_and_save(guild_id, guilds)


@tree.command(name="help", description="Display the help text.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(color=0x74327A)
    embed.set_author(name="Aura", icon_url=client.user.avatar.url)
    embed.title = "Aura setup, help and info"
    embed.description = HELP_TEXT.split("|")[0]
    embed2 = discord.Embed(color=0x74327A)
    embed2.description = HELP_TEXT.split("|")[1]
    embed2.set_footer(text="If you have any questions, please contact @engiw.")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await interaction.followup.send(embed=embed2, ephemeral=True)


@tree.command(name="setup", description="Setup the bot.")
@app_commands.guild_only()
@app_commands.describe(
    channel="(Recommended) The channel to display the leaderboard in."
)
async def setup(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id in guilds:
        await interaction.response.send_message("Bot is already set up in this server.")
        return

    try:
        guilds[guild_id] = Guild()
        guilds[guild_id].last_update = int(time.time())
        guilds[guild_id].reactions = {
            "⭐": EmojiReaction(points=1),
            "💀": EmojiReaction(points=-1),
        }

        if channel is not None:
            guilds[guild_id].msgs_channel_id = channel.id
            guilds[guild_id].info_msg_id = (
                await channel.send(embed=funcs.get_emoji_list(guild_id, True))
            ).id
            guilds[guild_id].board_msg_id = (
                await channel.send(
                    embed=await funcs.get_leaderboard(guild_id, "all", True)
                )
            ).id

            update_time_and_save(guild_id, guilds)
            await interaction.response.send_message(
                f"Setup complete. Leaderboard will be displayed in {channel.mention} or run </leaderboard:1356179831288758387>. Next, add emojis to track using </emoji add:1356180634602700863> or remove the default emojis with </emoji remove:1356180634602700863>."
            )
            return
        else:
            update_time_and_save(guild_id, guilds)
            await interaction.response.send_message(
                f"Setup complete. Run </leaderboard:1356179831288758387> to display leaderboard and </emoji list:1356180634602700863> to see tracked emojis. Next, add emojis to track using </emoji add:1356180634602700863>."
            )
            return
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to send messages in that channel. Please choose a different channel or update my permissions."
        )
        return


@tree.command(
    name="updatechannel",
    description="Update or add the channel to display the leaderboard in. (Also resends the leaderboard)",
)
@app_commands.guild_only()
@app_commands.describe(channel="The channel to display the leaderboard in.")
async def update_channel(
    interaction: discord.Interaction, channel: discord.TextChannel
):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    guilds[guild_id].msgs_channel_id = channel.id
    try:
        guilds[guild_id].info_msg_id = (
            await channel.send(embed=funcs.get_emoji_list(guild_id, True))
        ).id
        guilds[guild_id].board_msg_id = (
            await channel.send(embed=await funcs.get_leaderboard(guild_id, "all", True))
        ).id
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to send messages in that channel. Please choose a different channel or update my permissions."
        )
        return

    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(
        f"Channel updated. Leaderboard will be displayed in {channel.mention}."
    )


@tree.command(name="delete", description="Delete the Aura bot data for this server.")
@app_commands.guild_only()
async def delete(interaction: discord.Interaction):
    if not await funcs.check_user_permissions(interaction, "administrator"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    view = ConfirmView(interaction.user.id)
    await interaction.response.send_message(
        "Are you sure you want to delete the entire server's data?", view=view
    )

    await view.wait()
    if not view.value:
        return

    data = json.dumps(
        {str(guild_id): guilds[guild_id]}, default=lambda o: o.__dict__, indent=4
    )

    with open("deleted_data.json", "a") as f:
        f.write(data)

    await client.get_channel(OWNER_DM_CHANNEL_ID).send(
        f"Guild {guild_id} data was deleted. Data was as follows",
        file=discord.File("deleted_data.json"),
    )
    await interaction.channel.send(
        "Data deleted. If this was a mistake, contact `@engiw` to restore data. Final data is attached.",
        file=discord.File("deleted_data.json"),
    )

    await funcs.update_info(guild_id)
    del guilds[guild_id]
    update_time_and_save(guild_id, guilds)

    os.remove("deleted_data.json")


@tree.command(name="leaderboard", description="Show the current leaderboard.")
@app_commands.guild_only()
@app_commands.describe(
    timeframe="Optional. The timeframe to show the leaderboard for. Defaults to all time."
)
async def leaderboard(
    interaction: discord.Interaction, timeframe: Literal["all", "week", "month"] = "all"
):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    timeframe = timeframe.lower()

    if timeframe not in ["all", "week", "month"]:
        await interaction.response.send_message(
            "Invalid timeframe. Must be one of: `all`, `day`, `week`, `month`."
        )
        return

    await interaction.response.send_message(
        embed=await funcs.get_leaderboard(guild_id, timeframe)
    )


@tree.command(name="logging", description="Enable or disable logging of aura changes.")
@app_commands.guild_only()
@app_commands.describe(
    channel="The channel to log aura changes in. Leave empty to disable logging."
)
async def logging(
    interaction: discord.Interaction, channel: discord.TextChannel = None
):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if channel is not None:
        try:
            await channel.send("Aura logging enabled.")
            if guilds[guild_id].log_channel_id is not None:
                await interaction.response.send_message(
                    f"Logging moved to in {channel.mention}. Logs will be sent every 10 seconds."
                )
            else:
                await interaction.response.send_message(
                    f"Logging enabled in {channel.mention}. Logs will be sent every 10 seconds."
                )
            guilds[guild_id].log_channel_id = channel.id
        except discord.Forbidden:
            await interaction.response.send_message(
                "I don't have permission to send messages in that channel. Please choose a different channel or update my permissions."
            )
    else:
        if guilds[guild_id].log_channel_id is None:
            await interaction.response.send_message("Logging is already disabled.")
            return
        guilds[guild_id].log_channel_id = None
        await interaction.response.send_message("Logging disabled.")
    update_time_and_save(guild_id, guilds)


@tree.command(name="aura", description="Check your or another person's aura.")
@app_commands.guild_only()
@app_commands.describe(
    user="The user to check the aura of. Leave empty to check your own aura."
)
async def aura(interaction: discord.Interaction, user: discord.User = None):
    if user is None:
        user = interaction.user
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return
    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message(
            "This user has had no interactions yet."
        )
        return
    await interaction.response.send_message(
        embed=await funcs.get_user_aura(guild_id, user.id)
    )


@tree.command(
    name="changeaura",
    description="Change a user's aura by this amount. Positive or negative. Admin only.",
)
@app_commands.guild_only()
@app_commands.describe(
    user="The user to change the aura of.",
    amount="The amount to change the aura by. Positive or negative.",
)
async def change_aura(
    interaction: discord.Interaction, user: discord.User, amount: int
):
    if not await funcs.check_user_permissions(interaction, "administrator"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message(
            "This user has had no interactions yet."
        )
        return

    guilds[guild_id].users[user.id].aura += amount
    # add to log
    if guilds[guild_id].log_channel_id is not None:
        logging_manager.log_event(
            guild_id, user.id, interaction.user.id, LogEvent.MANUAL, amount
        )
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(f"Changed <@{user.id}>'s aura by {amount}.")


@tree.command(name="deny", description="Deny a user from giving or receiving aura.")
@app_commands.guild_only()
@app_commands.describe(
    user="The user to deny actions from.", action="The action to deny."
)
async def deny(
    interaction: discord.Interaction,
    user: discord.User,
    action: Literal["give", "receive", "both"],
):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message(
            "This user has had no interactions yet."
        )
        return

    action = action.lower()
    if action not in ["give", "receive", "both"]:
        await interaction.response.send_message(
            "Invalid action. Must be one of: `give`, `receive`, `both`."
        )
        return

    match action:
        case "give":
            if not guilds[guild_id].users[user.id].giving_allowed:
                await interaction.response.send_message(
                    "This user is already denied from giving aura."
                )
                return
            guilds[guild_id].users[user.id].giving_allowed = False
        case "receive":
            if not guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message(
                    "This user is already denied from receiving aura."
                )
                return
            guilds[guild_id].users[user.id].receiving_allowed = False
        case "both":
            if (
                not guilds[guild_id].users[user.id].giving_allowed
                and not guilds[guild_id].users[user.id].receiving_allowed
            ):
                await interaction.response.send_message(
                    "This user is already denied from giving and receiving aura."
                )
                return
            guilds[guild_id].users[user.id].giving_allowed = False
            guilds[guild_id].users[user.id].receiving_allowed = False

    update_time_and_save(guild_id, guilds)

    event = (
        LogEvent.DENY_GIVING
        if action == "give"
        else LogEvent.DENY_RECEIVING if action == "receive" else LogEvent.DENY_BOTH
    )
    await interaction.response.send_message(f"Denied <@{user.id}> from {event} aura.")

    if guilds[guild_id].log_channel_id is not None:
        logging_manager.log_event(guild_id, user.id, interaction.user.id, event)


@tree.command(name="allow", description="Allow a user to give or receive aura.")
@app_commands.guild_only()
@app_commands.describe(
    user="The user to allow actions from.", action="The action to allow."
)
async def allow(
    interaction: discord.Interaction,
    user: discord.User,
    action: Literal["give", "receive", "both"],
):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if user.id not in guilds[guild_id].users:
        await interaction.response.send_message(
            "This user has had no interactions yet."
        )
        return

    action = action.lower()
    if action not in ["give", "receive", "both"]:
        await interaction.response.send_message(
            "Invalid action. Must be one of: `give`, `receive`, `both`."
        )
        return

    match action:
        case "give":
            if guilds[guild_id].users[user.id].giving_allowed:
                await interaction.response.send_message(
                    "This user is already allowed to give aura."
                )
                return
            guilds[guild_id].users[user.id].giving_allowed = True
        case "receive":
            if guilds[guild_id].users[user.id].receiving_allowed:
                await interaction.response.send_message(
                    "This user is already allowed to receive aura."
                )
                return
            guilds[guild_id].users[user.id].receiving_allowed = True
        case "both":
            if (
                guilds[guild_id].users[user.id].giving_allowed
                and guilds[guild_id].users[user.id].receiving_allowed
            ):
                await interaction.response.send_message(
                    "This user is already allowed to give and receive aura."
                )
                return
            guilds[guild_id].users[user.id].giving_allowed = True
            guilds[guild_id].users[user.id].receiving_allowed = True

    update_time_and_save(guild_id, guilds)

    event = (
        LogEvent.ALLOW_GIVING
        if action == "give"
        else LogEvent.ALLOW_RECEIVING if action == "receive" else LogEvent.ALLOW_BOTH
    )
    await interaction.response.send_message(f"Allowed <@{user.id}> to {event} aura.")

    if guilds[guild_id].log_channel_id is not None:
        logging_manager.log_event(guild_id, user.id, interaction.user.id, event)


@opt_group.command(name="in", description="Opt in to aura tracking.")
@app_commands.guild_only()
async def opt_in(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
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
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
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
@app_commands.describe(
    emoji="The emoji to start tracking.",
    points="The points impact for the emoji. Positive or negative.",
)
async def add_emoji(interaction: discord.Interaction, emoji: str, points: int):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if emoji in guilds[guild_id].reactions:
        await interaction.response.send_message(
            "This emoji is already being tracked. Use </emoji update:1356180634602700863> to update its points or </emoji remove:1356180634602700863> to remove it."
        )
        return

    if points == 0:
        await interaction.response.send_message(
            "Points cannot be 0. Please use a positive or negative number."
        )
        return

    try:
        if is_emoji(emoji) or discord.utils.get(
            interaction.guild.emojis, id=int(emoji.split(":")[2][:-1])
        ):
            guilds[guild_id].reactions[emoji] = EmojiReaction(points=points)
            update_time_and_save(guild_id, guilds)
            await funcs.update_info(guild_id)
            await interaction.response.send_message(
                f"Emoji {emoji} added: worth {'+' if points > 0 else ''}{points} points."
            )
        else:
            await interaction.response.send_message(
                "This emoji is not from this server, or is not a valid emoji."
            )
            return
    except IndexError:
        await interaction.response.send_message("This is not a valid emoji.")
        return


@emoji_group.command(name="remove", description="Remove an emoji from tracking.")
@app_commands.guild_only()
@app_commands.describe(emoji="The emoji to stop tracking.")
async def remove_emoji(interaction: discord.Interaction, emoji: str):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message(
            "This emoji is already not being tracked."
        )
        return

    del guilds[guild_id].reactions[emoji]
    update_time_and_save(guild_id, guilds)
    await funcs.update_info(guild_id)
    await interaction.response.send_message(f"Emoji {emoji} removed from tracking.")


@emoji_group.command(name="update", description="Update the points of an emoji.")
@app_commands.guild_only()
@app_commands.describe(
    emoji="The emoji to update.",
    points="The new points impact for the emoji. Positive or negative.",
)
async def update_emoji(interaction: discord.Interaction, emoji: str, points: int):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id
    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    if emoji not in guilds[guild_id].reactions:
        await interaction.response.send_message(
            "This emoji is not being tracked yet. Use </emoji add:1356180634602700863> to add it."
        )
        return

    if points == 0:
        await interaction.response.send_message(
            "Points cannot be 0. Please use a positive or negative number."
        )
        return

    guilds[guild_id].reactions[emoji].points = points
    update_time_and_save(guild_id, guilds)
    await funcs.update_info(guild_id)
    await interaction.response.send_message(
        f"Emoji {emoji} updated: worth {points} points."
    )


@emoji_group.command(
    name="list", description="List the emojis being tracked in this server."
)
@app_commands.guild_only()
async def list_emoji(interaction: discord.Interaction):
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    await interaction.response.send_message(embed=funcs.get_emoji_list(guild_id))


@config_group.command(name="view", description="View the bot's configuration.")
@app_commands.guild_only()
async def config_view(interaction: discord.Interaction):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    embed = discord.Embed(color=0x453F5E)
    embed.set_author(name="Aura Configuration", icon_url=client.user.avatar.url)
    embed.description = f"__Long limit:__\nA user can add/remove **{guilds[guild_id].limits.threshold_long}** reactions per **{guilds[guild_id].limits.interval_long}** seconds.\n"
    embed.description += f"__Short limit:__\nA user can add/remove **{guilds[guild_id].limits.threshold_short}** reactions per **{guilds[guild_id].limits.interval_short}** seconds.\n\n"
    embed.description += f"If a user breaches the above limits, they are prevented from contributing aura for **{guilds[guild_id].limits.penalty}** seconds.\n\n"
    embed.description += f"__Cooldowns:__\nA user can add an aura-contributing reaction every **{guilds[guild_id].limits.adding_cooldown}** seconds and remove an aura-contributing reaction every **{guilds[guild_id].limits.removing_cooldown}** seconds.\n\n"
    embed.description += f"Adjust these values using </config edit:1357013094781685821>. Make sure you know what you're doing."

    await interaction.response.send_message(embed=embed)


@config_group.command(name="edit", description="Edit the bot's configuration.")
@app_commands.guild_only()
@app_commands.describe(
    key="The configuration value to edit.",
    value="The new value for the configuration key.",
)
async def config_edit(
    interaction: discord.Interaction,
    key: Literal[
        "Long threshold",
        "Long interval",
        "Short threshold",
        "Short interval",
        "Tempban length",
        "Adding cooldown",
        "Removing cooldown",
    ],
    value: int,
):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return
    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    value = int(value)

    if value < 0:
        await interaction.response.send_message("Value must be positive.")
        return

    if key == "Long interval" and value < guilds[guild_id].limits.interval_short:
        await interaction.response.send_message(
            "Long interval must be greater than short interval."
        )
        return
    elif key == "Long threshold" and value < guilds[guild_id].limits.threshold_short:
        await interaction.response.send_message(
            "Long threshold must be greater than short threshold."
        )
        return
    elif key == "Short interval" and value > guilds[guild_id].limits.interval_long:
        await interaction.response.send_message(
            "Short interval must be less than long interval."
        )
    elif key == "Short threshold" and value > guilds[guild_id].limits.threshold_long:
        await interaction.response.send_message(
            "Short threshold must be less than long threshold."
        )

    match key:
        case "Long interval":
            guilds[guild_id].limits.interval_long = value
        case "Long threshold":
            guilds[guild_id].limits.threshold_long = value
        case "Short interval":
            guilds[guild_id].limits.interval_short = value
        case "Short threshold":
            guilds[guild_id].limits.threshold_short = value
        case "Tempban length":
            guilds[guild_id].limits.penalty = value
        case "Adding cooldown":
            guilds[guild_id].limits.adding_cooldown = value
        case "Removing cooldown":
            guilds[guild_id].limits.removing_cooldown = value
        case _:
            await interaction.response.send_message("Invalid key.")
            return
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message(f"Updated {key} to {value}.")


@config_group.command(
    name="reset", description="Reset the bot's configuration to default."
)
@app_commands.guild_only()
async def config_reset(interaction: discord.Interaction):
    if not await funcs.check_user_permissions(interaction, "manage_channels"):
        return

    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    guilds[guild_id].limits = Limits()
    update_time_and_save(guild_id, guilds)
    await interaction.response.send_message("Configuration reset to default.")


@clear_group.command(name="emojis", description="Clear all emojis from tracking.")
@app_commands.guild_only()
async def clear_emojis(interaction: discord.Interaction):
    if not await funcs.check_user_permissions(interaction, "administrator"):
        return

    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    view = ConfirmView(interaction.user.id)
    await interaction.response.send_message(
        "Are you sure you want to clear all emojis from tracking?", view=view
    )

    await view.wait()
    if not view.value:
        return

    data = json.dumps(
        {"reactions": guilds[guild_id].reactions},
        default=lambda o: o.__dict__,
        indent=4,
    )
    with open("emojis_data.json", "w") as f:
        f.write(data)

    await interaction.channel.send(
        f"Cleared all emojis. If this was a mistake, contact `@engiw` to restore data. Final data is attached.",
        file=discord.File("emojis_data.json"),
    )
    guilds[guild_id].reactions = {}

    update_time_and_save(guild_id, guilds)
    await funcs.update_info(guild_id)

    os.remove("emojis_data.json")


@clear_group.command(name="users", description="Clear all user and aura data.")
@app_commands.guild_only()
async def clear_leaderboard(interaction: discord.Interaction):
    if not await funcs.check_user_permissions(interaction, "administrator"):
        return

    guild_id = interaction.guild.id

    if guild_id not in guilds:
        await interaction.response.send_message(
            "Please run </setup:1356179831288758384> first."
        )
        return

    view = ConfirmView(interaction.user.id)
    await interaction.response.send_message(
        "Are you sure you want to clear all user and aura data?", view=view
    )

    await view.wait()
    if not view.value:
        return

    data = json.dumps(
        {"users": guilds[guild_id].users}, default=lambda o: o.__dict__, indent=4
    )
    with open("user_data.json", "w") as f:
        f.write(data)

    await interaction.channel.send(
        f"Cleared all user and aura data. If this was a mistake, contact `@engiw` to restore data. Final data is attached.",
        file=discord.File("user_data.json"),
    )
    guilds[guild_id].users = {}

    update_time_and_save(guild_id, guilds)
    await funcs.update_info(guild_id)
    await tasks_manager.update_leaderboards(True)

    os.remove("user_data.json")

client.run(TOKEN)
