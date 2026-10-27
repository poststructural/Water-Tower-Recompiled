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
    v = updates.latest_game("release", source="https://github.com/Unowa001/AnimaniacsRecompiled")
    assert (v.name, v.ref, v.fell_back) == ("v0.2.0", "refs/tags/v0.2.0", False)


def test_release_channel_falls_back_to_main(monkeypatch):
    monkeypatch.setattr(updates, "_get", fake_get({
        "/repos/Unowa001/AnimaniacsRecompiled/releases": [],
        "/repos/Unowa001/AnimaniacsRecompiled/commits/main": MAIN,
    }))
    v = updates.latest_game("release", source="https://github.com/Unowa001/AnimaniacsRecompiled")
    assert v.fell_back and v.name == "main-abcdef1" and v.notes == "Faster level loads"


def test_launcher_update(monkeypatch):
    rels = [{"tag_name": "v1.0"},
            {"tag_name": "launcher-v9.0.0", "html_url": "p",
             "assets": [{"name": "AnimaniacsLauncherSetup-9.0.0.exe", "browser_download_url": "d"}]}]
    monkeypatch.setattr(updates, "_get", fake_get({"/repos/": rels}))
    lr = updates.latest_launcher("https://github.com/a/b")
    assert lr and lr.version == "9.0.0" and lr.installer_url == "d"
    rels[1]["tag_name"] = "launcher-v0.0.1"
    assert updates.latest_launcher("https://github.com/a/b") is None


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


def test_build_writes_a_log_and_checks_space(monkeypatch):
    import collections
    import pytest
    monkeypatch.setattr(build, "supported", lambda: None)
    monkeypatch.setattr(build, "detect", lambda: build.Toolchain("git", "bash", ["py"], True))
    Usage = collections.namedtuple("Usage", "total used free")
    monkeypatch.setattr(build.shutil, "disk_usage", lambda p: Usage(0, 0, 2e9))
    v = updates.GameVersion("main-abc", "x", "abc", "main")
    with pytest.raises(build.BuildError, match="needs about 4 GB"):
        build.build(v, "g", config.Settings(), log=lambda s: None)

    monkeypatch.setattr(build.shutil, "disk_usage", lambda p: Usage(0, 0, 100e9))

    def fail(version, game_dir, settings, log, cancelled, step, tc):
        log("compiling...")
        raise build.BuildError("ninja failed (exit code 1)")
    monkeypatch.setattr(build, "_build", fail)
    with pytest.raises(build.BuildError, match="full log") as e:
        build.build(v, "g", config.Settings(), log=lambda s: None)
    logs = [n for n in os.listdir(config.sub("logs")) if n.startswith("build-main-abc")]
    text = open(config.sub("logs", logs[0])).read()
    assert "compiling..." in text and "ninja failed" in text and logs[0] in str(e.value)

    def cancel(*a):
        raise build.Cancelled("cancelled")
    monkeypatch.setattr(build, "_build", cancel)
    with pytest.raises(build.Cancelled) as e:
        build.build(v, "g", config.Settings(), log=lambda s: None)
    assert str(e.value) == "cancelled"


def _git(*args, cwd=None):
    import subprocess
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


def _repo(tmp_path):
    repo = tmp_path / "repo"
    _git("init", "-q", "-b", "main", str(repo))
    (repo / "README.md").write_text("one")
    _git("add", "-A", cwd=repo)
    _git("commit", "-qm", "one", cwd=repo)
    _git("tag", "v1.0.0", cwd=repo)
    (repo / "README.md").write_text("two")
    _git("commit", "-qam", "two", cwd=repo)
    _git("tag", "-a", "v1.1.0-rc1", "-m", "rc", cwd=repo)
    (repo / "README.md").write_text("three")
    _git("commit", "-qam", "three", cwd=repo)
    return repo


def test_parse_source():
    d = updates.parse_source("")
    assert (d.kind, d.repo, d.git) == ("gitlab", "unowa001/animaniacs-remastered",
                                       "https://gitlab.com/unowa001/animaniacs-remastered.git")
    t = updates.parse_source("https://gitlab.com/g/sub/proj/-/tree/main")
    assert (t.kind, t.repo, t.host) == ("gitlab", "g/sub/proj", "https://gitlab.com")
    assert updates.parse_source("https://github.com/a/b.git").kind == "github"
    assert updates.parse_source("https://example.org/ani/update.json").kind == "manifest"
    assert updates.parse_source("https://codeberg.org/a/b.git").kind == "git"
    assert updates.parse_source(r"C:\src\AnimaniacsRecompiled").kind == "git"


def test_git_source_versions_and_checkout(tmp_path):
    repo = _repo(tmp_path)
    v = updates.latest_game("release", source=str(repo))
    assert (v.name, v.ref, v.source) == ("v1.0.0", "refs/tags/v1.0.0", str(repo))
    assert updates.latest_game("release", True, str(repo)).name == "v1.1.0-rc1"
    m = updates.latest_game("main", source=str(repo))
    assert m.name.startswith("main-") and m.channel == "main"

    r = build.Runner(lambda s: None)
    git = build.find_git()
    src = build.checkout(r, git, v)
    assert open(os.path.join(src, "README.md")).read() == "one"
    build.checkout(r, git, m)
    assert open(os.path.join(src, "README.md")).read() == "three"


def test_update_from_a_bundle(tmp_path):
    repo = _repo(tmp_path)
    bundle = tmp_path / "update.bundle"
    _git("bundle", "create", str(bundle), "--all", cwd=repo)
    v = updates.from_bundle(str(bundle))
    assert v.name == "v1.1.0-rc1"
    src = build.checkout(build.Runner(lambda s: None), build.find_git(), v)
    assert open(os.path.join(src, "README.md")).read() == "two"
    m = updates.from_bundle(str(bundle), "main")
    build.checkout(build.Runner(lambda s: None), build.find_git(), m)
    assert open(os.path.join(src, "README.md")).read() == "three"


def test_manifest_source(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    man = tmp_path / "update.json"
    man.write_text(json.dumps({"source": str(repo), "launcher": {
        "version": "9.1.0", "url": "https://example.org/setup.exe", "sha256": "AB"}}))
    assert updates.latest_game("release", source=str(man)).name == "v1.0.0"
    lr = updates.latest_launcher(str(man))
    assert lr and (lr.version, lr.installer_url, lr.sha256) == ("9.1.0", "https://example.org/setup.exe", "ab")
    man.write_text(json.dumps({"launcher": {"version": "0.0.1"}}))
    assert updates.latest_launcher(str(man)) is None
    assert updates.latest_launcher(str(repo)) is None


def test_download_checks_sha256(tmp_path):
    import hashlib
    f = tmp_path / "setup.exe"
    f.write_bytes(b"installer")
    url = f.as_uri()
    good = hashlib.sha256(b"installer").hexdigest()
    assert updates.download(url, str(tmp_path / "a.exe"), sha256=good)
    import pytest
    with pytest.raises(updates.UpdateError, match="sha256"):
        updates.download(url, str(tmp_path / "b.exe"), sha256="0" * 64)
    assert not os.path.exists(tmp_path / "b.exe")


def test_gitlab_launcher_release(monkeypatch):
    rels = [{"tag_name": "v1.0.0"},
            {"tag_name": "launcher-v9.0.0", "description": "n", "_links": {"self": "p"},
             "assets": {"links": [{"name": "AnimaniacsLauncherSetup-9.0.0.exe", "url": "u",
                                   "direct_asset_url": "d"}]}}]
    seen = []
    monkeypatch.setattr(updates, "_gitlab", lambda src, path: seen.append((src.repo, path)) or rels)
    lr = updates.latest_launcher("")
    assert lr and (lr.version, lr.installer_url, lr.page_url) == ("9.0.0", "d", "p")
    assert seen[0] == ("unowa001/animaniacs-remastered", "/releases?per_page=30")
