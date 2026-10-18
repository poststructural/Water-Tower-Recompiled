import os

import pytest

from animaniacs_launcher import config, gamesettings, play, profiles

GAME_WRITTEN = gamesettings.FALLBACK_TEMPLATE + "\n[future]\n; a key a newer game knows\nhdr = 1\n"


def test_edit_keeps_comments_and_unknown_keys(tmp_path):
    p = tmp_path / "settings.ini"
    p.write_text(GAME_WRITTEN)
    ini = gamesettings.load(str(p))
    assert gamesettings.value(ini, "display.width") == "1280"
    assert gamesettings.value(ini, "display.widescreen") == "0"  # not in the file: default
    gamesettings.apply(ini, {"display.width": "1920", "display.height": "1080",
                             "display.widescreen": "1", "graphics.render_scale": "3"})
    ini.save(str(p))
    text = p.read_text()
    assert "width = 1920" in text and "height = 1080" in text and "render_scale = 3" in text
    assert "; Window size in pixels" in text and "hdr = 1" in text
    # The new key lands inside [display], before [graphics].
    assert text.index("widescreen = 1") < text.index("[graphics]")
    assert text.count("[display]") == 1
    again = gamesettings.load(str(p))
    assert gamesettings.value(again, "display.widescreen") == "1"


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
