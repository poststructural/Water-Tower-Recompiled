/* settings.ini for the Vulkan build (src/settings.c). */
#ifndef ANI_SETTINGS_H
#define ANI_SETTINGS_H

typedef struct AniSettings {
    int width, height;
    int fullscreen;     /* 0 window, 1 fullscreen, 2 borderless */
    int vsync;          /* 0 off, 1 on, 2 adaptive */
    int skip_intro;
    char path[4200];    /* where the file was read from */
} AniSettings;

/* exe_dir ends in a separator; save_dir does not. */
void ani_settings_load(AniSettings *s, const char *exe_dir, const char *save_dir);

#endif
