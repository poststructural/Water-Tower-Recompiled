import os
import struct

import pytest

from animaniacs_launcher import steam


def existing_shortcut() -> bytes:
    # One shortcut Steam wrote, with a field type the launcher only carries (0x07).
    n = steam.Node(0, "shortcuts", children=[steam.Node(0, "0", children=[
        steam.Node(2, "appid", struct.pack("<I", 0x80001234)),
        steam.Node(1, "AppName", b"Other Game"),
        steam.Node(1, "Exe", b'"C:\\Games\\other.exe"'),
        steam.Node(7, "SomeFuture64", b"\x01" * 8),
        steam.Node(0, "tags", children=[steam.Node(1, "0", b"favorite")]),
    ])])
    return steam.write_vdf([n])


def test_roundtrip_is_byte_identical():
    data = existing_shortcut()
    assert steam.write_vdf(steam.read_vdf(data)) == data


def test_add_to_accounts(tmp_path):
    ud = tmp_path / "userdata"
    (ud / "111" / "config").mkdir(parents=True)
    (ud / "111" / "config" / "shortcuts.vdf").write_bytes(existing_shortcut())
    (ud / "222").mkdir()
    (ud / "anonymous").mkdir()  # not an account folder
    exe = str(tmp_path / "AnimaniacsLauncher.exe")
    assert "Added" in steam.add_to_steam(exe, str(ud))
    for acct in ("111", "222"):
        nodes = steam.read_vdf((ud / acct / "config" / "shortcuts.vdf").read_bytes())
        entries = nodes[0].children
        ours = entries[-1]
        assert ours.get("AppName") == steam.APP_NAME
        assert ours.get("Exe") == f'"{os.path.abspath(exe)}"'
        appid = struct.unpack("<I", ours.children[0].value)[0]
        assert appid & 0x80000000
    entries = steam.read_vdf((ud / "111" / "config" / "shortcuts.vdf").read_bytes())[0].children
    assert [e.key for e in entries] == ["0", "1"] and entries[0].get("AppName") == "Other Game"
    assert any(n.startswith("shortcuts.vdf.launcher-backup") for n in os.listdir(ud / "111" / "config"))
    # A second time changes nothing.
    assert "already" in steam.add_to_steam(exe, str(ud))


def test_bad_file_is_refused():
    with pytest.raises(steam.SteamError):
        steam.read_vdf(b"\x00shortcuts\x00\x01AppName\x00no end")
    with pytest.raises(steam.SteamError):
        steam.read_vdf(b"\x00shortcuts\x00\x09odd\x00\x08\x08")


def test_no_accounts(tmp_path):
    (tmp_path / "userdata").mkdir()
    with pytest.raises(steam.SteamError):
        steam.add_to_steam("x.exe", str(tmp_path / "userdata"))
