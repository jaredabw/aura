# Aura Bot

Aura Bot is a Discord bot that allows a server to have a leaderboard of 'aura', similar to Reddit karma. Moderators must assign a 'delta' to reactions that are to be tracked. This delta will be added to a user's score when they receive this reaction.

## Features
- Track emoji reactions and assign points (positive or negative) to users.
- Display a leaderboard of users based on their scores.
- Manage tracked emojis (add, remove, or update).
- Use default emojis or emojis from each server.
- Automatically update leaderboards at regular intervals.
- Easy setup and configuration for each server.

## Usage
1. Add bot to your server.
2. Run `/setup` with the optional argument being the channel for the live leaderboard.
3. Use `/emoji add` to add an emoji and its delta.
4. Watch your scores on the leaderboard!