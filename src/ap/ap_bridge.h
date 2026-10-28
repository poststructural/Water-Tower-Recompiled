/**
 * In-process Archipelago client for the recompiled game (modelled on
 * crackdown-recomp's src/ap/): the connection runs on its own thread, and
 * everything that touches the game runs on the game thread, from the hooks
 * in recomp_manual.c.
 *
 * Enabled by --ap-server HOST[:PORT] --ap-slot NAME (or ANI_AP_SERVER /
 * ANI_AP_SLOT; the password comes from ANI_AP_PASSWORD or --ap-password).
 * Without them every hook calls straight through and the game is vanilla.
 */
#pragma once
#include <stdbool.h>

typedef void (*ani_gen_fn)(void);

/* Before the kernel's path setup. Removes the --ap-* arguments it consumed
 * from argv. Returns the save directory to use for this seed (each seed gets
 * its own, so one seed's progress never leaks into another), or NULL to keep
 * save_dir. */
const char *ani_ap_init(int *argc, char **argv, const char *save_dir);
bool ani_ap_active(void);

/* Once per main-loop iteration (0x000B09A0, menus included): network and
 * item grants. */
void ani_ap_main_loop(void);

/* Hooks. Each runs the generated body itself (gen) when it should. */
void ani_ap_hook_frame(ani_gen_fn gen);          /* 0x0009A9C0 game update */
void ani_ap_hook_pickup(ani_gen_fn gen);         /* 0x00027E00 pickup update */
void ani_ap_hook_give_ability(ani_gen_fn gen);   /* 0x0009F840 GiveAbility */
void ani_ap_hook_get_all_edgars(ani_gen_fn gen); /* 0x000FD450 GetAllEdgars */
void ani_ap_hook_credits(ani_gen_fn gen);        /* 0x000FC730 SetReadyForCredits */
