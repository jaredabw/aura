"""Script to create the database for the Aura system."""

import sqlite3

from config import DB


def create_db():
    conn = sqlite3.connect(DB)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER PRIMARY KEY,
            info_msg_id INTEGER,
            board_msg_id INTEGER,
            msgs_channel_id INTEGER,
            log_channel_id INTEGER,
            last_update INTEGER
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            guild_id INTEGER,
            user_id INTEGER,
            aura INTEGER,
            aura_contribution INTEGER,
            num_pos_given INTEGER,
            num_pos_received INTEGER,
            num_neg_given INTEGER,
            num_neg_received INTEGER,
            opted_in INTEGER,
            giving_allowed INTEGER,
            receiving_allowed INTEGER,
            PRIMARY KEY (guild_id, user_id),
            FOREIGN KEY (guild_id) REFERENCES guilds(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reactions (
            guild_id INTEGER,
            emoji TEXT,
            points INTEGER,
            PRIMARY KEY (guild_id, emoji),
            FOREIGN KEY (guild_id) REFERENCES guilds(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS limits (
            guild_id INTEGER PRIMARY KEY,
            interval_long INTEGER,
            threshold_long INTEGER,
            interval_short INTEGER,
            threshold_short INTEGER,
            penalty INTEGER,
            adding_cooldown INTEGER,
            removing_cooldown INTEGER,
            FOREIGN KEY (guild_id) REFERENCES guilds(id)
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE user_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            aura INTEGER NOT NULL,
            aura_contribution INTEGER NOT NULL,
            num_pos_given INTEGER NOT NULL,
            num_pos_received INTEGER NOT NULL,
            num_neg_given INTEGER NOT NULL,
            num_neg_received INTEGER NOT NULL,
            snapshot_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guild_id) REFERENCES guilds (id),
            FOREIGN KEY (guild_id, user_id) REFERENCES users (guild_id, user_id)
        )
    """
    )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_db()
    print("Database created successfully.")
