import json
import os
import zipfile

import pytest

from animaniacs_launcher import mods


def make_mod(folder, mid, files, **meta):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "mod.json"), "w") as f:
        json.dump({"id": mid, "name": mid.title(), "version": "1.0", **meta}, f)
    for rel, data in files.items():
        p = os.path.join(folder, "files", *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(data)
    return folder


def zip_dir(folder, dest, prefix=""):
    with zipfile.ZipFile(dest, "w") as z:
        for d, _, names in os.walk(folder):
            for n in names:
                full = os.path.join(d, n)
                z.write(full, prefix + os.path.relpath(full, folder).replace(os.sep, "/"))
    return dest


@pytest.fixture
def game(tmp_path):
    g = tmp_path / "game"
    (g / "resource").mkdir(parents=True)
    (g / "default.xbe").write_bytes(b"XBEH")
    (g / "resource" / "a.bin").write_bytes(b"orig-a")
    (g / "resource" / "b.bin").write_bytes(b"orig-b")
    return str(g)


def test_install_order_and_overlay(tmp_path, game):
    one = make_mod(tmp_path / "src1", "one", {"Resource/A.BIN": b"one-a", "resource/new.bin": b"new"})
    two = make_mod(tmp_path / "src2", "two", {"resource/a.bin": b"two-a"}, author="me")
    mods.install(zip_dir(one, tmp_path / "one.zip", prefix="one/"))
    mods.install(str(two))
    ms = mods.load()
    assert [m.id for m in ms] == ["one", "two"] and ms[1].author == "me"
    assert mods.conflicts(ms) == {"resource/a.bin": ["one", "two"]}

    out = mods.prepare(game, log=lambda s: None)
    assert out != game
    read = lambda *p: open(os.path.join(out, *p), "rb").read()
    assert read("resource", "a.bin") == b"two-a"  # later wins, case ignored
    assert read("resource", "b.bin") == b"orig-b"
    assert read("resource", "new.bin") == b"new"
    assert not os.path.exists(os.path.join(out, "Resource", "A.BIN")) or os.name == "nt"
    assert open(os.path.join(game, "resource", "a.bin"), "rb").read() == b"orig-a"

    ms.reverse()
    mods.save(ms)
    assert read("resource", "a.bin") == b"two-a"
    out = mods.prepare(game, log=lambda s: None)
    assert read("resource", "a.bin") == b"one-a"

    for m in ms:
        m.enabled = False
    mods.save(ms)
    assert mods.prepare(game) == game


def test_upgrade_keeps_state_and_remove(tmp_path):
    src = make_mod(tmp_path / "s", "hd", {"resource/x.bin": b"1"})
    mods.install(str(src))
    ms = mods.load()
    ms[0].enabled = False
    mods.save(ms)
    make_mod(tmp_path / "s", "hd", {"resource/x.bin": b"2"}, version="2.0")
    m = mods.install(str(src))
    assert m.version == "2.0" and not m.enabled and len(mods.load()) == 1
    mods.remove("hd")
    assert mods.load() == [] and not os.path.exists(os.path.join(mods.root(), "hd"))


def test_bad_mods_are_refused(tmp_path):
    with pytest.raises(mods.ModError, match="default.xbe"):
        mods.install(str(make_mod(tmp_path / "x", "x", {"default.xbe": b"no"})))
    with pytest.raises(mods.ModError, match="id"):
        mods.install(str(make_mod(tmp_path / "y", "Bad Id!", {"a": b""})))
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("mod.json", json.dumps({"id": "evil"}))
        z.writestr("../escape.txt", "x")
    with pytest.raises(mods.ModError, match="unsafe"):
        mods.install(str(evil))
    assert mods.load() == []
