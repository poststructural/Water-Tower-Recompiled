"""What the newest version of the game build and of the launcher are.

Game versions come from the repository on GitHub:

  release channel  the newest published release whose tag is not a
                   launcher release ("launcher-v*"); falls back to main
                   while the repository has no releases yet
  main channel     the newest commit on main

A version is built from source on the player's machine, against their own
default.xbe: the recompiled code is generated from the game binary, so no
build of the game itself is downloaded.

Launcher versions are releases tagged "launcher-v<version>", carrying the
installer as an asset.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from . import REPO, __version__

API = "https://api.github.com"
LAUNCHER_TAG = "launcher-v"


class UpdateError(Exception):
    pass


@dataclass
class GameVersion:
    # Shown to the player and used as the build folder name.
    name: str
    # What git checks out.
    ref: str
    sha: str
    channel: str
    notes: str = ""
    url: str = ""
    # Set when the release channel had nothing and main was used instead.
    fell_back: bool = False


@dataclass
class LauncherRelease:
    version: str
    installer_url: str
    page_url: str
    notes: str = ""


def _get(path: str, timeout: float = 15.0):
    req = urllib.request.Request(API + path, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"AnimaniacsLauncher/{__version__}",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0":
            raise UpdateError("GitHub's hourly limit for update checks was reached; try again later")
        if e.code == 404:
            raise UpdateError(f"{REPO} was not found on GitHub (is it private?)")
        raise UpdateError(f"GitHub answered {e.code} for {path}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"could not reach GitHub: {getattr(e, 'reason', e)}")


def _game_releases(releases: list[dict], prereleases: bool) -> list[dict]:
    return [r for r in releases
            if not r.get("draft")
            and (prereleases or not r.get("prerelease"))
            and not r.get("tag_name", "").startswith(LAUNCHER_TAG)]


def latest_main() -> GameVersion:
    c = _get(f"/repos/{REPO}/commits/main")
    sha = c["sha"]
    msg = c.get("commit", {}).get("message", "")
    return GameVersion(f"main-{sha[:7]}", sha, sha, "main",
                       notes=msg.split("\n", 1)[0], url=c.get("html_url", ""))


def latest_game(channel: str = "release", prereleases: bool = False) -> GameVersion:
    if channel == "main":
        return latest_main()
    rels = _game_releases(_get(f"/repos/{REPO}/releases?per_page=30"), prereleases)
    if not rels:
        v = latest_main()
        v.fell_back = True
        return v
    r = rels[0]  # the API lists newest first
    tag = r["tag_name"]
    ref = _get(f"/repos/{REPO}/commits/{tag}")
    return GameVersion(tag, f"refs/tags/{tag}", ref["sha"], "release",
                       notes=r.get("body") or "", url=r.get("html_url", ""))


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:4])


def is_newer(candidate: str, current: str) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def latest_launcher() -> LauncherRelease | None:
    """The newest launcher release, if it is newer than this launcher."""
    for r in _get(f"/repos/{REPO}/releases?per_page=30"):
        tag = r.get("tag_name", "")
        if r.get("draft") or r.get("prerelease") or not tag.startswith(LAUNCHER_TAG):
            continue
        version = tag[len(LAUNCHER_TAG):]
        if not is_newer(version, __version__):
            return None
        asset = next((a for a in r.get("assets", [])
                      if a["name"].lower().endswith(".exe")), None)
        return LauncherRelease(version, asset["browser_download_url"] if asset else "",
                               r.get("html_url", ""), r.get("body") or "")
    return None


def download(url: str, dest: str, progress=None) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"AnimaniacsLauncher/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest + ".part", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while buf := r.read(1 << 20):
                f.write(buf)
                done += len(buf)
                if progress:
                    progress(done, total, os.path.basename(dest))
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"download failed: {getattr(e, 'reason', e)}")
    os.replace(dest + ".part", dest)
    return dest
