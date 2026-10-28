/* The Archipelago overlay on screen (ap_hud.c): which parts are on, from
 * settings.ini's [archipelago] section. Vulkan build only. */
#pragma once
#include <stdbool.h>

void ani_hud_configure(bool notifications, bool tracker, bool counter);
