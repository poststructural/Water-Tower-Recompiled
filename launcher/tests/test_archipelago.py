import json
import os
import zipfile

import pytest

from animaniacs_launcher import archipelago, config


def test_args_off_by_default():
    assert archipelago.args(config.Settings()) == ([], {})


def test_args_with_password_in_env():
    st = config.Settings(ap_enabled=True, ap_server=" archipelago.gg:38281 ", ap_slot="Yakko",
                         ap_password="hunter2")
    a, env = archipelago.args(st)
    assert a == ["--ap-server", "archipelago.gg:38281", "--ap-slot", "Yakko"]
    assert env == {"ANI_AP_PASSWORD": "hunter2"} and "hunter2" not in a


def test_args_need_server_and_slot():
    with pytest.raises(archipelago.ApError):
        archipelago.args(config.Settings(ap_enabled=True, ap_server="x:1"))


def test_apworld_packs_the_world(tmp_path):
    src = tmp_path / "animaniacs"
    (src / "docs").mkdir(parents=True)
    (src / "__init__.py").write_text("x = 1\n")
    (src / "docs" / "setup_en.md").write_text("hi\n")
    (src / "__pycache__").mkdir()
    (src / "__pycache__" / "junk.pyc").write_bytes(b"\0")
    out = archipelago.write_apworld(str(tmp_path / "a.apworld"), str(src))
    names = sorted(n.replace("\\", "/") for n in zipfile.ZipFile(out).namelist())
    assert names == ["animaniacs/__init__.py", "animaniacs/docs/setup_en.md"]


def test_apworld_without_source(tmp_path):
    with pytest.raises(archipelago.ApError):
        archipelago.write_apworld(str(tmp_path / "a.apworld"), str(tmp_path / "none"))


def test_last_session_reads_the_games_state(tmp_path):
    base = tmp_path / "archipelago"
    folder = base / "123_Yakko_Warner"
    folder.mkdir(parents=True)
    (base / "last_seed_Yakko_Warner.txt").write_text("123\n")
    (folder / "ap_state.json").write_text(json.dumps(
        {"checked": [1, 2, 3], "items": [1095630849, 1095630850, 1095630849],
         "edgars_required": 30}))
    s = archipelago.last_session("Yakko Warner", str(tmp_path))
    assert (s.seed, s.checks, s.edgars, s.items, s.goal_edgars) == ("123", 3, 2, 3, 30)
    assert archipelago.last_session("Dot", str(tmp_path)) is None
