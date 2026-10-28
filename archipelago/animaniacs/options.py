from dataclasses import dataclass

from Options import Choice, PerGameCommonOptions, Range, Toggle


class Goal(Choice):
    """edgar_hunt: win once you have received Edgars Required Edgars.
    credits: win by beating CC Deville on the Warner lot, the game's ending (his
    boss game needs 36 Edgars), with at least Edgars Required received."""
    display_name = "Goal"
    option_edgar_hunt = 0
    option_credits = 1
    default = 0


class EdgarsRequired(Range):
    """How many Edgars you need to receive to win. There are 45 in the game: eight
    in each movie set, four on the Warner lot, and CC Deville's."""
    display_name = "Edgars Required"
    range_start = 1
    range_end = 45
    default = 30


class Collectibles(Choice):
    """Each movie set (and the lot) has 300 collectibles: film reels, gold nuggets,
    pumpkins, crowns, emeralds and scarabs.

    none: they are not checks.
    milestones: every 25 collected in a level is a check (72 checks).
    every_one: every single one is a check (1800 checks)."""
    display_name = "Collectibles"
    option_none = 0
    option_milestones = 1
    option_every_one = 2
    default = 1


class Apples(Toggle):
    """Every apple (the health pickups) placed in the levels is a check (253)."""
    display_name = "Apples"


class ShuffleAbilities(Toggle):
    """Put the abilities (Bomb, Shovel, Snorkel and the rest) in the item pool, and
    make the places the game hands them out into checks.

    Experimental: the logic assumes a level's checks can need every ability the game
    hands out up to the end of that level, which has not been confirmed by a
    playthrough. Off keeps the abilities where the game gives them."""
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
    goal: Goal
    edgars_required: EdgarsRequired
    collectibles: Collectibles
    apples: Apples
    shuffle_abilities: ShuffleAbilities
    starting_siblings: StartingSiblings
