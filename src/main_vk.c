/**
 * Animaniacs: The Great Edgar Hunt - recompiled game entry point, Vulkan runtime.
 *
 * The boot of main.c, against ngbrecomp's xboxrecomp fork: xemu's NV2A model
 * and Vulkan renderer execute the title's pushbuffers on the GPU (instead of
 * the CPU rasteriser), guest threads run on one virtual CPU, and audio and
 * input go through SDL2. Adapted from ngbrecomp's src/main.c.
 *
 * Game data: a "game" directory next to the executable (default.xbe,
 * resource/, movies/, tkaXBoxDSPImage.bin), ANI_GAME_DIR, or argv[1].
 * Saves: ANI_SAVE_DIR, else %LOCALAPPDATA%/AnimaniacsRecompiled.
 * Archipelago: --ap-server HOST:PORT --ap-slot NAME (docs/ARCHIPELAGO.md).
 *
 * Renderer: ANI_RENDERER=xemu (default, a window), null (no window).
 */

#if defined(_WIN32)
#include <windows.h>
#include <dbghelp.h>
#include <mmsystem.h>
#include <unistd.h>
#include <pthread.h>
#else
#define _GNU_SOURCE
#include <pthread.h>
#include <unistd.h>
#include "platform/win32_compat.h"
#endif
#include "platform/vcpu.h"
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>

#include <xbox/xboxrecomp.h>
#include "usb/ohci.h"
#include "nv2a_vk_runtime.h"
#include "nv2a_window.h"
#include "settings.h"
#include "ap/ap_hud.h"
#define SDL_MAIN_HANDLED   /* our own main(), not SDL_main */
#include <SDL.h>
#include "ap/ap_bridge.h"

extern void xbox_InputInit(void);

extern RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp;
extern RECOMP_TLS uint32_t g_ebx, g_esi, g_edi;
extern ptrdiff_t g_xbox_mem_offset;

#define ANI_ENTRY_POINT 0x0010A26Au

extern void xbe_entry_point(void);
extern int recomp_dispatch_init(void);

static char s_game_dir[4096];
static char s_save_dir[4096];
static bool s_headless;
static AniSettings s_settings;

/* Create a directory and its parents (the save folder on first run). */
static void ani_mkdirs(const char *path)
{
    char buf[4096];
    snprintf(buf, sizeof buf, "%s", path);
    for (char *p = buf + 1; *p; p++) {
        if (*p == '/' || *p == '\\') {
            char c = *p;
            *p = 0;
            CreateDirectoryA(buf, NULL);
            *p = c;
        }
    }
    CreateDirectoryA(buf, NULL);
}

/* ── Crash reporting ───────────────────────────────────────── */

static void print_host_symbol(FILE *out, void *rip)
{
#if defined(_WIN32)
    char buf[sizeof(SYMBOL_INFO) + 256];
    SYMBOL_INFO *sym = (SYMBOL_INFO *)buf;
    DWORD64 disp = 0;

    memset(buf, 0, sizeof(buf));
    sym->SizeOfStruct = sizeof(SYMBOL_INFO);
    sym->MaxNameLen = 255;
    if (SymFromAddr(GetCurrentProcess(), (DWORD64)(uintptr_t)rip, &disp, sym))
        fprintf(out, "  in %s+0x%llX\n", sym->Name, (unsigned long long)disp);
#else
    (void)out;
    (void)rip;
#endif
}

static void print_guest_stack(FILE *out)
{
    const uint32_t *sp;
    int i, shown = 0;

    if (!g_xbox_mem_offset || !g_esp)
        return;
    sp = (const uint32_t *)((uintptr_t)g_xbox_mem_offset + g_esp);
    fprintf(out, "  guest stack (return addresses, innermost first):\n");
    for (i = 0; i < 256 && shown < 24; i++) {
        uint32_t v = sp[i];
        if (v > g_xbox_code_lo && v < g_xbox_code_hi) {
            fprintf(out, "    [esp+%-4d] 0x%08X\n", i * 4, v);
            shown++;
        }
    }
}

/* The emulated APU's registers are unmapped under RECOMP_AC97_READY and
 * every access arrives here. */
typedef struct MCPXAPUState MCPXAPUState;
extern MCPXAPUState *mcpx_apu_init_standalone(uint8_t *ram_ptr);
extern MCPXAPUState *g_apu_state;
extern bool apu_hook_handle_mmio(PCONTEXT ctx, uintptr_t fault_addr,
                                 uint32_t fault_xbox_va, int is_write);
#define APU_TRAP_BASE 0xFE800000u
#define APU_TRAP_END  0xFE880000u

static LONG CALLBACK veh_handler(PEXCEPTION_POINTERS ep)
{
    uintptr_t fault_addr;
    uint32_t xbox_va;
    int is_write;

#if defined(_WIN32) && XBOX_HAS_VCPU
    vcpu_win_unredirect(ep);
#endif
    if (ep->ExceptionRecord->ExceptionCode != EXCEPTION_ACCESS_VIOLATION)
        return EXCEPTION_CONTINUE_SEARCH;

    fault_addr = ep->ExceptionRecord->ExceptionInformation[1];
    is_write = ep->ExceptionRecord->ExceptionInformation[0] ? 1 : 0;
    xbox_va = (uint32_t)(fault_addr - (uintptr_t)g_xbox_mem_offset);

    if (g_apu_state && xbox_va >= APU_TRAP_BASE && xbox_va < APU_TRAP_END
            && apu_hook_handle_mmio(ep->ContextRecord, fault_addr, xbox_va, is_write))
        return EXCEPTION_CONTINUE_EXECUTION;
    if (xbox_OhciOwnsAddress(xbox_va) &&
        xbox_OhciHandleMmio(ep->ContextRecord, xbox_va))
        return EXCEPTION_CONTINUE_EXECUTION;

    fprintf(stderr, "[CRASH] Access violation at RIP=0x%llX, fault addr=0x%llX (%s)\n",
            (unsigned long long)ep->ContextRecord->Rip,
            (unsigned long long)fault_addr, is_write ? "write" : "read");
    fprintf(stderr, "  Xbox VA of fault: 0x%08X\n", xbox_va);
    fprintf(stderr, "  Xbox regs: eax=%08X ecx=%08X edx=%08X ebx=%08X\n",
            g_eax, g_ecx, g_edx, g_ebx);
    fprintf(stderr, "             esi=%08X edi=%08X esp=%08X\n", g_esi, g_edi, g_esp);
    print_host_symbol(stderr, (void *)(uintptr_t)ep->ContextRecord->Rip);
    print_guest_stack(stderr);
    fflush(stderr);
    return EXCEPTION_CONTINUE_SEARCH;
}

static void save_dir_path(char *out, size_t n);

/* Nothing handled the exception: the game is going down. Write crash.txt
 * beside log.txt, say where it is, and end the process. */
static LONG WINAPI crash_filter(PEXCEPTION_POINTERS ep)
{
    static volatile LONG once;
    char path[4200], msg[4600];
    FILE *f;

    if (InterlockedExchange(&once, 1))
        return EXCEPTION_EXECUTE_HANDLER;
    save_dir_path(path, sizeof path - 16);
    strcat(path, "/crash.txt");
    f = fopen(path, "w");
    if (f) {
        SYSTEMTIME t;
        GetLocalTime(&t);
        fprintf(f, "Animaniacs Recompiled %s crashed, %04d-%02d-%02d %02d:%02d:%02d\n\n",
                ANI_VERSION, t.wYear, t.wMonth, t.wDay, t.wHour, t.wMinute, t.wSecond);
        fprintf(f, "Exception 0x%08lX at 0x%llX",
                ep->ExceptionRecord->ExceptionCode,
                (unsigned long long)ep->ContextRecord->Rip);
        if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
            uintptr_t a = ep->ExceptionRecord->ExceptionInformation[1];
            fprintf(f, ", %s of 0x%llX",
                    ep->ExceptionRecord->ExceptionInformation[0] ? "write" : "read",
                    (unsigned long long)a);
            if (a - (uintptr_t)g_xbox_mem_offset < 0x10000000u)
                fprintf(f, " (Xbox 0x%08X)", (uint32_t)(a - (uintptr_t)g_xbox_mem_offset));
        }
        fprintf(f, "\n");
        print_host_symbol(f, (void *)(uintptr_t)ep->ContextRecord->Rip);
        fprintf(f, "  Xbox regs: eax=%08X ecx=%08X edx=%08X ebx=%08X\n",
                g_eax, g_ecx, g_edx, g_ebx);
        fprintf(f, "             esi=%08X edi=%08X esp=%08X\n", g_esi, g_edi, g_esp);
        print_guest_stack(f);
        fprintf(f, "\nPlease attach this file and log.txt (same folder) to a bug report.\n");
        fclose(f);
    }
    fprintf(stderr, "[CRASH] report written to %s\n", path);
    fflush(stderr);
    snprintf(msg, sizeof msg,
             "The game crashed and has to close.\n\n"
             "A report was saved to:\n%s\n\n"
             "Please attach it and log.txt from the same folder to a bug report.",
             path);
    MessageBoxA(NULL, msg, "Animaniacs Recompiled", MB_OK | MB_ICONERROR);
    return EXCEPTION_EXECUTE_HANDLER;
}

/* ── Paths ─────────────────────────────────────────────────── */

static void exe_dir(char *out, size_t n)
{
    char *slash;
#if defined(_WIN32)
    DWORD len = GetModuleFileNameA(NULL, out, (DWORD)n);
    if (!len || len >= n) { out[0] = 0; return; }
    for (char *p = out; *p; p++) if (*p == '\\') *p = '/';
#else
    ssize_t len = readlink("/proc/self/exe", out, n - 1);
    if (len <= 0) { out[0] = 0; return; }
    out[len] = 0;
#endif
    slash = strrchr(out, '/');
    if (slash) slash[1] = 0; else out[0] = 0;
}

static void save_dir_path(char *out, size_t n)
{
    const char *env = getenv("ANI_SAVE_DIR");
    if (env && *env) { snprintf(out, n, "%s", env); return; }
#if defined(_WIN32)
    {
        const char *base = getenv("LOCALAPPDATA");
        snprintf(out, n, "%s/AnimaniacsRecompiled", base && *base ? base : ".");
    }
#else
    {
        const char *home = getenv("HOME");
        snprintf(out, n, "%s/.local/share/AnimaniacsRecompiled", home && *home ? home : ".");
    }
#endif
}

static bool load_file(const char *path, void **out_data, size_t *out_size)
{
    FILE *f = fopen(path, "rb");
    long size;
    void *data;

    if (!f)
        return false;
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (size <= 0 || !(data = malloc((size_t)size))) {
        fclose(f);
        return false;
    }
    if (fread(data, 1, (size_t)size, f) != (size_t)size) {
        free(data);
        fclose(f);
        return false;
    }
    fclose(f);
    *out_data = data;
    *out_size = (size_t)size;
    return true;
}

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

/* ── Boot (guest thread) ───────────────────────────────────── */

static void *guest_main(void *unused)
{
    char xbe_path[4200];
    void *xbe_data = NULL;
    size_t xbe_size = 0;

    (void)unused;
#if XBOX_HAS_VCPU
    vcpu_attach(VCPU_PRIO_NORMAL);
#endif
    snprintf(xbe_path, sizeof(xbe_path), "%s/default.xbe", s_game_dir);
    if (!load_file(xbe_path, &xbe_data, &xbe_size)) {
        fprintf(stderr, "Cannot read %s\n"
                        "Put the game's files in a 'game' directory next to the "
                        "executable, or pass its path.\n", xbe_path);
        exit(1);
    }
    printf("XBE loaded: %zu bytes\n", xbe_size);

    /* The US dump's header was re-flagged as a debug XBE and its TlsAddress
     * points into the header's strings; the image is the same as the PAL
     * one, whose header names the real directory (_tls_used, in .data). */
    xbox_SetTlsDirectoryFallback(0x001DEF40u);
    if (!xbox_MemoryLayoutInit(xbe_data, xbe_size)) {
        fprintf(stderr, "Failed to initialize the Xbox memory layout.\n");
        exit(1);
    }
    g_xbox_mem_offset = xbox_GetMemoryOffset();

    {
        Nv2aVkOptions o = { .headless = s_headless };
        if (xbox_Nv2aVkStart(&o) != 0) {
            fprintf(stderr, "Cannot start the GPU.\n");
            exit(1);
        }
    }

    if (getenv("RECOMP_AC97_READY")) {
        g_apu_state = mcpx_apu_init_standalone((uint8_t *)xbox_GetMemoryBase());
        fprintf(stderr, "[BOOT] emulated APU %s\n",
                g_apu_state ? "up" : "FAILED to initialise");
    }

    xbox_kernel_init();
    {
        extern void xbox_path_init(const char *game_dir, const char *save_dir);
        printf("Save directory: %s\n", s_save_dir);
        xbox_path_init(s_game_dir, s_save_dir);
    }
    xbox_kernel_bridge_init();
    xbox_OhciInit();
    g_esp = XBOX_STACK_TOP;

    if (!recomp_dispatch_init())
        fprintf(stderr, "[BOOT] flat dispatch unavailable\n");
    xbox_WatchdogStart();

    printf("Entry point: 0x%08X, ESP: 0x%08X\nStarting game...\n",
           ANI_ENTRY_POINT, g_esp);
    xbe_entry_point();

    printf("Game returned.\n");
    exit(0);
    return NULL;
}

/* ── Display ───────────────────────────────────────────────── */

/* Turn settings.ini's display choices into the window, the picture shape and
 * the render scale, now that the monitor is known.
 *
 *   window   windowed: the configured size (native = the monitor's), shrunk
 *            to fit the monitor; fullscreen: the monitor.
 *   aspect   the configured shape; auto = the window's (the monitor's in
 *            fullscreen). Never narrower than the original 4:3: a 5:4 screen
 *            gets 4:3 with bars, not a cropped view.
 *   scale    render_scale, or the smallest multiple of 640x480 that covers
 *            the picture on both axes (capped by max_render_scale).
 *
 * The shape goes to the game (ani_aspect: a wider horizontal view) and to the
 * presenter; the scale to the GPU model through NV2A_SCALE, unless the
 * environment already set it. */
static void resolve_display(const AniSettings *st, int *win_w, int *win_h,
                            double *aspect_out)
{
    extern float ani_aspect;   /* recomp_manual.c */
    SDL_DisplayMode dm;
    int mon_w = 1920, mon_h = 1080, out_w, out_h, pic_w, pic_h, scale;
    double aspect;
    char buf[8];

    if (SDL_WasInit(SDL_INIT_VIDEO) || SDL_InitSubSystem(SDL_INIT_VIDEO) == 0) {
        if (SDL_GetDesktopDisplayMode(0, &dm) == 0 && dm.w > 0 && dm.h > 0)
            mon_w = dm.w, mon_h = dm.h;
    }
    if (st->mode != ANI_WINDOWED || !st->width || !st->height) {
        out_w = mon_w;
        out_h = mon_h;
    } else {
        out_w = st->width;
        out_h = st->height;
        if (out_w > mon_w || out_h > mon_h) {   /* keep the shape, fit the screen */
            double k = (double)mon_w / out_w < (double)mon_h / out_h
                     ? (double)mon_w / out_w : (double)mon_h / out_h;
            out_w = (int)(out_w * k);
            out_h = (int)(out_h * k);
        }
    }
    aspect = st->aspect > 0 ? st->aspect : (double)out_w / out_h;
    if (aspect < 4.0 / 3.0) aspect = 4.0 / 3.0;
    if (aspect > 4.0) aspect = 4.0;

    pic_w = out_w;
    pic_h = (int)(out_w / aspect);
    if (pic_h > out_h) {
        pic_h = out_h;
        pic_w = (int)(out_h * aspect);
    }
    scale = st->render_scale ? st->render_scale
                             : ani_settings_auto_scale(pic_w, pic_h, st->max_render_scale);
    snprintf(buf, sizeof buf, "%d", scale);
    if (!getenv("NV2A_SCALE")) {
#if defined(_WIN32)
        _putenv_s("NV2A_SCALE", buf);
#else
        setenv("NV2A_SCALE", buf, 0);
#endif
    }
    scale = atoi(getenv("NV2A_SCALE"));
    ani_aspect = (float)aspect;
    *win_w = out_w;
    *win_h = out_h;
    *aspect_out = aspect;
    printf("Display: monitor %dx%d, %s %dx%d, picture %dx%d (%.3f:1), "
           "render %dx%d (scale %d)\n",
           mon_w, mon_h, st->mode == ANI_WINDOWED ? "window" : "fullscreen",
           out_w, out_h, pic_w, pic_h, aspect, 640 * scale, 480 * scale, scale);
}

/* ── Entry (host main thread: window and events) ───────────── */

int main(int argc, char **argv)
{
    const char *r;

#if defined(_WIN32)
    timeBeginPeriod(1);
    /* A GUI program: output that was redirected stays where it was sent;
     * started from a console it goes there; otherwise to log.txt in the
     * save folder, so a player has something to attach to a bug report. */
    {
        HANDLE err = GetStdHandle(STD_ERROR_HANDLE);
        if (err == NULL || err == INVALID_HANDLE_VALUE ||
            GetFileType(err) == FILE_TYPE_UNKNOWN) {
            if (AttachConsole(ATTACH_PARENT_PROCESS)) {
                freopen("CONOUT$", "w", stdout);
                freopen("CONOUT$", "w", stderr);
            } else {
                char log[4200];
                save_dir_path(log, sizeof log - 16);
                ani_mkdirs(log);
                strcat(log, "/log.txt");
                if (freopen(log, "w", stdout))
                    freopen(log, "a", stderr);
            }
        }
    }
#endif
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);

    r = getenv("ANI_RENDERER");
    s_headless = r && !strcmp(r, "null");
    /* The GPU model raises vblank from its CRTC; the APU and the controller
     * ports need their models. Each can still be overridden. */
    set_default("RECOMP_AC97_READY", "1");
    set_default("RECOMP_USB", "1");
    /* DirectSound's GP DSP command doorbell: nothing runs the DSP, so
     * acknowledge its commands (found from GPSADDR; patches/ngbrecomp-0001). */
    set_default("RECOMP_APU_DSP_ACK", "auto");

    /* Archipelago: --ap-server/--ap-slot (consumed here). A session picks
     * its own save directory, one per seed. */
    save_dir_path(s_save_dir, sizeof s_save_dir);
    ani_mkdirs(s_save_dir);
    {
        const char *ap_dir = ani_ap_init(&argc, argv, s_save_dir);
        if (ap_dir)
            snprintf(s_save_dir, sizeof s_save_dir, "%s", ap_dir);
    }

    if (argc > 1)
        snprintf(s_game_dir, sizeof s_game_dir, "%s", argv[1]);
    else if (getenv("ANI_GAME_DIR"))
        snprintf(s_game_dir, sizeof s_game_dir, "%s", getenv("ANI_GAME_DIR"));
    else {
        exe_dir(s_game_dir, sizeof s_game_dir);
        strncat(s_game_dir, "game", sizeof s_game_dir - strlen(s_game_dir) - 1);
    }
    printf("=== Animaniacs: The Great Edgar Hunt - Static Recompilation %s (Vulkan) ===\n",
           ANI_VERSION);
    printf("Game directory: %s\n", s_game_dir);

    {
        extern int ani_skip_intro, ani_hud_43;   /* recomp_manual.c */
        char exe[4096], save[4096];
        exe_dir(exe, sizeof exe);
        save_dir_path(save, sizeof save);
        ani_mkdirs(save);
        ani_settings_load(&s_settings, exe, save);
        ani_skip_intro = s_settings.skip_intro;
        ani_hud_43 = !s_settings.hud_stretch;
        ani_hud_configure(s_settings.ap_notifications, s_settings.ap_tracker, s_settings.ap_hud,
                          s_settings.ap_chat);
        printf("Settings: %s\n", s_settings.path);
    }

#if defined(_WIN32)
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
    SymInitialize(GetCurrentProcess(), NULL, TRUE);
#endif
    AddVectoredExceptionHandler(1, veh_handler);
    SetUnhandledExceptionFilter(crash_filter);

    if (!s_headless) {
        int win_w, win_h;
        double aspect;
        resolve_display(&s_settings, &win_w, &win_h, &aspect);
        if (nv2a_window_create("Animaniacs: The Great Edgar Hunt", win_w, win_h,
                               s_settings.mode == ANI_WINDOWED ? 0 : 1,
                               aspect, s_settings.vsync) != 0) {
            fprintf(stderr, "Cannot open the game window.\n");
            return 1;
        }
        xbox_InputInit();
    }

#if defined(_WIN32)
    CloseHandle(CreateThread(NULL, 64u << 20,
                             (LPTHREAD_START_ROUTINE)guest_main, NULL, 0, NULL));
#else
    {
        pthread_attr_t attr;
        pthread_t th;
        pthread_attr_init(&attr);
        pthread_attr_setstacksize(&attr, 64u << 20);
        if (pthread_create(&th, &attr, guest_main, NULL) != 0)
            return 1;
        pthread_attr_destroy(&attr);
    }
#endif

    if (!s_headless) {
        while (nv2a_window_pump())
            usleep(2000);
        printf("Window closed.\n");
        _exit(0);
    }
    for (;;)
#if defined(_WIN32)
        Sleep(INFINITE);
#else
        pause();
#endif
}
