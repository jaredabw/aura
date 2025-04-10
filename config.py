UPDATE_INTERVAL = 10  # how often to update the leaderboard
LOGGING_INTERVAL = 10  # how often to send logs

OWNER_ID = 355938178265251842
OWNER_DM_CHANNEL_ID = 1356159596347129897

DB = "aura_data.db"  # database file name

HELP_TEXT = """Aura tracks emoji reactions and gives aura points to people based on the reactions they receive.

__**SETUP:**__
1. Run </setup:1356179831288758384>. If you want a live leaderboard, create a new channel and provide it.
2. Run </logging:1356254831488139457> to set a channel for aura changes to be logged to. This is highly recommended, in the case of anyone spamming or being unfair. 
3. Add your emojis with </emoji add:1356180634602700863>, and specify their aura points impact.
4. Watch the leaderboard in the new channel, or run </leaderboard:1356179831288758387> to see it!

__**MOD COMMANDS**__:
- </setup:1356179831288758384> - Setup the bot for your server. Initialises the bot and optionally allows you to specify a channel to display the leaderboard. By default, ⭐ (+1) and 💀 (-1) are added. _Permission:_ `Manage Channels`.  
- </delete:1356179831288758386> - Delete all bot data for this server. Removes all tracked data, including emojis, leaderboards, and logs. _Permission:_ `Administrator`.  
- </changeaura:1356559832605392980> - Change a user's aura by a specified amount. Allows administrators to manually adjust a user's aura score by adding or subtracting points. Used for correcting errors or rewarding users. _Permission:_ `Administrator`.  
- </updatechannel:1356179831288758385> - Update or add the leaderboard display channel. The leaderboard and emoji list will be resent in the new channel. Ensure the bot has permission to send messages in the specified channel. _Permission:_ `Manage Channels`.  
- </logging:1356254831488139457> - Enable or disable aura change logging. Specify a channel to enable logging of aura changes. If the channel argument is empty, logging will be disabled. Logs are sent in batches every 10 seconds to avoid spamming. Ensure the bot has permission to send messages in the specified channel. _Permission:_ `Manage Channels`.  
- </emoji add:1356180634602700863> - Add an emoji to tracking. Specify an emoji and its aura points impact (positive or negative). _Permission:_ `Manage Channels`.  
- </emoji remove:1356180634602700863> - Remove an emoji from tracking. Stops tracking the specified emoji and removes its aura impact. _Permission:_ `Manage Channels`.  
- </emoji update:1356180634602700863> - Update the points of a tracked emoji. For example, you can change ⭐ from +1 to +2. _Permission:_ `Manage Channels`.  
- </deny:1356559832605392981> - Deny a user from giving or receiving aura. Restricts a user from giving, receiving, or both. _Permission:_ `Manage Channels`.  
- </allow:1356559832605392982> - Allow a user to give or receive aura. Lifts restrictions on a user, allowing them to give, receive, or both. _Permission:_ `Manage Channels`.  
- </config view:1357013094781685821> - See the bot's timers, thresholds and cooldowns for this server. _Permission:_ `Manage Channels`. 
- </config edit:1357013094781685821> - Adjust these values for this server. It is highly recommended to leave the values as their defaults, unless you know what you are doing. _Permission:_ `Manage Channels`. 
- </config reset:1357013094781685821> - Set the config values back to default. _Permission:_ `Manage Channels`. 
- </clear emojis:1357026159350780189> - Clear all emojis and their associated aura impacts from this server. _Permission:_ `Administrator`. 
- </clear users:1357026159350780189> - Clear all user data, such as aura and number of reactions. Wipes the leaderboard. _Permission:_ `Administrator`. 
|
__**GENERAL COMMANDS**__:
- </help:1356273217890816000> - This command. Gives information about the bot.  
- </leaderboard:1356179831288758387> - Display the current leaderboard. The leaderboard in your specified channel updates automatically, but you can use this command to view it manually.  
- </aura:1356559832605392979> - Check your or another user's aura and other info. If no user is specified, it displays your own info.  
- </emoji list:1356180634602700863> - List all tracked emojis with their aura points impact.  
- </opt in:1356593461914108076> - Opt in to aura tracking. Users are opted in by default.  
- </opt out:1356593461914108076> - Opt out of aura tracking. Hides you from the leaderboard.  

__**INFO:**__
- All reactions are counted when multiple people put the same reaction on a message.
- You require Manage Channels permissions to run commands that affect the setup.
- Emoji must be standard emoji or emoji from this server.
- Implements two spam filters: 
  - 10 second cooldown on giving aura (per server user recipient combination); ignored if a user removed their reaction, i.e. put the wrong reaction, removed it, and added the correct reaction.  
  - Temporary bans from giving aura for excessive reaction additions and/or removals in a short period of time.
  - These values are configurable at your discretion.
- If you are getting the error "A specified channel ID is invalid" when trying to use /setup or /updatechannel, try running the command on PC."""
