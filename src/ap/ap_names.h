/**
 * Other games' item and location names, for the popups ("Hookshot for Sam").
 * They come from the server's data packages, and are cached on disk by game
 * and checksum (<dir>/<game>_<checksum>.json) so a room is only asked for the
 * games it hasn't sent before. Game thread only.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

#include "ap_json.h"

void ani_names_reset(void);
/* Loads every cached package in dir. */
void ani_names_load(const char *dir);
bool ani_names_have(const char *game, const char *checksum);
/* One game's entry of a DataPackage (item_name_to_id, location_name_to_id,
 * checksum). Written to dir as well when dir is not NULL. False if malformed. */
bool ani_names_add(const char *game, const AjValue *pkg, const char *dir);
const char *ani_names_item(const char *game, int64_t id);      /* NULL if unknown */
const char *ani_names_location(const char *game, int64_t id);
