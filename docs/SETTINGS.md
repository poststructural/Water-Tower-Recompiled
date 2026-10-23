# settings.ini

The Vulkan build reads `settings.ini` beside `Animaniacs.exe` (or in the save
folder when the exe's folder is read-only). A missing file is written with the
defaults below. Values are case-insensitive; `on/off`, `true/false`, `yes/no`
and `1/0` all work for switches. Unknown keys are ignored, so a launcher can
keep its own. Environment variables (`NV2A_SCALE`, `NV2A_MSAA`, ...) override
the file, for testing.

## [display]

| Key | Values | Default | |
|---|---|---|---|
| `mode` | `windowed`, `fullscreen`, `exclusive` | `windowed` | `fullscreen` is borderless at the monitor's resolution. `exclusive` is accepted and currently behaves like `fullscreen`. F11 / Alt+Enter toggles in game. |
| `resolution` | `WxH` (e.g. `1280x720`, `1920x1080`, `2560x1440`, `3840x2160`, `2560x1080`, `3440x1440`), `native` | `1920x1080` | Window size in windowed mode; shrunk to fit the monitor if larger. Fullscreen always uses the monitor's resolution. |
| `aspect` | `4:3`, `16:9`, `16:10`, `21:9`, `32:9`, any `W:H` or decimal (1.333-4.0), `auto` | `auto` | Shape of the picture. `auto` = the window's shape (the monitor's in fullscreen). Wider than 4:3 shows more of the world at the sides (Hor+). The frontend menus (a 4:3 painted stage) and the movies are shown at 4:3 with side bars. Narrower than 4:3 is shown as 4:3 with bars. |
| `hud` | `4:3`, `stretch` | `4:3` | 2D on a wide picture (HUD, menu text, prompts). `4:3` keeps each item's shape, anchored to the left edge, right edge or centre; `stretch` spreads it across the width. Full-screen fades always cover the screen. |
| `vsync` | `on`, `off`, `adaptive` (or `1`, `0`, `2`) | `on` | |
| `show_fps` | `on`, `off` | `off` | F10 toggles in game. |

## [graphics]

| Key | Values | Default | |
|---|---|---|---|
| `render_scale` | `auto`, `1`-`8` | `auto` | Internal resolution as a multiple of the console's 640x480. `auto` picks the smallest multiple that covers the picture on both axes: 2 at 720p, 3 at 1080p, 4 at 1440p, 6 at 4K (16:9). |
| `max_render_scale` | `1`-`8` | `6` | Upper limit for `auto`. Lower it for weaker GPUs. |
| `msaa` | `1`, `2`, `4`, `8` | `1` | Multisample anti-aliasing. |
| `texture_filter` | `smooth`, `console` | `smooth` | `smooth` filters and mipmaps textures; `console` samples them as the Xbox did. |

## [game]

| Key | Values | Default | |
|---|---|---|---|
| `skip_intro` | `on`, `off` | `off` | Skips the publisher logos and the intro movie. |

## Keys from the first version

Still read, so older files and launchers keep working; new files don't
contain them.

| Old key | Meaning now |
|---|---|
| `[display] width`, `height` | `resolution = WxH` |
| `[display] fullscreen = 0/1/2` | `mode = windowed` / `fullscreen` / `fullscreen` |
| `[display] widescreen = 0/1` | `aspect = 4:3` / `16:9` |

## Measured (RTX-class desktop GPU, 2560x1440 monitor)

| Output | Render | fps (Warner lot) |
|---|---|---|
| 1920x1080 window, 16:9 | 1920x1440 (auto, 3x) | 60 |
| 2560x1440, 16:9 | 2560x1920 (auto, 4x) | 60 |
| 2560x1080, 21:9 | 2560x1920 (auto, 4x) | 58-60 |
| 1920x1080, 16:9 | 3840x2880 (forced 6x) | 56-60 |
