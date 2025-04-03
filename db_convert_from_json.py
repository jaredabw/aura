import json
import sqlite3

with open('data.json', 'r') as file:
    data = json.load(file)

conn = sqlite3.connect("aura_data.db")
cursor = conn.cursor()

for guild_id, guild_data in data["guilds"].items():
    cursor.execute("""
        INSERT OR REPLACE INTO guilds (id, info_msg_id, board_msg_id, msgs_channel_id, log_channel_id, last_update)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        guild_data["info_msg_id"],
        guild_data["board_msg_id"],
        guild_data["msgs_channel_id"],
        guild_data["log_channel_id"],
        guild_data["last_update"]
    ))

    for user_id, user_data in guild_data["users"].items():
        cursor.execute("""
            INSERT OR REPLACE INTO users (user_id, guild_id, aura, aura_contribution, num_pos_given, num_pos_received,
            num_neg_given, num_neg_received, opted_in, giving_allowed, receiving_allowed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            guild_id,
            user_data["aura"],
            user_data["aura_contribution"],
            user_data["num_pos_given"],
            user_data["num_pos_received"],
            user_data["num_neg_given"],
            user_data["num_neg_received"],
            int(user_data["opted_in"]),
            int(user_data["giving_allowed"]),
            int(user_data["receiving_allowed"])
        ))

    for emoji, reaction_data in guild_data["reactions"].items():
        cursor.execute("""
            INSERT OR REPLACE INTO reactions (guild_id, emoji, points)
            VALUES (?, ?, ?)
        """, (
            guild_id,
            emoji,
            reaction_data["points"]
        ))

    limits_data = guild_data["limits"]
    cursor.execute("""
        INSERT OR REPLACE INTO limits (guild_id, interval_long, threshold_long, interval_short, threshold_short, penalty,
        adding_cooldown, removing_cooldown)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        guild_id,
        limits_data["interval_long"],
        limits_data["threshold_long"],
        limits_data["interval_short"],
        limits_data["threshold_short"],
        limits_data["penalty"],
        limits_data["adding_cooldown"],
        limits_data["removing_cooldown"]
    ))

conn.commit()
conn.close()

print("Data conversion complete!")
