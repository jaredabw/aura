'''Insert JSON data into SQLite database for Aura bot.'''

import json
import sqlite3
import sys

DB_FILENAME = "aura_data.db"

def insert_users(cursor: sqlite3.Cursor, guild_id: int, users: dict):
    """Insert user data into the database."""
    for user_id, user in users.items():
        cursor.execute("""
            INSERT OR REPLACE INTO users (guild_id, user_id, aura, aura_contribution, num_pos_given, num_pos_received,
                                          num_neg_given, num_neg_received, opted_in, giving_allowed, receiving_allowed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guild_id, int(user_id), user["aura"], user["aura_contribution"],
            user["num_pos_given"], user["num_pos_received"], user["num_neg_given"], user["num_neg_received"],
            int(user["opted_in"]), int(user["giving_allowed"]), int(user["receiving_allowed"])
        ))

def insert_reactions(cursor: sqlite3.Cursor, guild_id: int, reactions: dict):
    """Insert reaction data into the database."""
    for emoji, reaction in reactions.items():
        cursor.execute("""
            INSERT OR REPLACE INTO reactions (guild_id, emoji, points)
            VALUES (?, ?, ?)
        """, (guild_id, emoji, reaction["points"]))

def insert_guild_data(cursor: sqlite3.Cursor, guild_id: int, guild_data: dict):
    """Insert full guild data into the database."""
    cursor.execute("""
        INSERT OR REPLACE INTO guilds (id, info_msg_id, board_msg_id, msgs_channel_id, log_channel_id, last_update)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        guild_id, guild_data.get("info_msg_id"), guild_data.get("board_msg_id"),
        guild_data.get("msgs_channel_id"), guild_data.get("log_channel_id"), guild_data.get("last_update")
    ))

    if "users" in guild_data:
        insert_users(cursor, guild_id, guild_data["users"])
    
    if "reactions" in guild_data:
        insert_reactions(cursor, guild_id, guild_data["reactions"])

def insert_json_data(json_data: dict, guild_id: int):
    """Determine the type of data and insert it into the database."""
    conn = sqlite3.connect(DB_FILENAME)
    cursor = conn.cursor()

    if "users" in json_data:
        insert_users(cursor, guild_id, json_data["users"])
    elif "reactions" in json_data:
        insert_reactions(cursor, guild_id, json_data["reactions"])
    else:
        insert_guild_data(cursor, guild_id, json_data[str(guild_id)])

    conn.commit()
    conn.close()
    print("Data inserted successfully.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python db_insert_json.py <guild_id> <json_file>")
        sys.exit(1)

    guild_id = int(sys.argv[1])
    json_file = sys.argv[2]

    with open(json_file, "r") as file:
        data = json.load(file)

    insert_json_data(data, guild_id)
