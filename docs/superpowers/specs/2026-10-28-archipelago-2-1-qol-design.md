# Archipelago 2.1: in-game quality of life

## Why

2.0 put the Archipelago client inside the game, but everything it knows only shows
up in the log. A player mid-run can't see what they just sent or received, how many
Edgars they have toward the goal, or which checks a movie set still holds without
alt-tabbing to a separate tracker. 2.1 puts that on screen.

## Goals (in build order)

1. **Item notifications.** A popup for every item received ("Edgar from Sam") and
   every check of ours that sends an item to someone ("Rodeo Edgar: Hookshot for Sam").
   Several can stack; each fades after a few seconds.
2. **Check tracker screen.** A key or controller button opens a screen over the held
   game listing, per movie set (and the lot), the checks found and left by kind:
   Edgars, ACME letters, script pages, quest items, milestones, and collectibles or
   apples when the room has them. Picking a set lists the names of the checks still
   left there. Close and the game carries on.
3. **Edgar and goal counter.** A small always-on readout: Edgars received / required
   and the goal, plus a connection light (connected, reconnecting, offline).
4. Later in 2.1: server chat and hints shown as popups, then DeathLink.

## Non-goals

- The game's own font or art style (Austin chose the built-in font; swapping later
  is possible since text drawing sits behind one function).
- Typing chat from inside the game.
- Logic-aware "what's reachable now" in the tracker. It shows found and left, not
  in-logic.

## Anti-goals

- Anything that costs frame rate, stutters the game, or covers the HUD while playing.
- A popup flood when connecting to a room with many items already sent: the backlog
  on connect is summarized in one popup ("Received 14 items"), not 14.
- Breaking vanilla play: with no AP session, none of this draws.

## Constraints found

- The renderer (ngbrecomp submodule, `present_sdl.c`) already has two drawing paths,
  both unused by this game:
  - `nv2a_overlay_wanted` / `nv2a_overlay_frame`: a full-window ARGB picture drawn by
    the game over the frame it is held at. Fits the tracker screen as is.
  - The F10 frame-rate box: drawn live, but opaque, top-left only, grey and white only,
    and shared with the FPS counter. Too limited for popups and the counter.
- The repo already carries ngbrecomp changes as `patches/ngbrecomp-NNNN-*.patch`, so a
  small new patch for a live HUD layer is in keeping with how the project works.
- Names from other games in the multiworld ("Hookshot") need their data packages; the
  client doesn't fetch them yet (`on_print` in `ap_bridge.c` says so). 2.1 adds
  `GetDataPackage` for the room's games and caches it beside `ap_state.json`.
- F9, F10, F11 are taken by the renderer. The pad is read through XInput
  (`xinput_device.c`).

## Approaches considered

- **A. A live HUD layer patched into the presenter, plus the existing held-game overlay
  for the tracker (chosen).** One patch adds a game-supplied ARGB layer, alpha-blended
  over the presented frame each present (only the changed rows uploaded, only while
  something is showing). Popups and the counter draw into it; the tracker uses the
  overlay that already exists. Costs one more patch to carry.
- **B. Everything through the F10 box.** No patch, but one opaque grey rectangle in one
  corner that fights the FPS counter. Rejected: looks bad and can't do color or stacking.
- **C. An external tracker pack (PopTracker/EmoTracker) instead of an in-game screen.**
  Useful for streamers, but it's the alt-tab Austin wants to avoid. Could follow later
  as an extra; not instead.

## Decided

- Built-in font (Austin, 2026-10-28): an embedded bitmap font scaled to the window,
  with a dark translucent panel behind text so it reads over any scene.
- Notifications: received items in one color, sent items in another, progression items
  marked. Top-right stack, newest on top, about 4 s each, at most 4 visible.
- All three features on by default when an AP session is running; a settings.ini
  `[archipelago]` section can turn each off. The launcher's Archipelago tab gets the
  same toggles.

## Left to the builder

- Exact keys: proposal is Tab or F1 for the tracker, and holding the controller's Back
  button for half a second (a short press stays the game's).
- Font choice and sizes, panel layout, colors.
- How the HUD layer patch blends (CPU into a staging image and a blended blit, or a
  tiny pipeline) as long as it costs well under a millisecond.
- Test plan: unit tests for the tracker's counting and the popup queue against fake
  guest memory as `tests/ap` does today, a live run with `ANI_AP_TEST_COLLECT=1`,
  and game-rendered frame captures (never screen grabs) for each screen.
