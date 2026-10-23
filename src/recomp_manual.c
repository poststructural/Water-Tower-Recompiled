/**
 * Manual function overrides and ICALL diagnostics
 *
 * This file provides:
 *   - recomp_lookup_manual()  : intercept specific Xbox VAs with hand-written code
 *   - recomp_icall_fail_log() : log when an indirect call target can't be resolved
 *   - ICALL trace ring buffer  : globals used by the RECOMP_ICALL macro
 *
 * The recomp pipeline generates an auto-dispatch table (recomp_lookup) that
 * resolves most function addresses. recomp_lookup_manual() is called FIRST,
 * giving you a chance to override any function with a custom implementation.
 *
 * Common reasons to add manual overrides:
 *   - Trace a function to understand call flow (wrap the generated version)
 *   - Fix a function the lifter translated incorrectly
 *   - Stub out a function that crashes (return early, set eax to a safe value)
 *   - Redirect a function to a native implementation (e.g., skip CRT init)
 *   - Intercept D3D/audio calls for custom rendering or sound
 */

#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>   /* ptrdiff_t */

/* ── ICALL trace ring buffer ───────────────────────────────── */

/*
 * These globals are written by the RECOMP_ICALL macro (defined in
 * recomp_types.h) every time an indirect call is dispatched. When a
 * crash occurs, the VEH handler or recomp_icall_fail_log() can dump
 * the last 16 call targets to help you trace what happened.
 *
 * The runtime owns them: xbox_kernel defines all three in
 * src/kernel/xbox_memory_layout.c, and recomp_types.h declares them extern.
 * Declare, do not define -- a definition here as well is a duplicate symbol,
 * and a project copied from this template failed to link on all three:
 *
 *   xbox_memory_layout.obj : error LNK2005: g_icall_count already defined
 *                            in recomp_manual.obj
 */
extern volatile uint32_t g_icall_trace[16];
extern volatile uint32_t g_icall_trace_idx;
extern volatile uint64_t g_icall_count;

typedef void (*recomp_func_t)(void);

/* ── Register state (defined in xbox_memory_layout.c) ──────── */

/* Thread-local in the runtime (RECOMP_TLS). A plain extern binds to the TLS
 * template, not the calling thread's register, so writes would be lost. */
#if defined(_MSC_VER)
#  define ANI_TLS __declspec(thread)
#else
#  define ANI_TLS _Thread_local
#endif
extern ANI_TLS uint32_t g_eax, g_esp;
extern ptrdiff_t g_xbox_mem_offset;

/* ── Manual function overrides ─────────────────────────────── */

/*
 * Return a function pointer to override the given Xbox VA, or NULL
 * to fall through to the auto-generated dispatch table.
 *
 * This is called on every indirect call (RECOMP_ICALL) and every
 * direct call through the dispatch table, so keep it fast. A chain
 * of if-statements on uint32_t compiles to a simple comparison
 * sequence; for large override tables, consider a sorted array
 * with binary search.
 *
 * Examples of common override patterns:
 *
 *   // Trace wrapper: log entry/exit around the generated function
 *   extern void sub_00012345(void);
 *   static void traced_sub_00012345(void) {
 *       fprintf(stderr, "[TRACE] sub_00012345 entered, eax=0x%08X\n", g_eax);
 *       sub_00012345();
 *       fprintf(stderr, "[TRACE] sub_00012345 returned, eax=0x%08X\n", g_eax);
 *   }
 *
 *   // Stub: skip a function entirely (return 0 in eax)
 *   static void stub_00067890(void) {
 *       g_eax = 0;
 *   }
 *
 *   // Fix: replace a broken lifted function with correct C
 *   static void fixed_sub_000ABCDE(void) {
 *       // Read arguments from stack/registers per calling convention
 *       uint32_t arg1 = g_ecx;
 *       uint32_t arg2 = MEM32(g_esp + 4);
 *       // ... correct implementation ...
 *       g_eax = result;
 *   }
 */
/* ── Animaniacs: The Great Edgar Hunt ──────────────────────── */

/* Guest dword at an Xbox VA. */
#define GUEST32(va) (*(volatile uint32_t *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(va)))

/* A debug switch from the environment, read once: getenv in a per-draw hook
 * costs real frame time. */
#define ANI_ENV(name)     ({ static int v_ = -1; if (v_ < 0) v_ = getenv(name) != NULL; v_; })

/* XDK 5849 D3D (non-LTCG, in the D3D section). The device pointer lives at
 * 0x0015A388; device+0x2C is the pushbuffer write sequence and device+0x30
 * points at the GPU semaphore that BACK_END_WRITE_SEMAPHORE_RELEASE (0x1D70)
 * writes, which is how the GPU reports how far it has got. */
#define ANI_D3D_DEVICE_PTR  0x0015A388u

#if !defined(ANI_NV2A_VK)
void nv2a_pb_set_semaphore_target(uint32_t guest_va);
#endif

/* D3D_BlockOnTime (0x0014FA40): waits until the semaphore at *(device+0x30)
 * reaches a fence, spinning at 0x0014FB77. Nothing writes that semaphore
 * unless the pushbuffer executor is told where it is, so the first D3D call
 * to wait on the GPU (the display-mode switch in device creation) hung
 * forever. Hand the executor the semaphore on first entry, then run the
 * original. Needs RECOMP_PB_EXEC=1. */
static void ani_register_gpu_semaphore(void)
{
#if !defined(ANI_NV2A_VK)   /* the NV2A model writes the semaphore itself */
    static volatile int registered;

    if (!registered) {
        uint32_t dev = GUEST32(ANI_D3D_DEVICE_PTR);
        uint32_t sem = dev ? GUEST32(dev + 0x30) : 0;
        if (sem) {
            nv2a_pb_set_semaphore_target(sem);
            registered = 1;
            fprintf(stderr, "[D3D] GPU semaphore at 0x%08X (device 0x%08X)\n",
                    sem, dev);
        }
    }
#endif
}

extern void sub_0014FA40_gen(void);
void sub_0014FA40(void)
{
#if defined(ANI_NV2A_VK)
    extern void nv2a_trace(char);
    nv2a_trace('B');
#endif
    ani_register_gpu_semaphore();
    sub_0014FA40_gen();
#if defined(ANI_NV2A_VK)
    nv2a_trace('b');
#endif
}

/* D3D KickOff (0x0014F860). Register the semaphore here too, before the
 * first pushbuffer reaches the GPU: a semaphore release the executor runs
 * before it knows the target is dropped, and if the last release before a
 * BlockOnTime was one of those, that wait never ends. */
extern void sub_0014F860_gen(void);
void sub_0014F860(void)
{
    ani_register_gpu_semaphore();
    sub_0014F860_gen();
}

/* D3D's GPU-sync flush (0x0014F830). BlockOnTime calls it after patching a
 * "wake me" method into the ring, then waits for PGRAPH 0x400B10's fence bits
 * to match the semaphore -- which only holds once the executor has caught up.
 * The flush spin is what holds the title back until then, so main.c's
 * instant flush acknowledgement must stand aside while this one runs. */
volatile long g_ani_sync_flush;

extern void sub_0014F830_gen(void);
void sub_0014F830(void)
{
    InterlockedIncrement(&g_ani_sync_flush);
    sub_0014F830_gen();
    InterlockedDecrement(&g_ani_sync_flush);
}

/* BlockOnTime's "how far is the GPU from this fence" (0x0014F4C0), its only
 * caller. At 0x2000 bytes or more BlockOnTime patches a "wake me" software
 * method into the ring and sleeps on the event at device+0x1DCC, which the
 * GPU's software-method interrupt signals through D3D's ISR. Nothing raises
 * that interrupt here, and KeWaitForSingleObject on the event fails at once,
 * so the title spun at 0x0014FB94 for ever (first seen in the gi1.xmv intro
 * under RECOMP_PB_WALK=dma). Reporting "close" sends BlockOnTime to its
 * semaphore spin at 0x0014FB77 instead, which the executor does satisfy. */
extern void sub_0014F4C0_gen(void);
void sub_0014F4C0(void)
{
    sub_0014F4C0_gen();
#if !defined(ANI_NV2A_VK)   /* the NV2A model raises the interrupt */
    g_eax = 0;
#else
    if (ANI_ENV("ANI_BLOCK_SPIN"))
        g_eax = 0;
#endif
}

/* Game state machine step (0x000B09A0): when the requested state at
 * 0x00313A70 differs from the current one at 0x00313B54 it tears the old one
 * down and enters the new. States 3..8 are the levels (3 = level 0, the
 * Warner lot hub; the loader opens resource/level<state-3>.hog).
 * ANI_LEVEL=N (1-5) turns a request for the hub into one for level N: a test
 * aid for reaching every level without playing through to it. */
#define ANI_STATE_CURRENT   0x00313B54u
#define ANI_STATE_REQUESTED 0x00313A70u

extern void sub_000B09A0_gen(void);
void sub_000B09A0(void)
{
    static int want = -2;
    if (want == -2) {
        const char *e = getenv("ANI_LEVEL");
        want = (e && *e >= '1' && *e <= '5') ? *e - '0' : 0;
    }
    if (ANI_ENV("ANI_STATE_LOG")) {
        static uint32_t last_cur = ~0u, last_req = ~0u;
        uint32_t cur = GUEST32(ANI_STATE_CURRENT), req = GUEST32(ANI_STATE_REQUESTED);
        if (cur != last_cur || req != last_req)
            fprintf(stderr, "[ANI] game state %u, requested %u\n", cur, req);
        last_cur = cur;
        last_req = req;
    }
    if (want && GUEST32(ANI_STATE_REQUESTED) == 3 &&
        GUEST32(ANI_STATE_CURRENT) != 3) {
        fprintf(stderr, "[ANI] ANI_LEVEL: entering level %d instead of the hub\n", want);
        GUEST32(ANI_STATE_REQUESTED) = 3u + (uint32_t)want;
    }
    sub_000B09A0_gen();
#if defined(ANI_NV2A_VK)
    /* The frontend (states below 3) draws its stage as a full-screen 4:3
     * backdrop with 3D characters standing on it, which a wider view would
     * pull apart; it is shown at 4:3 with side bars. The levels use the
     * picture's shape. */
    {
        extern float ani_aspect;
        extern void nv2a_present_set_aspect(double aspect);
        static float picture;
        static int shown = -1;
        int frontend = GUEST32(ANI_STATE_CURRENT) < 3;
        if (picture == 0.0f)
            picture = ani_aspect;
        if (picture > 1.34f && frontend != shown) {
            shown = frontend;
            ani_aspect = frontend ? 4.0f / 3.0f : picture;
            nv2a_present_set_aspect(ani_aspect);
        }
    }
#endif
}

/* Movie player entry (0x000ECF20, cdecl: the movie's base name). The boot
 * sequence plays splashig, splashwb, warthog and gi1 through it; the
 * frontend moves on when no movie is playing, so not starting one skips it.
 * ani_skip_intro comes from settings.ini (skip_intro). */
int ani_skip_intro;

extern void sub_000ECF20_gen(void);
void sub_000ECF20(void)
{
    if (ani_skip_intro) {
        static const char *const boot[] = { "splashig", "splashwb", "warthog", "gi1" };
        uint32_t name_va = GUEST32(g_esp + 4);
        const char *name = (const char *)((uintptr_t)g_xbox_mem_offset + name_va);
        for (unsigned i = 0; name_va && i < sizeof boot / sizeof boot[0]; i++) {
            if (!strcmp(name, boot[i])) {
                fprintf(stderr, "[ANI] skip_intro: not playing %s\n", name);
                g_esp += 4;   /* the ret: pop the caller's return address */
                g_eax = 0;
                return;
            }
        }
    }
#if defined(ANI_NV2A_VK)
    /* The movie plays inside this call (sub_0013B7E0 runs it to the end), and
     * every movie is 640x480 4:3. Show it at 4:3 while it plays, so a wide
     * picture setting pillarboxes it instead of stretching it. */
    {
        extern float ani_aspect;
        extern void nv2a_present_set_aspect(double aspect);
        if (ani_aspect > 1.34f) {
            fprintf(stderr, "[ANI] movie at 4:3 (picture %.3f:1)\n", ani_aspect);
            nv2a_present_set_aspect(4.0 / 3.0);
            sub_000ECF20_gen();
            nv2a_present_set_aspect(ani_aspect);
            return;
        }
    }
#endif
    sub_000ECF20_gen();
}

/* The picture shape the game renders for (main_vk.c, from settings.ini):
 * 4:3 is the original; wider shapes widen the horizontal view (Hor+). */
float ani_aspect = 4.0f / 3.0f;

/* Camera projection scales (0x0005CC80, every frame from the render path):
 * calls sub_00063F30(camera, k * [0x002EEC50], k * [0x002EECA8]) -- the
 * horizontal and vertical scale factors (cot of the half-angles). The camera
 * modes keep the vertical one 4/3 of the horizontal (the fmul by 4/3 at
 * 0x0005C84F; pairs such as 2.4 / 3.2), which is a 4:3 view. For widescreen
 * the horizontal scale becomes 1/aspect of the vertical for this call only: the
 * same vertical view, a wider horizontal one (Hor+), which the presenter
 * shows at that shape. */
#define ANI_PROJ_X 0x002EEC50u
#define ANI_PROJ_Y 0x002EECA8u

extern void sub_0005CC80_gen(void);
void sub_0005CC80(void)
{
    volatile float *x = (volatile float *)((uintptr_t)g_xbox_mem_offset + ANI_PROJ_X);
    volatile float *y = (volatile float *)((uintptr_t)g_xbox_mem_offset + ANI_PROJ_Y);
    float saved = *x;

    if (ANI_ENV("ANI_WS_LOG")) {
        static float seen[16][2];
        static int nseen;
        int i;
        for (i = 0; i < nseen && !(seen[i][0] == saved && seen[i][1] == *y); i++)
            ;
        if (i == nseen && nseen < 16) {
            seen[nseen][0] = saved;
            seen[nseen++][1] = *y;
            fprintf(stderr, "[ANI] proj scales %f %f\n", saved, *y);
        }
    }
    if (ani_aspect > 1.34f && saved > 0.0f) {
        float r = *y / saved;
        if (r > 1.30f && r < 1.37f)
            *x = *y / ani_aspect;
    }
    sub_0005CC80_gen();
    *x = saved;
}

/* Projection setup (0x00084110, cdecl: fov, aspect, near, far, viewport...).
 * Every camera goes through it -- the gameplay camera (sub_000843B0) and the
 * cutscene cameras alike -- with aspect 4:3 (0x3FAAAAAB). With widescreen on
 * (settings.ini), a 4:3 aspect becomes 16:9: the game renders a wider view
 * into the same framebuffer, and the presenter stretches it to 16:9
 * (anamorphic, like a widescreen TV). Other aspects -- render-to-texture
 * cameras -- are left alone. */

extern void sub_00084110_gen(void);
void sub_00084110(void)
{
    if (ani_aspect > 1.34f) {
        volatile float *aspect = (volatile float *)
            ((uintptr_t)g_xbox_mem_offset + (uint32_t)(g_esp + 8));
        float a = *aspect;
        if (ANI_ENV("ANI_WS_LOG")) {
            static float seen[16][7];
            static int nseen;
            float v[7];
            int i;
            for (i = 0; i < 7; i++)
                v[i] = *(volatile float *)((uintptr_t)g_xbox_mem_offset +
                                           (uint32_t)(g_esp + 4 + 4 * i));
            for (i = 0; i < nseen && memcmp(seen[i], v, sizeof v); i++)
                ;
            if (i == nseen && nseen < 16) {
                memcpy(seen[nseen++], v, sizeof v);
                fprintf(stderr, "[ANI] projection: %f %f %f %f | %f %f %f from 0x%08X\n",
                        v[0], v[1], v[2], v[3], v[4], v[5], v[6],
                        GUEST32(g_esp));
            }
        }
        if (a > 1.33f && a < 1.34f) {
            *aspect = ani_aspect;
            sub_00084110_gen();
            /* cdecl: the caller pops the arguments, so restore what it passed. */
            *(volatile float *)((uintptr_t)g_xbox_mem_offset +
                                (uint32_t)(g_esp + 8)) = a;
            return;
        }
    }
    sub_00084110_gen();
}

/* Cutscene letterbox (0x000A7C00, every frame from the render loop
 * sub_0009ABD0). While a cutscene runs, the state at 0x00312D84 is non-zero
 * and this draws two black quads with the 2D quad routine 0x0011E4A0 --
 * 0..60 and 360..480 of the 640x480 screen -- sliding them in and out by the
 * offset at 0x00312D80, which it also advances. In a picture wider than 4:3
 * the cutscene view is already wide, so the bars are left out; the state
 * and the slide still advance, since scripts wait on them. */
static int s_in_letterbox;

extern void sub_000A7C00_gen(void);
void sub_000A7C00(void)
{
    extern float ani_aspect;
    s_in_letterbox = ani_aspect > 1.34f;
    sub_000A7C00_gen();
    s_in_letterbox = 0;
}

/* 2D quad (0x0011E4A0, cdecl). Skipped only for the letterbox bars above.
 * ANI_QUAD_LOG=1 lists each call site once with its rectangle. */
extern void sub_0011E4A0_gen(void);
void sub_0011E4A0(void)
{
    if (s_in_letterbox) {
        g_esp += 4;   /* the ret: the caller pops the arguments (cdecl) */
        return;
    }
    if (ANI_ENV("ANI_QUAD_LOG")) {
        static uint32_t seen[64];
        static int nseen;
        uint32_t ret = GUEST32(g_esp);
        int i;
        for (i = 0; i < nseen && seen[i] != ret; i++)
            ;
        if (i == nseen && nseen < 64) {
            seen[nseen++] = ret;
            fprintf(stderr, "[ANI] quad from 0x%08X: %f %f %f %f\n", ret,
                    *(volatile float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(g_esp + 4)),
                    *(volatile float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(g_esp + 8)),
                    *(volatile float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(g_esp + 12)),
                    *(volatile float *)((uintptr_t)g_xbox_mem_offset + (uint32_t)(g_esp + 16)));
        }
    }
    sub_0011E4A0_gen();
}

/*
 * Controller rumble (0x0013CB60, cdecl: left, right motor 0..1; esi is the
 * pad object). The game creates an event, hands XInputSetState the feedback
 * block and waits for the USB transfer to signal it -- every call, from the
 * main thread. On the emulated USB that wait costs a poll interval and can
 * be missed outright, which halved the frame rate in busy scenes and froze
 * the cliffs level. The motors are set on the host controller directly.
 */
extern void sub_0013CB60_gen(void);
void sub_0013CB60(void)
{
#if defined(ANI_NV2A_VK)
    extern unsigned long xbox_InputSetState(unsigned long port, const void *vibration);
    float l, r;
    uint16_t v[2];
    memcpy(&l, (const void *)((uintptr_t)g_xbox_mem_offset + g_esp + 4), 4);
    memcpy(&r, (const void *)((uintptr_t)g_xbox_mem_offset + g_esp + 8), 4);
    l = l < 0.0f ? 0.0f : l > 1.0f ? 1.0f : l;
    r = r < 0.0f ? 0.0f : r > 1.0f ? 1.0f : r;
    v[0] = (uint16_t)(l * 65535.0f);
    v[1] = (uint16_t)(r * 65535.0f);
    xbox_InputSetState(0, v);
#endif
    g_esp += 4;   /* the ret: the caller pops the arguments (cdecl) */
    g_eax = 0;
}

/*
 * 2D at 4:3 on wide pictures. The game draws its menus, text and HUD through
 * an immediate-mode layer: 0x001378E0 begins a primitive (types >= 5 load a
 * 640x480 orthographic projection), vertices go to the pushbuffer as
 * SetVertexData4f(VERTEX) (method 0x1518, x y z w), and D3D End (0x0014DD80)
 * closes it. At End the primitive's vertex x values are still in the
 * unsubmitted pushbuffer, so they are squeezed by 4:3 / aspect there:
 * anchored left, right or centre by which third of the screen the primitive
 * sits in. Primitives spanning the whole width (fades, backdrops) stay
 * stretched. ani_hud_43 = 0 (settings: hud = stretch) turns this off.
 */
int ani_hud_43 = 1;

static uint32_t s_2d_start;   /* pushbuffer address after Begin, 0 = not 2D */

extern void sub_001378E0_gen(void);
void sub_001378E0(void)
{
    extern float ani_aspect;
    int32_t prim = (int32_t)GUEST32(g_esp + 4);
    sub_001378E0_gen();
    s_2d_start = 0;
    if (prim >= 5 && ani_hud_43 && ani_aspect > 1.34f)
        s_2d_start = GUEST32(GUEST32(0x0015A388));
}

extern void sub_0014DD80_gen(void);
void sub_0014DD80(void)
{
    uint32_t start = s_2d_start, end;
    s_2d_start = 0;
    if (start) {
        extern float ani_aspect;
        float lo = 1e9f, hi = -1e9f, s = (4.0f / 3.0f) / ani_aspect, x, cx;
        uint32_t p;
        end = GUEST32(GUEST32(0x0015A388));
        if (end > start && end - start < 0x100000) {
            for (p = start; p + 20 <= end; p += 4) {
                if (GUEST32(p) != 0x00101518u)
                    continue;
                memcpy(&x, (const void *)((uintptr_t)g_xbox_mem_offset + p + 4), 4);
                if (x < lo) lo = x;
                if (x > hi) hi = x;
                p += 16;
            }
            if (lo <= hi && !(lo <= 1.0f && hi >= 639.0f)) {
                cx = 0.5f * (lo + hi);
                for (p = start; p + 20 <= end; p += 4) {
                    if (GUEST32(p) != 0x00101518u)
                        continue;
                    memcpy(&x, (const void *)((uintptr_t)g_xbox_mem_offset + p + 4), 4);
                    if (cx < 640.0f / 3.0f)
                        x = x * s;
                    else if (cx > 1280.0f / 3.0f)
                        x = 640.0f - (640.0f - x) * s;
                    else
                        x = 320.0f + (x - 320.0f) * s;
                    memcpy((void *)((uintptr_t)g_xbox_mem_offset + p + 4), &x, 4);
                    p += 16;
                }
            }
        }
    }
    sub_0014DD80_gen();
}


recomp_func_t recomp_lookup_manual(uint32_t xbox_va)
{
    /*
     * TODO: Add your overrides here. Examples:
     *
     * if (xbox_va == 0x00012345) return traced_sub_00012345;
     * if (xbox_va == 0x00067890) return stub_00067890;
     * if (xbox_va == 0x000ABCDE) return fixed_sub_000ABCDE;
     */

    (void)xbox_va;
    return (recomp_func_t)0;
}

/* ── ICALL failure logging ─────────────────────────────────── */

/*
 * Called when RECOMP_ICALL cannot resolve a target address.
 * This usually means one of:
 *   - A vtable dispatch to an address not in the dispatch table
 *   - A function pointer loaded from uninitialized or corrupt memory
 *   - A kernel thunk address that the bridge doesn't handle
 *
 * During early bring-up you will see many of these. Most are harmless
 * (the ICALL macro pops the dummy return address and continues).
 * Focus on the ones that cause crashes or incorrect behavior.
 */
void recomp_icall_fail_log(uint32_t va)
{
    fprintf(stderr, "[ICALL] Failed to resolve VA 0x%08X (total calls: %llu)\n",
            va, (unsigned long long)g_icall_count);

    /* Dump last 16 call targets from the ring buffer */
    fprintf(stderr, "  Recent ICALL targets:\n");
    for (int i = 0; i < 16; i++) {
        int idx = (g_icall_trace_idx - 16 + i) & 15;
        if (g_icall_trace[idx])
            fprintf(stderr, "    [%2d] 0x%08X\n", i, g_icall_trace[idx]);
    }
    fflush(stderr);
}

/* An indirect call whose target is not code: a null or wild function pointer.
 *
 * Skipping these is right -- calling a data address is worse -- but skipping
 * them *silently* is not. They almost always arrive inside a loop, so the
 * symptom is a hang with no output rather than a diagnosable null vtable call.
 *
 * Rate-limited per address: a spin can produce millions of these, and the
 * useful information is which addresses occur, not how often.
 */
void recomp_icall_not_code_log(uint32_t va)
{
    enum { SLOTS = 16 };
    static uint32_t seen[SLOTS];
    static uint64_t hits[SLOTS];
    static int count;
    int i;

    for (i = 0; i < count; i++)
        if (seen[i] == va)
            break;
    if (i == count) {
        if (count == SLOTS)
            return;
        seen[count] = va;
        hits[count] = 0;
        count++;
    }
    hits[i]++;
    /* Report at 1, 10, 100, 1000 ... rather than once. A single line says a
     * wild pointer was skipped; the progression says it is being skipped in a
     * loop, which is the difference between a curiosity and the reason the
     * title is hung. */
    {
        uint64_t n = hits[i];
        while (n >= 10 && n % 10 == 0)
            n /= 10;
        if (n != 1)
            return;
    }
    fprintf(stderr, "[ICALL] target 0x%08X is not code -- skipped %llu time(s) "
                    "(null or wild function pointer, at call #%llu)\n",
            va, (unsigned long long)hits[i],
            (unsigned long long)g_icall_count);
    fflush(stderr);
}

/* ── Untranslated instructions ───────────────────────────────────────────
 *
 * The lifter emits RECOMP_UNIMPL(text, va) at every instruction it has no
 * translation for, in place of the bare comment it used to leave. The
 * instruction is still a no-op; this only stops the omission being silent.
 * RECOMP_UNIMPL_TRAP=1 aborts at the first hit, at the guest address of the
 * cause rather than wherever the damage surfaces. */
#include <stdlib.h>

void recomp_unimpl(const char *text, uint32_t va)
{
    static int printed;
    const char *trap = getenv("RECOMP_UNIMPL_TRAP");
    int stop = trap && *trap && *trap != '0';

    if (printed < 50 || stop) {
        printed++;
        fprintf(stderr,
                "[UNIMPL] untranslated instruction REACHED: `%s` at 0x%08X"
                " (a no-op; set RECOMP_UNIMPL_TRAP=1 to stop here)\n",
                text, va);
        fflush(stderr);
    }
    if (stop) abort();
}
