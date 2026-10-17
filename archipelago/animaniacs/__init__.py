"""Archipelago world for Animaniacs: The Great Edgar Hunt (Xbox), played through the
static recompilation at https://github.com/Unowa001/AnimaniacsRecompiled.

The client lives inside the recompiled executable (src/ap/); there is no separate
client program. Every Edgar statuette you pick up sends a check, and the Edgars you
receive are what opens the movie sets.
"""
from typing import Any, Dict, List

from BaseClasses import Item, ItemClassification, Location, Region, Tutorial
from worlds.AutoWorld import WebWorld, World

from . import catalog
from .catalog import ABILITIES, EDGAR, FILLER, LEVELS, SIBLINGS
from .options import AnimaniacsOptions

SLOT_DATA_VERSION = 1


class AnimaniacsItem(Item):
    game = catalog.GAME


class AnimaniacsLocation(Location):
    game = catalog.GAME


class AnimaniacsWeb(WebWorld):
    tutorials = [Tutorial(
        "Multiworld Setup Guide",
        "Setting up the Animaniacs recompilation for Archipelago.",
        "English", "setup_en.md", "setup/en", ["Unowa001"])]


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
    location_name_groups = {lv.name: set(lv.edgar_locations) for lv in LEVELS}

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

    def generate_early(self) -> None:
        for name in self._starting():
            self.multiworld.push_precollected(self.create_item(name))

    def create_item(self, name: str) -> AnimaniacsItem:
        if name == FILLER:
            cls = ItemClassification.filler
        else:
            cls = ItemClassification.progression
        return AnimaniacsItem(name, cls, self.item_name_to_id[name], self.player)

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        self.multiworld.regions.append(menu)
        shuffled = {a.name for a in self._shuffled_abilities()}
        for lv in LEVELS:
            region = Region(lv.name, self.player, self.multiworld)
            for name, loc_id in lv.edgar_locations.items():
                region.locations.append(AnimaniacsLocation(self.player, name, loc_id, region))
            for a in ABILITIES:
                if a.level == lv.index and a.name in shuffled:
                    region.locations.append(
                        AnimaniacsLocation(self.player, a.location_name, a.location_id, region))
            self.multiworld.regions.append(region)
            menu.connect(region, f"Open {lv.name}", self._level_rule(lv))

    def _level_rule(self, lv: catalog.Level):
        player, edgars = self.player, lv.unlock_edgars
        # Abilities a level's checks need only count when abilities are shuffled;
        # otherwise the game hands them out where it always does.
        needs = [n for n in lv.requires if n in {a.name for a in self._shuffled_abilities()}]
        return lambda state: state.has(EDGAR, player, edgars) and state.has_all(needs, player)

    def create_items(self) -> None:
        pool = [self.create_item(a.name) for a in self._shuffled_abilities()]
        pool += [self.create_item(EDGAR) for _ in range(catalog.TOTAL_EDGARS)]
        missing = len(self.multiworld.get_unfilled_locations(self.player)) - len(pool)
        pool += [self.create_item(FILLER) for _ in range(missing)]
        self.multiworld.itempool += pool

    def set_rules(self) -> None:
        need = min(int(self.options.edgars_required), catalog.TOTAL_EDGARS)
        player = self.player
        self.multiworld.completion_condition[player] = lambda state: state.has(EDGAR, player, need)

    def get_filler_item_name(self) -> str:
        return FILLER

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "version": SLOT_DATA_VERSION,
            "catalog_version": catalog.RAW["catalog_version"],
            "edgars_required": int(self.options.edgars_required),
            "shuffle_abilities": bool(self.options.shuffle_abilities),
            "shuffled_abilities": [a.bit for a in self._shuffled_abilities()],
            # Received at the start (precollected) and forced on by the client.
            "start_abilities": [a.bit for a in ABILITIES if a.name in self._starting()],
        }
