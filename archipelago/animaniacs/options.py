from dataclasses import dataclass

from Options import Choice, PerGameCommonOptions, Range, Toggle


class EdgarsRequired(Range):
    """How many Edgars you need to receive to win."""
    display_name = "Edgars Required"
    range_start = 1
    range_end = 36
    default = 30


class ShuffleAbilities(Toggle):
    """Put the abilities (Bomb, Shovel, Snorkel and the rest) in the item pool, and
    make the places the game hands them out into checks.

    Experimental: which level each ability is found in, and which Edgars need it,
    have not been confirmed by a playthrough yet. Off keeps the abilities where the
    game gives them, and only Edgars are shuffled."""
    display_name = "Shuffle Abilities"


class StartingSiblings(Choice):
    """With abilities shuffled: start with Wakko and Dot (start_with), or shuffle
    them like the other abilities (shuffle)."""
    display_name = "Starting Siblings"
    option_start_with = 0
    option_shuffle = 1
    default = 0


@dataclass
class AnimaniacsOptions(PerGameCommonOptions):
    edgars_required: EdgarsRequired
    shuffle_abilities: ShuffleAbilities
    starting_siblings: StartingSiblings
