"""What the newest version of the game build and of the launcher are.

Where updates come from is one setting, the update source, which can be:

  a GitLab project      https://gitlab.com/<owner>/<project> (the default):
                        game versions from its version tags and main branch,
                        launcher updates from its launcher-v* releases
  a GitHub repository   https://github.com/<owner>/<repo>: game versions from
                        its releases and main branch, launcher updates from
                        its launcher-v* releases
  an update file        an https:// address or a path ending in .json:
                        {"source": "<git address of the game's source>",
                         "launcher": {"version": "1.0.0", "url": "<installer>",
                                      "sha256": "<hex>", "notes": "...",
                                      "page": "<web page>"}}
                        so the files can be hosted anywhere; both keys are
                        optional
  any git repository    a git address (Codeberg, GitLab, a server), a folder
                        holding a checkout, or a .bundle file: game versions
                        from its tags and main branch; no launcher updates

For the game, either way:

  release channel  the newest version tag (v1.0.0; with a "-", as in
                   v1.1.0-rc1, a pre-release), or the newest GitHub release;
                   falls back to main while there is none
  main channel     the newest commit on main

A version is built from source on the player's machine, against their own
default.xbe: the recompiled code is generated from the game binary, so no
build of the game itself is downloaded.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

from urllib.parse import quote

from . import HOME_URL, __version__

API = "https://api.github.com"
LAUNCHER_TAG = "launcher-v"
DEFAULT_SOURCE = HOME_URL


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
    # The git address, folder or bundle the version is fetched from.
    source: str = ""


@dataclass
class LauncherRelease:
    version: str
    installer_url: str
    page_url: str
    notes: str = ""
    sha256: str = ""


@dataclass
class Source:
    # "gitlab", "github", "manifest" or "git"
    kind: str
    # The git address, folder or bundle to fetch the game's source from.
    git: str
    # owner/repo, for kind "github" or "gitlab"
    repo: str = ""
    # https://gitlab.example.org, for kind "gitlab"
    host: str = ""
    # The update file, for kind "manifest"
    manifest: str = ""


_GITHUB = re.compile(r"^https://github\.com/([\w.-]+/[\w.-]+?)(?:\.git)?/?$", re.I)
# gitlab.com, or any host with "gitlab" in its name; groups can nest.
_GITLAB = re.compile(r"^(https://[^/]*gitlab[^/]*)/((?:[\w.-]+/)+[\w.-]+?)(?:\.git)?/?$", re.I)


def parse_source(text: str) -> Source:
    s = (text or DEFAULT_SOURCE).strip().strip('"')
    m = _GITHUB.match(s)
    if m:
        return Source("github", f"https://github.com/{m.group(1)}.git", repo=m.group(1))
    m = _GITLAB.match(s.split("/-/", 1)[0])  # a page inside it: .../-/tree/main
    if m:
        host, repo = m.group(1).rstrip("/"), m.group(2)
        return Source("gitlab", f"{host}/{repo}.git", repo=repo, host=host)
    if s.lower().split("?")[0].endswith(".json"):
        return Source("manifest", "", manifest=s)
    return Source("git", s)


def _open(url: str, timeout: float, headers: dict | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": f"AnimaniacsLauncher/{__version__}",
                                               **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def _get(path: str, timeout: float = 15.0):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with _open(API + path, timeout, headers) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403 and e.headers.get("X-RateLimit-Remaining") == "0":
            raise UpdateError("GitHub's hourly limit for update checks was reached; try again later")
        if e.code in (403, 404, 451):
            raise UpdateError("the repository is not available on GitHub; set another "
                              "update source on the Updates tab")
        raise UpdateError(f"GitHub answered {e.code} for {path}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"could not reach GitHub: {getattr(e, 'reason', e)}")


def _gitlab(src: Source, path: str, timeout: float = 15.0):
    url = f"{src.host}/api/v4/projects/{quote(src.repo, safe='')}{path}"
    headers = {}
    token = os.environ.get("GITLAB_TOKEN")
    if token:
        headers["PRIVATE-TOKEN"] = token
    try:
        with _open(url, timeout, headers) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 404):
            raise UpdateError(f"{src.repo} was not found on {src.host} (is it private?)")
        raise UpdateError(f"GitLab answered {e.code} for {path}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"could not reach GitLab: {getattr(e, 'reason', e)}")


def read_manifest(where: str, timeout: float = 15.0) -> dict:
    try:
        if re.match(r"^https?://", where, re.I):
            with _open(where, timeout) as r:
                data = json.load(r)
        else:
            with open(where, encoding="utf-8") as f:
                data = json.load(f)
    except urllib.error.HTTPError as e:
        raise UpdateError(f"the update file answered {e.code}: {where}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"could not read the update file: {getattr(e, 'reason', e)}")
    except ValueError:
        raise UpdateError(f"the update file is not valid JSON: {where}")
    if not isinstance(data, dict):
        raise UpdateError("the update file should hold a JSON object")
    return data


def _git_source(src: Source) -> str:
    if src.kind != "manifest":
        return src.git
    git = read_manifest(src.manifest).get("source")
    if not isinstance(git, str) or not git:
        raise UpdateError("the update file has no \"source\" for the game")
    return git


def ls_remote(source: str, git: str | None = None) -> dict[str, str]:
    """{ref: sha} of a git address, folder or bundle."""
    if git is None:
        from .build import find_git
        git = find_git()
    if not git:
        raise UpdateError("Git is not installed (see Updates > Install missing tools)")
    try:
        p = subprocess.run([git, "ls-remote", "--tags", "--heads", source],
                           capture_output=True, text=True, timeout=60,
                           env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError) as e:
        raise UpdateError(f"could not run git: {e}")
    if p.returncode:
        err = (p.stderr.strip().splitlines() or ["no answer"])[-1]
        raise UpdateError(f"could not read {source}: {err}")
    refs = {}
    for line in p.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        if ref.endswith("^{}"):
            refs[ref[:-3]] = sha  # an annotated tag's commit
        else:
            refs.setdefault(ref, sha)
    return refs


_VERSION_TAG = re.compile(r"^refs/tags/(v\d+(?:\.\d+)*(?:-[\w.]+)?)$")


def from_refs(refs: dict[str, str], source: str, channel: str,
              prereleases: bool) -> GameVersion:
    def main() -> GameVersion:
        for head in ("refs/heads/main", "refs/heads/master"):
            if head in refs:
                sha = refs[head]
                return GameVersion(f"main-{sha[:7]}", sha, sha, "main", source=source)
        raise UpdateError(f"{source} has no main branch")

    if channel == "main":
        return main()
    tags = []
    for ref in refs:
        m = _VERSION_TAG.match(ref)
        if m and (prereleases or "-" not in m.group(1)):
            tags.append(m.group(1))
    if not tags:
        v = main()
        v.fell_back = True
        return v
    tag = max(tags, key=lambda t: (_version_tuple(t), "-" not in t))
    return GameVersion(tag, f"refs/tags/{tag}", refs[f"refs/tags/{tag}"], "release", source=source)


def _game_releases(releases: list[dict], prereleases: bool) -> list[dict]:
    return [r for r in releases
            if not r.get("draft")
            and (prereleases or not r.get("prerelease"))
            and not r.get("tag_name", "").startswith(LAUNCHER_TAG)]


def _github_main(repo: str, source: str) -> GameVersion:
    c = _get(f"/repos/{repo}/commits/main")
    sha = c["sha"]
    msg = c.get("commit", {}).get("message", "")
    return GameVersion(f"main-{sha[:7]}", sha, sha, "main",
                       notes=msg.split("\n", 1)[0], url=c.get("html_url", ""), source=source)


def latest_game(channel: str = "release", prereleases: bool = False,
                source: str = "") -> GameVersion:
    src = parse_source(source)
    if src.kind != "github":
        # GitLab too: its version tags are the releases, and a tag needs no
        # release page to be built.
        git = _git_source(src)
        return from_refs(ls_remote(git), git, channel, prereleases)
    if channel == "main":
        return _github_main(src.repo, src.git)
    rels = _game_releases(_get(f"/repos/{src.repo}/releases?per_page=30"), prereleases)
    if not rels:
        v = _github_main(src.repo, src.git)
        v.fell_back = True
        return v
    r = rels[0]  # the API lists newest first
    tag = r["tag_name"]
    ref = _get(f"/repos/{src.repo}/commits/{tag}")
    return GameVersion(tag, f"refs/tags/{tag}", ref["sha"], "release",
                       notes=r.get("body") or "", url=r.get("html_url", ""), source=src.git)


def from_bundle(path: str, channel: str = "release", prereleases: bool = True) -> GameVersion:
    """The version a source bundle (git bundle create) carries, for a manual
    update from a file."""
    if not os.path.isfile(path):
        raise UpdateError(f"not found: {path}")
    return from_refs(ls_remote(os.path.abspath(path)), os.path.abspath(path), channel, prereleases)


def _version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v.split("-", 1)[0])[:4])


def is_newer(candidate: str, current: str) -> bool:
    return _version_tuple(candidate) > _version_tuple(current)


def latest_launcher(source: str = "") -> LauncherRelease | None:
    """The newest launcher release, if it is newer than this launcher."""
    src = parse_source(source)
    if src.kind == "git":
        return None
    if src.kind == "gitlab":
        for r in _gitlab(src, "/releases?per_page=30"):
            tag = r.get("tag_name", "")
            if r.get("upcoming_release") or not tag.startswith(LAUNCHER_TAG):
                continue
            version = tag[len(LAUNCHER_TAG):]
            if not is_newer(version, __version__):
                return None
            links = (r.get("assets") or {}).get("links") or []
            exe = next((a for a in links if a.get("name", "").lower().endswith(".exe")), None)
            url = exe.get("direct_asset_url") or exe.get("url", "") if exe else ""
            page = (r.get("_links") or {}).get("self", f"{src.host}/{src.repo}/-/releases")
            return LauncherRelease(version, url, page, r.get("description") or "")
        return None
    if src.kind == "manifest":
        info = read_manifest(src.manifest).get("launcher")
        if not isinstance(info, dict) or not info.get("version"):
            return None
        version = str(info["version"]).lstrip("v")
        if not is_newer(version, __version__):
            return None
        return LauncherRelease(version, str(info.get("url", "")), str(info.get("page", "")),
                               str(info.get("notes", "")), str(info.get("sha256", "")).lower())
    for r in _get(f"/repos/{src.repo}/releases?per_page=30"):
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


def download(url: str, dest: str, progress=None, sha256: str = "") -> str:
    h = hashlib.sha256()
    try:
        with _open(url, 60) as r, open(dest + ".part", "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while buf := r.read(1 << 20):
                f.write(buf)
                h.update(buf)
                done += len(buf)
                if progress:
                    progress(done, total, os.path.basename(dest))
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"download failed: {getattr(e, 'reason', e)}")
    if sha256 and h.hexdigest() != sha256.lower():
        os.remove(dest + ".part")
        raise UpdateError("the download does not match the update file's sha256; not installed")
    os.replace(dest + ".part", dest)
    return dest
