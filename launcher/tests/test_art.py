"""The launcher's art ships with it and is ours (launcher/tools/make_art.py)."""

import os

from animaniacs_launcher import home

UI = home.UI_DIR


def test_every_image_home_uses_is_there():
    names = ["hero.png", "banner.png", "wordmark.png", "card.png"]
    names += [f"{k}_{s}.png" for k in ("play", "button") for s in ("normal", "focus", "disabled")]
    names += [f"status_{k}.png" for k in ("ok", "warn", "bad", "busy")]
    for n in names:
        path = os.path.join(UI, n)
        assert os.path.getsize(path) > 0, n
        with open(path, "rb") as f:
            assert f.read(8) == b"\x89PNG\r\n\x1a\n", n


def test_font_and_its_license_ship_together():
    assert os.path.exists(home.FONT_FILE)
    assert os.path.exists(os.path.join(os.path.dirname(home.FONT_FILE), "LuckiestGuy-LICENSE.txt"))
