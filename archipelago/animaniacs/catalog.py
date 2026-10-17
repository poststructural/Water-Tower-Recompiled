"""Loads catalog.json, the one source of item and location IDs.

The same file generates src/ap/ap_catalog.h for the game (scripts/gen_ap_catalog.py),
so the world and the client cannot disagree on an ID.
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


class Level(NamedTuple):
    index: int
    name: str
    unlock_edgars: int
    requires: List[str]
    edgar_locations: Dict[str, int]  # name -> id, in ordinal order


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

ABILITIES: List[Ability] = [
    Ability(a["bit"], a["key"], a["name"], a["item"], a["location"]["id"],
            a["location"]["name"], a["level"])
    for a in RAW["abilities"]]
LEVELS: List[Level] = [
    Level(lv["index"], lv["name"], lv["unlock_edgars"], list(lv["requires"]),
          {loc["name"]: loc["id"] for loc in lv["edgar_locations"]})
    for lv in RAW["levels"]]

TOTAL_EDGARS = sum(len(lv.edgar_locations) for lv in LEVELS)
SIBLINGS = ("Wakko", "Dot")


def ability(name: str) -> Optional[Ability]:
    return next((a for a in ABILITIES if a.name == name), None)


item_name_to_id: Dict[str, int] = {EDGAR: EDGAR_ID, FILLER: FILLER_ID}
item_name_to_id.update({a.name: a.item_id for a in ABILITIES})

location_name_to_id: Dict[str, int] = {}
for _lv in LEVELS:
    location_name_to_id.update(_lv.edgar_locations)
location_name_to_id.update({a.location_name: a.location_id for a in ABILITIES})
