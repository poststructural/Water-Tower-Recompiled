import os
import zipfile

import pytest

from animaniacs_launcher import gamefiles, xiso

from conftest import game_tree, make_xbe, make_xiso, write_tree


def read_tree(root):
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            p = os.path.join(d, n)
            out[os.path.relpath(p, root).replace(os.sep, "/")] = open(p, "rb").read()
    return out


@pytest.mark.parametrize("offset", [0, 0x2080000])
def test_xiso_extract_roundtrip(tmp_path, offset):
    files = game_tree()
    img = tmp_path / "game.iso"
    img.write_bytes(make_xiso(files, offset))
    assert xiso.is_xiso(str(img))
    listed = xiso.list_files(str(img))
    assert "resource/" in listed and "movies/intro.xmv" in listed
    seen = []
    xiso.extract(str(img), str(tmp_path / "out"), progress=lambda d, t, n: seen.append((d, t)))
    assert read_tree(tmp_path / "out") == files
    assert seen[-1][0] == seen[-1][1] == sum(map(len, files.values()))


def test_xiso_rejects_traversal(tmp_path):
    img = tmp_path / "bad.iso"
    img.write_bytes(make_xiso({"..": b"x"}))
    with pytest.raises(xiso.XisoError):
        xiso.list_files(str(img))


def test_not_an_image(tmp_path):
    p = tmp_path / "x.iso"
    p.write_bytes(b"\0" * 200000)
    assert not xiso.is_xiso(str(p))
    with pytest.raises(ValueError):
        gamefiles.source_kind(str(p))


def test_parse_xbe():
    info = gamefiles.parse_xbe(make_xbe(region=1))
    assert info.title_id == gamefiles.TITLE_ID and info.title == "Animaniacs" and info.region == "US"


def test_check_dir_ok_and_problems(tmp_path):
    write_tree(tmp_path / "g", game_tree())
    assert gamefiles.check_dir(str(tmp_path / "g")).ok

    write_tree(tmp_path / "other", {**game_tree(make_xbe(title_id=0x4D530004, title="Halo")),
                                    "movies/": b""})
    os.remove(tmp_path / "other" / "tkaXBoxDSPImage.bin")
    chk = gamefiles.check_dir(str(tmp_path / "other"))
    assert not chk.ok
    assert any("Halo" in p for p in chk.problems)
    assert any("tkaXBoxDSPImage.bin" in p for p in chk.problems)


def test_import_folder_in_place(tmp_path):
    write_tree(tmp_path / "wrap" / "Animaniacs", game_tree())
    got = gamefiles.import_game(str(tmp_path / "wrap"), str(tmp_path / "dest"))
    assert got == str(tmp_path / "wrap" / "Animaniacs")
    assert not (tmp_path / "dest").exists()


def test_import_iso_and_zip(tmp_path):
    files = game_tree()
    img = tmp_path / "game.iso"
    img.write_bytes(make_xiso(files))
    got = gamefiles.import_game(str(img), str(tmp_path / "from_iso"))
    assert read_tree(got) == files

    z = tmp_path / "game.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for k, v in files.items():
            zf.writestr("Animaniacs/" + k, v)
    got = gamefiles.import_game(str(z), str(tmp_path / "from_zip"))
    assert got == str(tmp_path / "from_zip")
    assert read_tree(got) == files
    assert not (tmp_path / "from_zip.partial").exists()


def test_import_bad_iso_leaves_nothing(tmp_path):
    img = tmp_path / "game.iso"
    img.write_bytes(make_xiso({"default.xbe": make_xbe(title_id=1)}))
    with pytest.raises(ValueError):
        gamefiles.import_game(str(img), str(tmp_path / "dest"))
    assert not (tmp_path / "dest").exists() and not (tmp_path / "dest.partial").exists()


def test_cancel(tmp_path):
    img = tmp_path / "game.iso"
    img.write_bytes(make_xiso(game_tree()))
    with pytest.raises(xiso.XisoError):
        gamefiles.import_game(str(img), str(tmp_path / "dest"), cancelled=lambda: True)
