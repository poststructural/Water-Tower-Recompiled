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

extern void xbox_InputInit(void);

extern RECOMP_TLS uint32_t g_eax, g_ecx, g_edx, g_esp;
extern RECOMP_TLS uint32_t g_ebx, g_esi, g_edi;
extern ptrdiff_t g_xbox_mem_offset;

#define ANI_ENTRY_POINT 0x0010A26Au

extern void xbe_entry_point(void);
extern int recomp_dispatch_init(void);

static char s_game_dir[4096];
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

static void print_host_symbol(void *rip)
{
#if defined(_WIN32)
    char buf[sizeof(SYMBOL_INFO) + 256];
    SYMBOL_INFO *sym = (SYMBOL_INFO *)buf;
    DWORD64 disp = 0;

    memset(buf, 0, sizeof(buf));
    sym->SizeOfStruct = sizeof(SYMBOL_INFO);
    sym->MaxNameLen = 255;
    if (SymFromAddr(GetCurrentProcess(), (DWORD64)(uintptr_t)rip, &disp, sym))
        fprintf(stderr, "  in %s+0x%llX\n", sym->Name, (unsigned long long)disp);
#else
    (void)rip;
#endif
}

static void print_guest_stack(void)
{
    const uint32_t *sp;
    int i, shown = 0;

    if (!g_xbox_mem_offset || !g_esp)
        return;
    sp = (const uint32_t *)((uintptr_t)g_xbox_mem_offset + g_esp);
    fprintf(stderr, "  guest stack (return addresses, innermost first):\n");
    for (i = 0; i < 256 && shown < 24; i++) {
        uint32_t v = sp[i];
        if (v > g_xbox_code_lo && v < g_xbox_code_hi) {
            fprintf(stderr, "    [esp+%-4d] 0x%08X\n", i * 4, v);
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
    print_host_symbol((void *)(uintptr_t)ep->ContextRecord->Rip);
    print_guest_stack();
    fflush(stderr);
    return EXCEPTION_CONTINUE_SEARCH;
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
        char save_dir[4096];
        save_dir_path(save_dir, sizeof(save_dir));
        printf("Save directory: %s\n", save_dir);
        xbox_path_init(s_game_dir, save_dir);
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

    if (argc > 1)
        snprintf(s_game_dir, sizeof s_game_dir, "%s", argv[1]);
    else if (getenv("ANI_GAME_DIR"))
        snprintf(s_game_dir, sizeof s_game_dir, "%s", getenv("ANI_GAME_DIR"));
    else {
        exe_dir(s_game_dir, sizeof s_game_dir);
        strncat(s_game_dir, "game", sizeof s_game_dir - strlen(s_game_dir) - 1);
    }
    printf("=== Animaniacs: The Great Edgar Hunt - Static Recompilation (Vulkan) ===\n");
    printf("Game directory: %s\n", s_game_dir);

    {
        extern int ani_skip_intro, ani_widescreen;   /* recomp_manual.c */
        char exe[4096], save[4096];
        exe_dir(exe, sizeof exe);
        save_dir_path(save, sizeof save);
        ani_mkdirs(save);
        ani_settings_load(&s_settings, exe, save);
        ani_skip_intro = s_settings.skip_intro;
        ani_widescreen = s_settings.widescreen;
        printf("Settings: %s\n", s_settings.path);
    }

#if defined(_WIN32)
    SymSetOptions(SYMOPT_DEFERRED_LOADS | SYMOPT_UNDNAME);
    SymInitialize(GetCurrentProcess(), NULL, TRUE);
#endif
    AddVectoredExceptionHandler(1, veh_handler);

    if (!s_headless) {
        if (nv2a_window_create("Animaniacs: The Great Edgar Hunt",
                               s_settings.width, s_settings.height,
                               s_settings.fullscreen,
                               s_settings.widescreen ? 16.0 / 9.0 : 4.0 / 3.0,
                               s_settings.vsync) != 0) {
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
