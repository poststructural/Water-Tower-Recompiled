/*
 * settings.ini: the player's options for the Vulkan build.
 *
 * Read once at start-up, before the window and the GPU model exist. Each key
 * maps to the runtime switch that already does the job (NV2A_SCALE and so
 * on), set only when the environment has not set it, so a variable always
 * wins for testing. A missing file is written out with the defaults and a
 * comment per key, so the player has something to edit.
 *
 * Where: settings.ini beside the executable when it is writable (a portable
 * install), else in the save directory.
 */
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "settings.h"

static void set_default(const char *name, const char *value)
{
    if (getenv(name))
        return;
#if defined(_WIN32)
    _putenv_s(name, value);
#else
    setenv(name, value, 0);
#endif
}

static const char DEFAULT_INI[] =
    "; Animaniacs: The Great Edgar Hunt (static recompilation) settings.\n"
    "; Delete this file to get the defaults back.\n"
    "\n"
    "[display]\n"
    "; Window size in pixels at start-up (F11 or Alt+Enter toggles fullscreen).\n"
    "width = 1280\n"
    "height = 960\n"
    "; 0 windowed, 1 fullscreen, 2 borderless fullscreen\n"
    "fullscreen = 0\n"
    "; 1 sync to the display (no tearing), 0 off, 2 adaptive\n"
    "vsync = 1\n"
    "; 1 shows the frame rate (F10 toggles it in game)\n"
    "show_fps = 0\n"
    "\n"
    "[graphics]\n"
    "; Internal render resolution: 1 is the console's 640x480, 2 is 1280x960, up to 4\n"
    "render_scale = 2\n"
    "; Multisample anti-aliasing: 1 (off), 2, 4 or 8\n"
    "msaa = 1\n"
    "; smooth (filtered, mipmapped) or console (as the Xbox drew it)\n"
    "texture_filter = smooth\n"
    "\n"
    "[game]\n"
    "; 1 skips the publisher logos and intro movie at start-up\n"
    "skip_intro = 0\n";

static void apply(AniSettings *s, const char *section, const char *key,
                  const char *val)
{
    int v = atoi(val);

    if (!strcmp(section, "display")) {
        if (!strcmp(key, "width") && v >= 320)       s->width = v;
        else if (!strcmp(key, "height") && v >= 240) s->height = v;
        else if (!strcmp(key, "fullscreen"))         s->fullscreen = v;
        else if (!strcmp(key, "vsync"))              s->vsync = v;
        else if (!strcmp(key, "show_fps") && v)      set_default("NV2A_SHOW_FPS", "1");
    } else if (!strcmp(section, "graphics")) {
        if (!strcmp(key, "render_scale") && v >= 1 && v <= 4)
            set_default("NV2A_SCALE", val);
        else if (!strcmp(key, "msaa") && v > 1)
            set_default("NV2A_MSAA", val);
        else if (!strcmp(key, "texture_filter"))
            set_default("NV2A_TEX_FILTER", val);
    } else if (!strcmp(section, "game")) {
        if (!strcmp(key, "skip_intro"))
            s->skip_intro = v;
    }
}

static char *trim(char *p)
{
    char *e;
    while (isspace((unsigned char)*p))
        p++;
    e = p + strlen(p);
    while (e > p && isspace((unsigned char)e[-1]))
        *--e = 0;
    return p;
}

void ani_settings_load(AniSettings *s, const char *exe_dir, const char *save_dir)
{
    char path[4200], line[512], section[64] = "";
    FILE *f;

    s->width = 1280;
    s->height = 960;
    s->fullscreen = 0;
    s->vsync = 1;
    s->skip_intro = 0;
    set_default("NV2A_SCALE", "2");

    snprintf(path, sizeof path, "%ssettings.ini", exe_dir);
    f = fopen(path, "r");
    if (!f) {
        /* Portable if the exe's folder takes the file, else the save folder. */
        f = fopen(path, "w");
        if (!f) {
            snprintf(path, sizeof path, "%s/settings.ini", save_dir);
            f = fopen(path, "r");
            if (!f)
                f = fopen(path, "w");
            else
                goto parse;
        }
        if (f) {
            fputs(DEFAULT_INI, f);
            fclose(f);
            f = fopen(path, "r");
        }
    }
parse:
    snprintf(s->path, sizeof s->path, "%s", path);
    if (!f)
        return;
    while (fgets(line, sizeof line, f)) {
        char *p = trim(line), *eq;
        if (!*p || *p == ';' || *p == '#')
            continue;
        if (*p == '[') {
            char *e = strchr(p, ']');
            if (e) {
                *e = 0;
                snprintf(section, sizeof section, "%s", trim(p + 1));
            }
            continue;
        }
        eq = strchr(p, '=');
        if (!eq)
            continue;
        *eq = 0;
        apply(s, section, trim(p), trim(eq + 1));
    }
    fclose(f);
}
