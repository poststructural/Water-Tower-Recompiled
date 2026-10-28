/* settings.ini for the Vulkan build (src/settings.c). docs/SETTINGS.md lists
 * every key, for the launcher and for players editing the file by hand. */
#ifndef ANI_SETTINGS_H
#define ANI_SETTINGS_H

enum { ANI_WINDOWED = 0, ANI_FULLSCREEN = 1, ANI_BORDERLESS = 2 };

typedef struct AniSettings {
    /* [display] */
    int width, height;      /* window size; 0x0 = the monitor's resolution */
    int mode;               /* ANI_WINDOWED / ANI_FULLSCREEN / ANI_BORDERLESS */
    double aspect;          /* picture shape; 0 = the monitor's */
    int vsync;              /* 0 off, 1 on, 2 adaptive */
    int show_fps;
    int hud_stretch;        /* 0 = 2D keeps its 4:3 shape on wide pictures */
    /* [graphics] */
    int render_scale;       /* 0 = auto: enough for the output resolution */
    int max_render_scale;   /* cap for auto */
    int msaa;               /* 1, 2, 4, 8 */
    char texture_filter[16];
    /* [game] */
    int skip_intro;
    /* [archipelago]: the in-game overlay during a session */
    int ap_notifications, ap_tracker, ap_hud, ap_chat;
    char path[4200];        /* where the file was read from */
} AniSettings;

/* exe_dir ends in a separator; save_dir does not. */
void ani_settings_load(AniSettings *s, const char *exe_dir, const char *save_dir);

/* The render scale for a picture of out_w x out_h pixels: the smallest whole
 * multiple of 640x480 at least as large on both axes, so the picture is never
 * magnified (the framebuffer stays 4:3 and is drawn wider for widescreen). */
int ani_settings_auto_scale(int out_w, int out_h, int cap);

#endif
