"""Auto-update from GitHub Releases.

The application checks the latest release of the repository. When it is
newer than the running version and the program runs as a frozen Windows
executable, the new ``.exe`` is downloaded and swapped in place by a small
helper script once the application has quit, then relaunched.

For a private repository a GitHub token with read access to the repository
contents is required: set the ``BOOKLET_GITHUB_TOKEN`` environment variable
or put ``{"github_token": "..."}`` in the config file (see ``config_path``).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from . import APP_NAME, REPO, __version__

API = "https://api.github.com"
ASSET_NAME = "BookletPrinter.exe"


class UpdateError(RuntimeError):
    pass


@dataclass
class Release:
    version: str
    tag: str
    notes: str
    asset_url: Optional[str]  # API url of the Windows asset
    html_url: str


# ------------------------------------------------------------------ config

def config_path() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_NAME / "config.json"


def load_config() -> dict:
    try:
        return json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def github_token() -> Optional[str]:
    return os.environ.get("BOOKLET_GITHUB_TOKEN") or load_config().get("github_token") or None


# ----------------------------------------------------------------- version

def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text.split("-")[0].split("+")[0])
    if not nums:
        raise ValueError(f"Version invalide : {text}")
    return tuple(int(n) for n in nums[:4])


def is_newer(candidate: str, current: str = __version__) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


# ------------------------------------------------------------------ GitHub

def _request(url: str, accept: str = "application/vnd.github+json") -> urllib.request.Request:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": f"{APP_NAME}/{__version__}"})
    token = github_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def latest_release(timeout: float = 10) -> Release:
    try:
        with urllib.request.urlopen(_request(f"{API}/repos/{REPO}/releases/latest"), timeout=timeout) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError(
                "Aucune release trouvée. Si le dépôt est privé, configurez un jeton GitHub "
                "(menu Aide → Jeton GitHub)."
            ) from exc
        raise UpdateError(f"GitHub a répondu {exc.code}.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"Impossible de joindre GitHub : {exc}") from exc
    asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
    return Release(
        version=data["tag_name"].lstrip("v"),
        tag=data["tag_name"],
        notes=data.get("body") or "",
        asset_url=asset["url"] if asset else None,
        html_url=data.get("html_url", f"https://github.com/{REPO}/releases"),
    )


def check_for_update() -> Optional[Release]:
    """Return the latest release if it is newer than the running version."""
    rel = latest_release()
    return rel if is_newer(rel.version) else None


def is_frozen_windows() -> bool:
    return bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")


def download(release: Release, dest: Path, progress: Optional[Callable[[int, int], None]] = None) -> Path:
    if not release.asset_url:
        raise UpdateError(f"La release {release.tag} ne contient pas {ASSET_NAME}.")
    req = _request(release.asset_url, accept="application/octet-stream")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(256 * 1024):
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"Téléchargement impossible : {exc}") from exc
    if dest.stat().st_size < 1024 * 1024:
        raise UpdateError("Le fichier téléchargé semble incomplet.")
    return dest


def install_and_restart(new_exe: Path) -> None:
    """Replace the running exe once it has exited, then relaunch it (Windows)."""
    if not is_frozen_windows():
        raise UpdateError("La mise à jour automatique n'est disponible que pour l'exécutable Windows.")
    current = Path(sys.executable)
    script = Path(tempfile.gettempdir()) / f"{APP_NAME}-update.cmd"
    script.write_text(
        "@echo off\r\n"
        f"set PID={os.getpid()}\r\n"
        ":wait\r\n"
        'tasklist /FI "PID eq %PID%" 2>NUL | find "%PID%" >NUL && (timeout /t 1 /nobreak >NUL & goto wait)\r\n'
        "set N=0\r\n"
        ":copy\r\n"
        f'move /Y "{new_exe}" "{current}" >NUL 2>&1 || (set /a N+=1 & timeout /t 1 /nobreak >NUL & if %N% LSS 30 goto copy)\r\n'
        f'start "" "{current}"\r\n'
        '(goto) 2>NUL & del "%~f0"\r\n',
        encoding="mbcs" if sys.platform.startswith("win") else "utf-8",
    )
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=0x08000000,  # CREATE_NO_WINDOW
        close_fds=True,
    )
