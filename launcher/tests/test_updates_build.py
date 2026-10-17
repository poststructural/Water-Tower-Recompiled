import json
import os

from animaniacs_launcher import build, cli, config, updates


def fake_get(responses):
    def get(path, timeout=15.0):
        for prefix, value in responses.items():
            if path.startswith(prefix):
                return value
        raise AssertionError(path)
    return get


MAIN = {"sha": "abcdef1234567890", "commit": {"message": "Faster level loads\n\nbody"},
        "html_url": "u"}


def test_release_channel_skips_launcher_and_drafts(monkeypatch):
    rels = [
        {"tag_name": "launcher-v0.2.0", "draft": False, "prerelease": False},
        {"tag_name": "v0.4.0", "draft": True},
        {"tag_name": "v0.3.0-rc1", "prerelease": True},
        {"tag_name": "v0.2.0", "body": "notes"},
    ]
    monkeypatch.setattr(updates, "_get", fake_get({
        "/repos/Unowa001/AnimaniacsRecompiled/releases": rels,
        "/repos/Unowa001/AnimaniacsRecompiled/commits/v0.2.0": {"sha": "1" * 40},
    }))
    v = updates.latest_game("release")
    assert (v.name, v.ref, v.fell_back) == ("v0.2.0", "refs/tags/v0.2.0", False)


def test_release_channel_falls_back_to_main(monkeypatch):
    monkeypatch.setattr(updates, "_get", fake_get({
        "/repos/Unowa001/AnimaniacsRecompiled/releases": [],
        "/repos/Unowa001/AnimaniacsRecompiled/commits/main": MAIN,
    }))
    v = updates.latest_game("release")
    assert v.fell_back and v.name == "main-abcdef1" and v.notes == "Faster level loads"


def test_launcher_update(monkeypatch):
    rels = [{"tag_name": "v1.0"},
            {"tag_name": "launcher-v9.0.0", "html_url": "p",
             "assets": [{"name": "AnimaniacsLauncherSetup-9.0.0.exe", "browser_download_url": "d"}]}]
    monkeypatch.setattr(updates, "_get", fake_get({"/repos/": rels}))
    lr = updates.latest_launcher()
    assert lr and lr.version == "9.0.0" and lr.installer_url == "d"
    rels[1]["tag_name"] = "launcher-v0.0.1"
    assert updates.latest_launcher() is None


def test_install_and_prune(tmp_path):
    bdir = tmp_path / "build-vk"
    bdir.mkdir()
    (bdir / build.EXE).write_bytes(b"MZ")
    (bdir / "Animaniacs.pdb").write_bytes(b"pdb")
    (bdir / "build.ninja").write_text("")
    for i in range(4):
        v = updates.GameVersion(f"main-{i}", "x", "y", "main")
        d = build.install(v, str(bdir))
        os.utime(os.path.join(d, "build.json"), (1000 + i, 1000 + i))
    assert sorted(os.listdir(d)) == sorted([build.EXE, "Animaniacs.pdb", "build.json"])
    assert [b["name"] for b in build.installed()] == ["main-3", "main-2", "main-1", "main-0"]
    build.prune("main-1", keep=1)
    assert [b["name"] for b in build.installed()] == ["main-3", "main-1"]


def test_settings_roundtrip_ignores_unknown_keys():
    st = config.Settings(game_dir="g", channel="main")
    st.save()
    raw = json.load(open(config.Settings.path()))
    raw["from_the_future"] = 1
    json.dump(raw, open(config.Settings.path(), "w"))
    assert config.Settings.load().channel == "main"


def test_cli_setup_and_check(tmp_path, capsys):
    from conftest import game_tree, make_xiso
    img = tmp_path / "g.iso"
    img.write_bytes(make_xiso(game_tree()))
    assert cli.main(["setup", str(img)]) == 0
    st = config.Settings.load()
    assert st.game_dir == config.sub("game")
    cli.main(["check"])
    assert "Animaniacs (EU)" in capsys.readouterr().out


def test_update_keeps_settings_ini(tmp_path):
    bdir = tmp_path / "build-vk"
    bdir.mkdir()
    (bdir / build.EXE).write_bytes(b"MZ")
    (bdir / "SDL2.dll").write_bytes(b"dll")
    (bdir / "settings.ini").write_text("fullscreen=0\n")  # the dev's own, never shipped
    old = build.install(updates.GameVersion("v1", "x", "y", "release"), str(bdir))
    assert not os.path.exists(os.path.join(old, "settings.ini"))
    with open(os.path.join(old, "settings.ini"), "w") as f:
        f.write("fullscreen=1\n")  # the game wrote the player's choice
    new = build.install(updates.GameVersion("v2", "x", "y", "release"), str(bdir), carry_from="v1")
    assert open(os.path.join(new, "settings.ini")).read() == "fullscreen=1\n"
    assert os.path.isfile(os.path.join(new, "SDL2.dll"))
    # Rebuilding the current build keeps it too.
    again = build.install(updates.GameVersion("v2", "x", "y", "release"), str(bdir), carry_from="v2")
    assert open(os.path.join(again, "settings.ini")).read() == "fullscreen=1\n"
