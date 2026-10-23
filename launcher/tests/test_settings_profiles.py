import os

import pytest

from animaniacs_launcher import config, gamesettings, play, profiles

GAME_WRITTEN = gamesettings.FALLBACK_TEMPLATE + "\n[future]\n; a key a newer game knows\nhdr = 1\n"


def test_edit_keeps_comments_and_unknown_keys(tmp_path):
    p = tmp_path / "settings.ini"
    p.write_text(GAME_WRITTEN)
    ini = gamesettings.load(str(p))
    assert gamesettings.value(ini, "display.resolution") == "1920x1080"
    assert gamesettings.value(ini, "graphics.render_scale") == "auto"
    gamesettings.apply(ini, {"display.resolution": "2560x1440", "display.aspect": "21:9",
                             "graphics.render_scale": "4", "game.skip_intro": "on"})
    ini.save(str(p))
    text = p.read_text()
    for line in ("resolution = 2560x1440", "aspect = 21:9", "render_scale = 4", "skip_intro = on",
                 "max_render_scale = 6"):
        assert line in text
    assert "; Picture shape" in text and "hdr = 1" in text
    assert text.count("[display]") == 1


def test_first_version_keys(tmp_path):
    old = ("[display]\nwidth = 1280\nheight = 960\nfullscreen = 2\nvsync = 2\nwidescreen = 1\n"
           "show_fps = 1\n[graphics]\nrender_scale = 2\n[game]\nskip_intro = 1\n")
    ini = gamesettings.IniFile(old)
    v = {n: gamesettings.value(ini, n) for n in gamesettings.OPTIONS}
    assert v["display.resolution"] == "1280x960" and v["display.mode"] == "fullscreen"
    assert v["display.aspect"] == "16:9" and v["display.vsync"] == "adaptive"
    assert v["display.show_fps"] == "on" and v["game.skip_intro"] == "on"
    assert v["graphics.max_render_scale"] == "6"
    # Writing a new key drops the old ones it replaces (the last key read wins).
    gamesettings.apply(ini, {"display.resolution": "1920x1080", "display.mode": "windowed"})
    text = ini.text()
    assert "width" not in text and "height" not in text and "fullscreen" not in text
    assert "resolution = 1920x1080" in text and "mode = windowed" in text
    assert "widescreen = 1" in text  # untouched until aspect is changed
    assert gamesettings.value(ini, "display.aspect") == "16:9"


def test_auto_scale_matches_docs():
    # docs/SETTINGS.md: 2 at 720p, 3 at 1080p, 4 at 1440p, 6 at 4K (16:9).
    assert [gamesettings.auto_scale(w, h) for w, h in
            [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)]] == [2, 3, 4, 6]
    assert gamesettings.auto_scale(3840, 2160, limit=4) == 4


def test_missing_section_is_added(tmp_path):
    ini = gamesettings.IniFile("[display]\nwidth = 640\n")
    ini.set("game", "skip_intro", "1")
    assert ini.text().endswith("[game]\nskip_intro = 1\n")


def test_template_from_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "settings.c").write_text(
        'static const char DEFAULT_INI[] =\n'
        '    "; Defaults.\\n"\n'
        '    "[display]\\n"\n'
        '    "width = 1280\\n";\n')
    assert gamesettings.template_from_source(str(tmp_path)) == "; Defaults.\n[display]\nwidth = 1280\n"
    assert gamesettings.template_from_source(str(tmp_path / "none")) is None


def test_template_matches_repo_source():
    # The fallback copy should follow src/settings.c on this branch.
    repo = os.path.join(os.path.dirname(__file__), "..", "..")
    t = gamesettings.template_from_source(repo)
    if t is None:
        pytest.skip("no src/settings.c")
    ini = gamesettings.IniFile(t)
    for name, o in gamesettings.OPTIONS.items():
        got = ini.get(o.section, o.key)
        if got is not None:
            assert got == o.default, name


def test_profiles(tmp_path, monkeypatch):
    monkeypatch.setenv("ANI_SAVE_DIR", str(tmp_path / "saves"))
    assert profiles.folder("") == str(tmp_path / "saves")
    assert profiles.env("") == {}
    for bad in ("", "../x", "a/b", "CON", "x" * 40, "trailing."):
        assert not profiles.valid_name(bad)
    profiles.create("Seed 1")
    with pytest.raises(ValueError):
        profiles.create("seed 1")
    assert profiles.list_profiles() == ["Seed 1"]
    assert profiles.env("Seed 1") == {"ANI_SAVE_DIR": str(tmp_path / "saves" / "profiles" / "Seed 1")}

    with pytest.raises(ValueError):
        profiles.backup("Seed 1", str(tmp_path))
    d = profiles.folder("")
    open(os.path.join(d, "save0.dat"), "wb").write(b"s")
    open(os.path.join(d, "log.txt"), "w").write("log")
    out = profiles.backup("", str(tmp_path))
    import zipfile
    assert zipfile.ZipFile(out).namelist() == ["save0.dat"]


def test_system_info_has_settings(tmp_path):
    exe = tmp_path / "Animaniacs.exe"
    exe.write_bytes(b"MZ")
    (tmp_path / "settings.ini").write_text("; c\n[display]\nwidth = 1920\n")
    info = play.system_info(config.Settings(custom_exe=str(exe)))
    assert "width = 1920" in info and "; c" not in info


def test_hud_option_defaults_and_saves():
    ini = gamesettings.IniFile(gamesettings.FALLBACK_TEMPLATE)
    assert gamesettings.value(ini, "display.hud") == "4:3"
    gamesettings.apply(ini, {"display.hud": "stretch"})
    assert ini.get("display", "hud") == "stretch"
    assert gamesettings.value(gamesettings.IniFile("[display]\n"), "display.hud") == "4:3"
