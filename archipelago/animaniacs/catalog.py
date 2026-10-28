"""Loads catalog.json, the one source of item and location IDs.

catalog.json is built from the game's own level data (scripts/survey_ap_catalog.py),
and the same file generates src/ap/ap_catalog.h for the game
(scripts/gen_ap_catalog.py), so the world and the client cannot disagree on an ID.
"""
import json
import pkgutil
from typing import Dict, List, NamedTuple, Optional


class Ability(NamedTuple):
    bit: int
    key: str
    name: str
    item_id: int
    location_id: int
    location_name: str
    level: int
    order: int          # where a vanilla playthrough meets it


class Level(NamedTuple):
    index: int
    name: str
    collectible: str
    collectibles: int
    unlock_edgars: int  # the hub's Edgar door for this set
    door_edgars: int    # the set's own Edgar door


class Loc(NamedTuple):
    id: int
    name: str
    level: int
    kind: str
    requires: List[str]          # ability keys
    collectibles: int            # collectibles of its level it needs (milestones, 125/300 Edgars)


def _load() -> dict:
    data = pkgutil.get_data(__name__, "catalog.json")
    if data is None:
        raise RuntimeError("catalog.json missing from the animaniacs world")
    return json.loads(data)


RAW = _load()
GAME: str = RAW["game"]
EDGAR = RAW["edgar_item"]["name"]
EDGAR_ID: int = RAW["edgar_item"]["id"]
FILLER = RAW["filler_item"]["name"]
FILLER_ID: int = RAW["filler_item"]["id"]
KINDS: Dict[str, int] = RAW["kinds"]

ABILITIES: List[Ability] = [
    Ability(a["bit"], a["key"], a["name"], a["item"], a["location"]["id"],
            a["location"]["name"], a["level"], a["order"])
    for a in RAW["abilities"]]
LEVELS: List[Level] = [
    Level(lv["index"], lv["name"], lv["collectible"], lv["collectibles"],
          lv["unlock_edgars"], lv["door_edgars"])
    for lv in RAW["levels"]]
LOCATIONS: List[Loc] = [
    Loc(l["id"], l["name"], l["level"], l["kind"], list(l.get("requires", [])),
        l.get("count", l.get("needs_collectibles", 0)))
    for l in RAW["locations"]]

TOTAL_EDGARS = sum(1 for l in LOCATIONS if l.kind == "edgar")
SIBLINGS = ("Wakko", "Dot")

# Collectibles a level has that need the Shovel (dug up from under a dig tile).
DUG: Dict[int, int] = {lv.index: 0 for lv in LEVELS}
for _l in LOCATIONS:
    if _l.kind == "collectible" and "shovel" in _l.requires:
        DUG[_l.level] += 1


def ability(key: str) -> Optional[Ability]:
    return next((a for a in ABILITIES if a.key == key), None)


item_name_to_id: Dict[str, int] = {EDGAR: EDGAR_ID, FILLER: FILLER_ID}
item_name_to_id.update({a.name: a.item_id for a in ABILITIES})

location_name_to_id: Dict[str, int] = {l.name: l.id for l in LOCATIONS}
location_name_to_id.update({a.location_name: a.location_id for a in ABILITIES})
