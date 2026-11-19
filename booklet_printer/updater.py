"""Auto-update from GitHub Releases.

The application checks the latest release of the repository. When it is
newer than the running version and the program runs as a frozen Windows
executable, the new ``.exe`` is downloaded and swapped in place by a small
helper script once the application has quit, then relaunched.

For a private repository a GitHub token with read access to the repository
contents is required: set the ``BOOKLET_GITHUB_TOKEN`` environment variable
or put ``{"github_token": "..."}`` in the config file (see ``config.config_path``).
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
from .config import config_path, load_config, save_config  # noqa: F401  (re-exported)
from .i18n import t

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


def github_token() -> Optional[str]:
    return os.environ.get("BOOKLET_GITHUB_TOKEN") or load_config().get("github_token") or None


# ----------------------------------------------------------------- version

def parse_version(text: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", text.split("-")[0].split("+")[0])
    if not nums:
        raise ValueError(f"Invalid version: {text}")
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
            raise UpdateError(t("upd.no_release")) from exc
        raise UpdateError(t("upd.http_error", code=exc.code)) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(t("upd.unreachable", error=exc)) from exc
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
        raise UpdateError(t("upd.no_asset", tag=release.tag, asset=ASSET_NAME))
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
        raise UpdateError(t("upd.download_failed", error=exc)) from exc
    if dest.stat().st_size < 1024 * 1024:
        raise UpdateError(t("upd.incomplete"))
    return dest


def update_log_path() -> Path:
    return Path(tempfile.gettempdir()) / f"{APP_NAME}-update.log"


def build_update_script(new_exe: Path, current: Path, pids: list[int], log: Path) -> str:
    """Batch script that waits for the app to exit, swaps the exe and relaunches it.

    * waits for every given process (the PyInstaller one-file bootloader keeps a
      parent process alive, which holds a lock on the exe);
    * retries the copy for a while (antivirus scans can lock the new file);
    * clears the PyInstaller environment so that the relaunched one-file exe
      unpacks itself again instead of reusing the deleted temp folder of the
      old process (without this the new version silently fails to start);
    * writes a log next to the script for troubleshooting.
    """
    lines = [
        "@echo off",
        "setlocal EnableDelayedExpansion",
        f'set "LOG={log}"',
        'echo [%date% %time%] update started > "%LOG%"',
    ]
    for pid in pids:
        lines += [
            "set /a N=0",
            f":wait{pid}",
            f'tasklist /FI "PID eq {pid}" 2>NUL | find " {pid} " >NUL',
            "if not errorlevel 1 (",
            "  set /a N+=1",
            f"  if !N! LSS 120 ( ping -n 2 127.0.0.1 >NUL & goto wait{pid} )",
            ")",
        ]
    lines += [
        'echo [%date% %time%] application closed >> "%LOG%"',
        "set /a N=0",
        ":copy",
        f'copy /Y /B "{new_exe}" "{current}" >NUL 2>>"%LOG%"',
        "if errorlevel 1 (",
        "  set /a N+=1",
        '  echo copy attempt !N! failed >> "%LOG%"',
        "  if !N! LSS 60 ( ping -n 2 127.0.0.1 >NUL & goto copy )",
        '  echo giving up, relaunching the previous version >> "%LOG%"',
        "  goto launch",
        ")",
        'echo [%date% %time%] new version installed >> "%LOG%"',
        f'del /F /Q "{new_exe}" >NUL 2>&1',
        ":launch",
        "set PYINSTALLER_RESET_ENVIRONMENT=1",
        "set _MEIPASS2=",
        "set _PYI_APPLICATION_HOME_DIR=",
        "set _PYI_ARCHIVE_FILE=",
        "set _PYI_PARENT_PROCESS_LEVEL=",
        "set _PYI_SPLASH_IPC=",
        f'cd /d "{current.parent}"',
        f'start "" "{current}"',
        'echo [%date% %time%] relaunched >> "%LOG%"',
        '(goto) 2>NUL & del "%~f0"',
    ]
    return "\r\n".join(lines) + "\r\n"


def _clean_environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_PYI") or k.startswith("_MEIPASS"))}
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def install_and_restart(new_exe: Path) -> None:
    """Replace the running exe once it has exited, then relaunch it (Windows)."""
    if not is_frozen_windows():
        raise UpdateError(t("upd.windows_only"))
    current = Path(sys.executable).resolve()
    pids = [os.getpid()]
    parent = os.getppid()
    if parent and parent != os.getpid():
        pids.append(parent)  # PyInstaller one-file bootloader
    script = Path(tempfile.gettempdir()) / f"{APP_NAME}-update.cmd"
    script.write_text(build_update_script(Path(new_exe).resolve(), current, pids, update_log_path()), encoding="mbcs")
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=0x08000000 | 0x00000200,  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        close_fds=True,
        env=_clean_environment(),
        cwd=str(current.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
