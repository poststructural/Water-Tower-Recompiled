/**
 * The game's side of the Archipelago bridge: guest addresses and layouts
 * read from default.xbe (EU retail, XDK 5849; the US dump has the same code
 * and data). Evidence for each is in docs/ARCHIPELAGO.md.
 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* Current level index; the game's own number is this plus 3. */
#define ANI_G_LEVEL_INDEX     0x00313B54u
#define ANI_G_LEVEL_BIAS      3
/* Progress block (0x106C bytes, what a save holds): six level records. */
#define ANI_G_LEVEL_RECORDS   0x003104D8u
#define ANI_G_LEVEL_RECORD    0x2B4u
#define ANI_G_RECORD_EDGARS   0x2A4u      /* bits 4-7: Edgars found in that level */
/* Ability word: GiveAbility ORs into it (0x0009F840), GetAbility tests it. */
#define ANI_G_ABILITIES       0x00311510u
/* Script variable store of the running level. */
#define ANI_G_SCRIPT_STORE    0x00308158u
/* Pickup objects (0x00027E00): +0x0C the objectname (0x0009C590 looks
 * objects up by it), +0x114 the pickup's state, +0x118 its PickupType. */
#define ANI_G_OBJ_NAME        0x0Cu
#define ANI_G_PICKUP_STATE    0x114u
#define ANI_G_PICKUP_TYPE     0x118u
/* Set when a script hands out an Edgar; the next frame adds it to
 * OscarPickupsCollected and plays "edgarsequence" (0x0009A9EE). */
#define ANI_G_EDGAR_PENDING   0x00308150u

#define ANI_G_LEVELS          6

int ani_game_level(void);                     /* 0..5, or -1 outside a level */
int ani_game_record_edgars(int level);
uint16_t ani_game_abilities(void);
void ani_game_set_abilities(uint16_t bits);
bool ani_game_edgar_pending(void);
uint32_t ani_game_pickup_state(uint32_t obj);
uint32_t ani_game_pickup_type(uint32_t obj);
/* The object's name, copied out; false if it has none. */
bool ani_game_object_name(uint32_t obj, char *out, size_t n);
int ani_stricmp(const char *a, const char *b);
int ani_strnicmp(const char *a, const char *b, size_t n);
/* A float variable of the running level's script store, by name, as the
 * game's own lookup (0x0009C7A0) finds it. */
bool ani_game_script_var(const char *name, float *out);
