#!/usr/bin/env python3
"""Build archipelago/animaniacs/catalog.json from the game's own level data.

Every check comes from the levels' object lists (levels/levelN.lvl inside
resource/levelN.hog): each pickup the game places is an object with a unique
name, and the pickup update (0x00027E00) hands the client that object, so a
check is "this level, this object". The Edgars' slots come from the levels'
RegisterEdgar calls, the door thresholds from their EdgarsNeeded attributes.

    python scripts/survey_ap_catalog.py game/resource          # write catalog.json
    python scripts/survey_ap_catalog.py game/resource --check  # fail if it differs

IDs follow from the data (category, level, order in the level file), so a
re-run gives the same IDs. Needs your own game files; the result is committed
so the apworld and the game build without them.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools" / "hog"))
import hog  # noqa: E402

CATALOG = ROOT / "archipelago" / "animaniacs" / "catalog.json"
BASE = 1095630848
VERSION = 2

# Location ID = BASE + kind * 0x10000 + level * 0x1000 + index.
KINDS = {"edgar": 1, "letter": 2, "script_page": 3, "quest": 4, "collectible": 5,
         "milestone": 6, "apple": 7, "ability": 8}

# LEVELn_NAME in localisation/general_eng.loc.
LEVEL_NAMES = ["The Warner Film Lot", "Ye Old West", "Spooky Movie", "Once Upon A Time",
               "King O'Sullivans Mines", "The Epic"]
# The hub's EdgarsNeeded_* (level0.lvl) open each movie set; each set has one
# more Edgar door of its own (EdgarsNeeded in levelN.lvl).
HUB_DOOR_VARS = [None, "EdgarsNeeded_West", "EdgarsNeeded_Spooky", "EdgarsNeeded_Once",
                 "EdgarsNeeded_Mine", "EdgarsNeeded_Epic"]
COLLECTIBLE = {"filmreels": "Film Reel", "goldnuggets": "Gold Nugget", "pumpkin": "Pumpkin",
               "crown": "Crown", "emerald": "Emerald", "scarab": "Scarab"}
MILESTONE_STEP = 25

# Edgar slots (RegisterEdgar's first argument; the comments beside the calls
# name them). Slots 0 and 1 are the Edgars for 125 and 300 collectibles: one
# copy per room, "edgar_125_NN" / "edgar_300_NN", spawned where you are.
EDGAR_NAMES = {
    0: {2: "Script Page Edgar", 7: "Chicken Boo Edgar"},
    1: {2: "Moody Clan Edgar", 3: "Rescue Dot Edgar", 4: "Rain Dance Edgar",
        5: "Horseshoe Game Edgar", 6: "Rodeo Edgar", 7: "Chicken Boo Edgar"},
    2: {2: "Ghost Hunt Edgar", 3: "Hellcube Edgar", 4: "Fountain Edgar",
        5: "Bride Boss Edgar", 6: "Jock McStrap Edgar", 7: "Chicken Boo Edgar"},
    3: {2: "Bo Peep's Sheep Edgar", 3: "Stinky Witch Edgar", 4: "Miss Muffet Edgar",
        5: "Billy Goats Edgar", 6: "Wagroth Edgar", 7: "Chicken Boo Edgar"},
    4: {2: "Lagoon Edgar", 3: "Monkey Temple Edgar", 4: "Treehouse Edgar",
        5: "Map Room Edgar", 6: "Totem Pole Boss Edgar", 7: "Chicken Boo Edgar"},
    5: {2: "Cleo's Milk Edgar", 3: "Bog Dates Edgar", 4: "Sparty's Slaves Edgar",
        5: "Pipe Mania Edgar", 6: "Chariot Race Edgar", 7: "Chicken Boo Edgar"},
}
LETTERS = {4: "A", 5: "C", 6: "M", 7: "E"}
# Pickup types (0x00027E00 and the counter names at 0x001E39B0, type - 1).
T_MAJOR, T_SCRIPT, T_EDGAR, T_APPLE = 1, 2, 3, 14
QUEST_TYPES = {8, 9, 10, 11, 12, 13, 16, 22}
QUEST_NAMES = {"bone": "Bone", "timber": "Timber", "keypiece": "Key Piece", "feather": "Feather",
               "dates": "Dates", "magnet": "Magnet", "object5_glue": "Glue",
               "object5_blueprints": "Blueprints", "object5_sticks": "Sticks"}

# Abilities (GetAbility, 0x000FCA30, names the bits), where the game hands
# each out, in the order a vanilla playthrough meets them.
ABILITIES = [  # bit, key, name, level, how
    (0x004, "skirt", "Limbo Skirt", 0, "pickup GrassSkirt"),
    (0x100, "suckers", "Suction Cups", 1, "Gold_Prospector_Sequence"),
    (0x020, "dot", "Dot", 1, "RescuedDot"),
    (0x040, "longattack", "Long Shot", 2, "Boogor_Sequence"),
    (0x002, "shovel", "Shovel", 2, "pickup shovel"),
    (0x010, "wakko", "Wakko", 2, "BossDefeated"),
    (0x080, "snorkel", "Snorkel", 3, "Duffy_Sequence"),
    (0x008, "magnifyglass", "Magnifying Glass", 3, "pickup Magnifying_Glass"),
    (0x001, "bomb", "Bomb", 4, "pickup bomb"),
    (0x200, "goggles", "Night Goggles", 4, "LightSwitch04"),
    (0x400, "redstardoor", "Red Star Door", 5, "Dirk_Sequence"),
]
ABILITY_ITEM = {0x001: 1095631104, 0x002: 1095631105, 0x004: 1095631106, 0x008: 1095631107,
                0x010: 1095631108, 0x020: 1095631109, 0x040: 1095631110, 0x080: 1095631111,
                0x100: 1095631112, 0x200: 1095631113, 0x400: 1095631114}


def blocks(text, kind):
    for m in re.finditer(r"\n\t" + kind + r"\r?\n\t\{(.*?)\n\t\}", text, re.S):
        yield m.group(1)


def attr(text, name):
    m = re.search(r"attribute\(\{" + name + r"\}, *(?:[A-Za-z]+, *[A-Za-z]+, *)?([-0-9.]+)",
                  text, re.I)
    return float(m.group(1)) if m else None


def field(text, name):
    m = re.search(name + r"\(\{([^}]*)\}\)", text, re.I)
    return m.group(1) if m else None


def level_files(resource, n):
    data = (resource / f"level{n}.hog").read_bytes()
    out = {}
    for name, off, stored, size in hog.entries(data):
        if name.startswith("levels/") and name.endswith(".lvl"):
            out[name[7:-4].lower()] = hog.read(data, off, stored, size).decode("latin1")
    return out


def survey(resource):
    levels, locations = [], []
    hub = None

    def add(kind, level, index, name, objects, **extra):
        loc = {"id": BASE + KINDS[kind] * 0x10000 + level * 0x1000 + index,
               "name": f"{LEVEL_NAMES[level]}: {name}", "level": level, "kind": kind}
        if objects:
            loc["objects"] = objects
        loc.update(extra)
        locations.append(loc)

    for n in range(6):
        files = level_files(resource, n)
        main = files[f"level{n}"]
        if n == 0:
            hub = main
        # Templates give each object class its type; an instance may amend it.
        tmpl = {k: (attr(v, "objecttype"), attr(v, "PickupType")) for k, v in files.items()}
        objs, linked = [], set()
        for b in blocks(main, "object"):
            cls = (field(b, "Levelname") or "").lower()
            ot, pt = tmpl.get(cls, (None, None))
            ot = attr(b, "objecttype") if attr(b, "objecttype") is not None else ot
            pt = attr(b, "PickupType") if attr(b, "PickupType") is not None else pt
            lk = re.search(r"attribute\(\{LinkedObject\}, *\{([^}]*)\}", b, re.I)
            if lk and lk.group(1) and cls == "digtile":
                linked.add(lk.group(1).lower())
            objs.append((field(b, "objectname"), cls, ot, pt))
        pickups = [(o, cls, int(pt)) for o, cls, ot, pt in objs
                   if ot == 4 and pt is not None and not o.lower().startswith("debug")]

        def dug(o):
            return {"requires": ["shovel"]} if o.lower() in linked else {}

        # Edgars, by slot.
        reg = {}
        for slot, obj in re.findall(r'RegisterEdgar\((\d+), *"([^"]+)"', main):
            if not re.match(r"edgar_(125|300)_", obj, re.I):
                reg[int(slot)] = obj
        coll_cls = next(c for c in COLLECTIBLE if any(cls == c for _, cls, _ in pickups))
        coll = COLLECTIBLE[coll_cls]
        add("edgar", n, 0, f"125 {coll}s Edgar", None, prefix="edgar_125_", slot=0,
            needs_collectibles=125)
        add("edgar", n, 1, f"300 {coll}s Edgar", None, prefix="edgar_300_", slot=1,
            needs_collectibles=300)
        for slot in sorted(reg):
            add("edgar", n, slot, EDGAR_NAMES[n][slot], [reg[slot]], slot=slot, **dug(reg[slot]))
        if n == 0:
            # Beating CC Deville (the lot's boss game, EdgarsToPlayBoss Edgars
            # to start it) hands over the last Edgar without an object, then
            # plays the ending.
            add("edgar", n, 8, "CC Deville Edgar", None, slot=8,
                needs_edgars=int(attr(main, "EdgarsToPlayBoss")), final=True)
        # ACME letters (one each; Spooky Movie places its C twice).
        for t, letter in LETTERS.items():
            names = [o for o, _, pt in pickups if pt == t]
            add("letter", n, t - 4, f"Letter {letter}", names)
        add("script_page", n, 0, "Script Page", [o for o, _, pt in pickups if pt == T_SCRIPT])
        # Quest items, numbered within their kind.
        qi = 0
        seen = {}
        for o, cls, pt in pickups:
            if pt not in QUEST_TYPES:
                continue
            base = re.sub(r"\d+$", "", o.lower())
            label = QUEST_NAMES.get(base, base.title())
            seen[label] = seen.get(label, 0) + 1
            num = re.search(r"(\d+)$", o)
            add("quest", n, qi, f"{label} {int(num.group(1)) if num else seen[label]}"
                if num or seen[label] > 1 else label, [o], **dug(o))
            qi += 1
        # Collectibles, in file order (the ID), named by the number in their
        # object name ("goldnuggets09" and "goldnuggets9" both exist: the
        # second one met gets a "b"), and the milestones.
        ci, named = 0, set()
        for o, cls, pt in pickups:
            if pt == T_MAJOR and cls == coll_cls:
                m = re.search(r"(\d+)$", o)
                label = f"{coll} {int(m.group(1))}" if m else f"{coll} {o}"
                if label in named:
                    label += "b"
                named.add(label)
                add("collectible", n, ci, label, [o], **dug(o))
                ci += 1
        for k in range(1, ci // MILESTONE_STEP + 1):
            add("milestone", n, k, f"{k * MILESTONE_STEP} {coll}s", None,
                count=k * MILESTONE_STEP)
        ai = 0
        for o, cls, pt in pickups:
            if pt == T_APPLE:
                add("apple", n, ai, f"Apple {ai + 1}", [o], **dug(o))
                ai += 1
        levels.append({"index": n, "name": LEVEL_NAMES[n], "collectible": coll,
                       "collectibles": ci,
                       "door_edgars": int(attr(main, "EdgarsNeeded") or 0) if n else 0})

    for lv in levels:
        var = HUB_DOOR_VARS[lv["index"]]
        lv["unlock_edgars"] = int(attr(hub, var)) if var else 0

    abilities = []
    for order, (bit, key, name, level, how) in enumerate(ABILITIES):
        abilities.append({"bit": bit, "key": key, "name": name, "item": ABILITY_ITEM[bit],
                          "level": level, "order": order, "granted_by": how,
                          "location": {"id": BASE + KINDS["ability"] * 0x10000 + level * 0x1000
                                       + bit.bit_length() - 1,
                                       "name": f"{LEVEL_NAMES[level]}: {name}"}})
    return {
        "game": "Animaniacs: The Great Edgar Hunt",
        "catalog_version": VERSION,
        "base_id": BASE,
        "note": "Generated by scripts/survey_ap_catalog.py from the game's level data. "
                "IDs are permanent once released.",
        "edgar_item": {"id": BASE + 1, "name": "Edgar"},
        "filler_item": {"id": BASE + 2, "name": "Applause"},
        "kinds": KINDS,
        "levels": levels,
        "abilities": abilities,
        "locations": locations,
    }


def main():
    resource = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "game" / "resource")
    text = json.dumps(survey(resource), indent=1) + "\n"
    if "--check" in sys.argv:
        if CATALOG.read_text() != text:
            print(f"{CATALOG} differs from the game data", file=sys.stderr)
            return 1
        return 0
    CATALOG.write_text(text)
    print(CATALOG)
    return 0


if __name__ == "__main__":
    sys.exit(main())
