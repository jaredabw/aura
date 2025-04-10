"""Contains the data models for the aura system."""

from dataclasses import dataclass, field
from enum import Enum


class ReactionEvent(Enum):
    """Enumeration that represents the type of reaction event: `ADD` or `REMOVE`.

    Members
    --------
    ADD: `ReactionEvent`
        Represents the addition of a reaction.
    REMOVE: `ReactionEvent`
        Represents the removal of a reaction.

    Attributes
    ----------
    base: `str`
        The infinitive form of the event.
    present: `str`
        The present participle form of the event.
    past: `str`
        The past participle form of the event.
    is_add: `bool`
        Whether the event is an addition or removal of a reaction.
    """

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
    """Enumeration that represents the type of log event.

    Members
    --------
    MANUAL: `LogEvent`
        Represents a manual change to a user's aura.
    SPAMMING: `LogEvent`
        Represents a user being temporarily banned for spamming reactions.
    DENY_GIVING | DENY_RECEIVING | DENY_BOTH: `LogEvent`
        Represents a user being denied from giving or receiving aura.
    ALLOW_GIVING | ALLOW_RECEIVING | ALLOW_BOTH: `LogEvent`
        Represents a user being allowed to give or receive aura.
    """

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
class GlobalUser:
    """Class that represents a user's global information.

    Attributes
    ----------
    user_id: `int`
        The ID of the user.
    avatar_url: `str`
        The URL of the user's avatar.
    bot: `bool`
        Whether the user is a bot or not."""

    user_id: int = None
    avatar_url: str = None
    bot: bool = False


@dataclass
class User:
    """Class that represents a user in a guild.

    Attributes
    ----------
    aura: `int`
        The user's aura score.
    aura_contribution: `int`
        The user's net aura contribution to other users.
    num_pos_given: `int`
        The number of positive reactions the user has given.
    num_pos_received: `int`
        The number of positive reactions the user has received.
    num_neg_given: `int`
        The number of negative reactions the user has given.
    num_neg_received: `int`
        The number of negative reactions the user has received.
    opted_in: `bool`
        Whether the user has opted in to aura tracking. Defaults to `True`.
    giving_allowed: `bool`
        Whether the user is allowed to give aura. Defaults to `True`.
    receiving_allowed: `bool`
        Whether the user is allowed to receive aura. Defaults to `True`."""

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
    """Class that represents the cooldowns for a user in a guild.

    Attributes
    ----------
    add_cooldown_began: `int`
        The timestamp when the add cooldown began.
    remove_cooldown_began: `int`
        The timestamp when the remove cooldown began."""

    add_cooldown_began: int = 0
    remove_cooldown_began: int = 0


@dataclass
class EmojiReaction:
    """Class that represents an emoji reaction in a guild.

    Attributes
    ----------
    points: `int`
        The number of aura points the reaction gives or takes away."""

    points: int = 0


@dataclass
class Limits:
    """Class that represents the configured limits and cooldowns for a guild.

    All time limits are in seconds.

    Defaults to the following values:
    `interval_long` = 60
    `threshold_long` = 10
    `interval_short` = 15
    `threshold_short` = 5
    `penalty` = 300
    `adding_cooldown` = 10
    `removing_cooldown` = 10

    Attributes
    ----------
    interval_long: `int`
        The long interval for the reaction limit.
    threshold_long: `int`
        The threshold for the long interval.
    interval_short: `int`
        The short interval for the reaction limit.
    threshold_short: `int`
        The threshold for the short interval.
    penalty: `int`
        The penalty for exceeding the limits.
    adding_cooldown: `int`
        The cooldown for adding reactions.
    removing_cooldown: `int`
        The cooldown for removing reactions."""

    interval_long: int = 60
    threshold_long: int = 10
    interval_short: int = 15
    threshold_short: int = 5
    penalty: int = 300
    adding_cooldown: int = 10
    removing_cooldown: int = 10


@dataclass
class Guild:
    """Class that represents a guild.

    Attributes
    ----------
    users: `Dict[int, User]`
        A dictionary of users in the guild, where the key is the user ID and the value is a `User` object.
    reactions: `Dict[str, EmojiReaction]`
        A dictionary of emoji reactions in the guild, where the key is the emoji and the value is an `EmojiReaction` object.
    info_msg_id: `int`
        The ID of the message that contains the emoji list.
    board_msg_id: `int`
        The ID of the message that contains the leaderboard.
    msgs_channel_id: `int`
        The ID of the channel where the leaderboard and emoji list are displayed.
    log_channel_id: `int`
        The ID of the channel where aura changes are logged.
    last_update: `int`
        The timestamp of the last update to the guild data."""

    users: dict[int, User] = field(default_factory=dict)
    reactions: dict[str, EmojiReaction] = field(default_factory=dict)
    info_msg_id: int = None
    board_msg_id: int = None
    msgs_channel_id: int = None
    log_channel_id: int = None
    last_update: int = None
    limits: Limits = field(default_factory=Limits)
