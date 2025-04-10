"""Provides functions to load and save data to a SQLite database."""

import sqlite3
import time

from models import *
from db_create import create_db
from config import DB


def update_time_and_save(guild_id: int, guilds: dict[int, Guild]):
    """Update the last update time for a guild and save the data.

    Parameters
    ----------
    guild_id: `int`
        The ID of the guild to update.
    guilds: `Dict[int, Guild]`
        A dictionary of guilds, where the key is the guild ID and the value is a `Guild` object.
    """

    if guild_id in guilds:
        guilds[guild_id].last_update = int(time.time())
    save_data(guilds)


def load_data(db_filename=DB) -> dict[int, Guild]:
    """Load the guild data from the SQLite database.

    Parameters
    ----------
    db_filename: `str`, optional
        The name of the database file to load the data from. Defaults to "aura_data.db".
    """

    try:
        with open(db_filename, "r"):
            pass
    except FileNotFoundError:
        create_db()
        print(f"Database {db_filename} was not found, so it was created.")
        return {}

    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    guilds = {}

    cursor.execute("SELECT * FROM guilds")
    guild_rows = cursor.fetchall()

    for guild_row in guild_rows:
        guild_id = guild_row[0]

        cursor.execute("SELECT * FROM users WHERE guild_id = ?", (guild_id,))
        user_rows = cursor.fetchall()

        users = {}
        for user_row in user_rows:
            users[user_row[1]] = User(
                aura=user_row[2],
                aura_contribution=user_row[3],
                num_pos_given=user_row[4],
                num_pos_received=user_row[5],
                num_neg_given=user_row[6],
                num_neg_received=user_row[7],
                opted_in=bool(user_row[8]),
                giving_allowed=bool(user_row[9]),
                receiving_allowed=bool(user_row[10]),
            )

        cursor.execute("SELECT * FROM reactions WHERE guild_id = ?", (guild_id,))
        reaction_rows = cursor.fetchall()

        reactions = {}
        for reaction_row in reaction_rows:
            reactions[reaction_row[1]] = EmojiReaction(points=reaction_row[2])

        cursor.execute("SELECT * FROM limits WHERE guild_id = ?", (guild_id,))
        limit_row = cursor.fetchone()

        limits = Limits(
            interval_long=limit_row[1],
            threshold_long=limit_row[2],
            interval_short=limit_row[3],
            threshold_short=limit_row[4],
            penalty=limit_row[5],
            adding_cooldown=limit_row[6],
            removing_cooldown=limit_row[7],
        )

        guilds[guild_id] = Guild(
            users=users,
            reactions=reactions,
            limits=limits,
            info_msg_id=guild_row[1],
            board_msg_id=guild_row[2],
            msgs_channel_id=guild_row[3],
            log_channel_id=guild_row[4],
            last_update=guild_row[5],
        )

    conn.close()
    return guilds


def save_data(guilds: dict[int, Guild], db_filename=DB):
    """Save the guild data to the SQLite database, ensuring deletions are handled."""

    try:
        with open(db_filename, "r"):
            pass
    except FileNotFoundError:
        create_db()
        print(f"Database {db_filename} was not found, so it was created.")

    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    # **1. Remove guilds that no longer exist in the dictionary**
    cursor.execute("SELECT id FROM guilds")
    existing_guilds = {row[0] for row in cursor.fetchall()}
    current_guilds = set(guilds.keys())

    deleted_guilds = existing_guilds - current_guilds
    for guild_id in deleted_guilds:
        cursor.execute("DELETE FROM guilds WHERE id = ?", (guild_id,))
        cursor.execute("DELETE FROM users WHERE guild_id = ?", (guild_id,))
        cursor.execute("DELETE FROM reactions WHERE guild_id = ?", (guild_id,))
        cursor.execute("DELETE FROM limits WHERE guild_id = ?", (guild_id,))

    # **2. Insert or update guilds**
    for guild_id, guild in guilds.items():
        cursor.execute(
            """
            INSERT OR REPLACE INTO guilds (id, info_msg_id, board_msg_id, msgs_channel_id, log_channel_id, last_update)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                guild_id,
                guild.info_msg_id,
                guild.board_msg_id,
                guild.msgs_channel_id,
                guild.log_channel_id,
                guild.last_update,
            ),
        )

        # **3. Handle users**
        cursor.execute("SELECT user_id FROM users WHERE guild_id = ?", (guild_id,))
        existing_users = {row[0] for row in cursor.fetchall()}
        current_users = set(guild.users.keys())

        # Delete removed users
        for user_id in existing_users - current_users:
            cursor.execute(
                "DELETE FROM users WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )

        # Insert/update users
        for user_id, user in guild.users.items():
            cursor.execute(
                """
                INSERT OR REPLACE INTO users (guild_id, user_id, aura, aura_contribution, num_pos_given, num_pos_received,
                num_neg_given, num_neg_received, opted_in, giving_allowed, receiving_allowed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    guild_id,
                    user_id,
                    user.aura,
                    user.aura_contribution,
                    user.num_pos_given,
                    user.num_pos_received,
                    user.num_neg_given,
                    user.num_neg_received,
                    int(user.opted_in),
                    int(user.giving_allowed),
                    int(user.receiving_allowed),
                ),
            )

        # **4. Handle reactions**
        cursor.execute("SELECT emoji FROM reactions WHERE guild_id = ?", (guild_id,))
        existing_reactions = {row[0] for row in cursor.fetchall()}
        current_reactions = set(guild.reactions.keys())

        # Delete removed reactions
        for emoji in existing_reactions - current_reactions:
            cursor.execute(
                "DELETE FROM reactions WHERE guild_id = ? AND emoji = ?",
                (guild_id, emoji),
            )

        # Insert/update reactions
        for emoji, reaction in guild.reactions.items():
            cursor.execute(
                """
                INSERT OR REPLACE INTO reactions (guild_id, emoji, points)
                VALUES (?, ?, ?)
            """,
                (guild_id, emoji, reaction.points),
            )

        # **5. Update limits**
        cursor.execute(
            """
            INSERT OR REPLACE INTO limits (guild_id, interval_long, threshold_long, interval_short, threshold_short, penalty,
            adding_cooldown, removing_cooldown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                guild_id,
                guild.limits.interval_long,
                guild.limits.threshold_long,
                guild.limits.interval_short,
                guild.limits.threshold_short,
                guild.limits.penalty,
                guild.limits.adding_cooldown,
                guild.limits.removing_cooldown,
            ),
        )

    conn.commit()
    conn.close()


def load_user_data(db_filename=DB) -> dict[int, GlobalUser]:
    """Load the user data from the SQLite database.

    Parameters
    ----------
    db_filename: `str`, optional
        The name of the database file to load the data from. Defaults to "aura_data.db".
    """

    try:
        with open(db_filename, "r"):
            pass
    except FileNotFoundError:
        create_db()
        print(f"Database {db_filename} was not found, so it was created.")
        return {}

    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM user_info")
    user_rows = cursor.fetchall()
    user_info = {}
    for user_row in user_rows:
        user_id = user_row[0]
        avatar_url = user_row[1]
        bot = bool(user_row[2])
        user_info[user_id] = GlobalUser(user_id=user_id, avatar_url=avatar_url, bot=bot)

    conn.close()
    return user_info


def save_user_data(user_info: dict[int, GlobalUser], db_filename=DB):
    """Save the user info data to the SQLite database.

    Parameters
    ----------
    user_info: `Dict[int, GlobalUser]`
        A dictionary of user info, where the key is the user ID and the value is a `GlobalUser` object.
    db_filename: `str`, optional
        The name of the database file to save the data to. Defaults to "aura_data.db".
    """

    try:
        with open(db_filename, "r"):
            pass
    except FileNotFoundError:
        create_db()
        print(f"Database {db_filename} was not found, so it was created.")

    conn = sqlite3.connect(db_filename)
    cursor = conn.cursor()

    for user_id, user in user_info.items():
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_info (user_id, avatar_url, bot)
            VALUES (?, ?, ?)
        """,
            (user_id, user.avatar_url, int(user.bot)),
        )

    conn.commit()
    conn.close()
