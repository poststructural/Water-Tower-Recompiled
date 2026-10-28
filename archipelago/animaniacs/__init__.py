"""Archipelago world for Animaniacs: The Great Edgar Hunt (Xbox), played through the
static recompilation at https://gitlab.com/unowa001/animaniacs-remastered.

The client lives inside the recompiled executable (src/ap/); there is no separate
client program. Every pickup the game places can be a check: the 44 Edgars, the
ACME letters, the script pages, the quest items, the collectibles and the apples.
The Edgars you receive are what open the movie sets.
"""
from typing import Any, Callable, Dict, List, Set

from BaseClasses import CollectionState, Item, ItemClassification, Location, Region, Tutorial
from worlds.AutoWorld import WebWorld, World

from . import catalog
from .catalog import ABILITIES, DUG, EDGAR, FILLER, LEVELS, LOCATIONS, SIBLINGS
from .options import AnimaniacsOptions

SLOT_DATA_VERSION = 2
GOAL_CREDITS = 1


class AnimaniacsItem(Item):
    game = catalog.GAME


class AnimaniacsLocation(Location):
    game = catalog.GAME


class AnimaniacsWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "Setting up the Animaniacs recompilation for Archipelago.",
        "English", "setup_en.md", "setup/en", ["Unowa001"])]


def _groups() -> Dict[str, Set[str]]:
    groups: Dict[str, Set[str]] = {lv.name: set() for lv in LEVELS}
    labels = {"edgar": "Edgars", "letter": "ACME Letters", "script_page": "Script Pages",
              "quest": "Quest Items", "collectible": "Collectibles",
              "milestone": "Collectible Milestones", "apple": "Apples"}
    for loc in LOCATIONS:
        groups[LEVELS[loc.level].name].add(loc.name)
        groups.setdefault(labels[loc.kind], set()).add(loc.name)
    for a in ABILITIES:
        groups[LEVELS[a.level].name].add(a.location_name)
        groups.setdefault("Abilities", set()).add(a.location_name)
    return groups


class AnimaniacsWorld(World):
    """Yakko, Wakko and Dot hunt for the stolen Edgar awards across the Warner Bros.
    studio lot and its movie sets."""
    game = catalog.GAME
    web = AnimaniacsWeb()
    options_dataclass = AnimaniacsOptions
    options: AnimaniacsOptions
    item_name_to_id = catalog.item_name_to_id
    location_name_to_id = catalog.location_name_to_id
    item_name_groups = {"Abilities": {a.name for a in ABILITIES}}
    location_name_groups = _groups()

    # ── Options ─────────────────────────────────────────────────────────

    def _kinds(self) -> List[str]:
        kinds = ["edgar", "letter", "script_page", "quest"]
        if self.options.collectibles == self.options.collectibles.option_milestones:
            kinds.append("milestone")
        elif self.options.collectibles == self.options.collectibles.option_every_one:
            kinds.append("collectible")
        if self.options.apples:
            kinds.append("apple")
        if self._shuffled_abilities():
            kinds.append("ability")
        return kinds

    def _shuffled_abilities(self) -> List[catalog.Ability]:
        if not self.options.shuffle_abilities:
            return []
        if self.options.starting_siblings == self.options.starting_siblings.option_start_with:
            return [a for a in ABILITIES if a.name not in SIBLINGS]
        return list(ABILITIES)

    def _starting(self) -> List[str]:
        if self.options.shuffle_abilities and \
                self.options.starting_siblings == self.options.starting_siblings.option_start_with:
            return list(SIBLINGS)
        return []

    # ── Logic ───────────────────────────────────────────────────────────
    #
    # A movie set opens at the hub's Edgar door for it. Each set has one more
    # Edgar door of its own, and which checks are behind it is not known, so
    # every check in a set counts as needing that door too. An ability the
    # game hands out where it always does counts as had once its set's door
    # can be passed; a shuffled one is an item. With abilities shuffled, a
    # set's checks count as needing every ability the game gives up to the end
    # of that set.

    def _edgars_for(self, level: int) -> int:
        lv = LEVELS[level]
        return max(lv.unlock_edgars, lv.door_edgars)

    def _ability_rule(self, key: str) -> Callable[[CollectionState], bool]:
        a = catalog.ability(key)
        player = self.player
        if a.name in {s.name for s in self._shuffled_abilities()} or a.name in self._starting():
            return lambda state: state.has(a.name, player)
        need = self._edgars_for(a.level)
        return lambda state: state.has(EDGAR, player, need)

    def _rule(self, level: int, requires: List[str], before_order: int = None):
        player = self.player
        need = self._edgars_for(level)
        shuffled = self._shuffled_abilities()
        names = [a.name for a in shuffled
                 if (a.order < before_order if before_order is not None else a.level <= level)]
        extra = [self._ability_rule(k) for k in requires]
        return lambda state: state.has(EDGAR, player, need) and state.has_all(names, player) \
            and all(r(state) for r in extra)

    def _location_rule(self, loc: catalog.Loc):
        requires = list(loc.requires)
        # A milestone (or a 125/300 Edgar) past the collectibles out in the open
        # needs the ones under the dig tiles too.
        if loc.collectibles and loc.collectibles > LEVELS[loc.level].collectibles - DUG[loc.level]:
            requires.append("shovel")
        return self._rule(loc.level, requires)

    # ── Generation ──────────────────────────────────────────────────────

    def generate_early(self) -> None:
        for name in self._starting():
            self.multiworld.push_precollected(self.create_item(name))

    def create_item(self, name: str) -> AnimaniacsItem:
        cls = ItemClassification.filler if name == FILLER else ItemClassification.progression
        return AnimaniacsItem(name, cls, self.item_name_to_id[name], self.player)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        kinds = set(self._kinds())
        shuffled = {a.name for a in self._shuffled_abilities()}
        for lv in LEVELS:
            region = Region(lv.name, self.player, self.multiworld)
            for loc in LOCATIONS:
                if loc.level == lv.index and loc.kind in kinds:
                    l = AnimaniacsLocation(self.player, loc.name, loc.id, region)
                    l.access_rule = self._location_rule(loc)
                    region.locations.append(l)
            for a in ABILITIES:
                if a.level == lv.index and a.name in shuffled:
                    l = AnimaniacsLocation(self.player, a.location_name, a.location_id, region)
                    l.access_rule = self._rule(lv.index, [], before_order=a.order)
                    region.locations.append(l)
            self.multiworld.regions.append(region)
            need = lv.unlock_edgars
            player = self.player
            menu.connect(region, f"Open {lv.name}", lambda state, n=need: state.has(EDGAR, player, n))

    def create_items(self) -> None:
        pool = [self.create_item(a.name) for a in self._shuffled_abilities()]
        pool += [self.create_item(EDGAR) for _ in range(catalog.TOTAL_EDGARS)]
        missing = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        pool += [self.create_item(FILLER) for _ in range(missing)]
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        need = min(int(self.options.edgars_required), catalog.TOTAL_EDGARS)
        player = self.player
        if self.options.goal == GOAL_CREDITS:
            final = self._rule(len(LEVELS) - 1, [])
            self.multiworld.completion_condition[player] = \
                lambda state: state.has(EDGAR, player, need) and final(state)
        else:
            self.multiworld.completion_condition[player] = lambda state: state.has(EDGAR, player, need)

    def get_filler_item_name(self) -> str:
        return FILLER

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "version": SLOT_DATA_VERSION,
            "catalog_version": catalog.RAW["catalog_version"],
            "goal": int(self.options.goal),
            "edgars_required": int(self.options.edgars_required),
            "location_kinds": [catalog.KINDS[k] for k in self._kinds()],
            "shuffle_abilities": bool(self.options.shuffle_abilities),
            "shuffled_abilities": [a.bit for a in self._shuffled_abilities()],
            # Received at the start (precollected) and forced on by the client.
            "start_abilities": [a.bit for a in ABILITIES if a.name in self._starting()],
        }
