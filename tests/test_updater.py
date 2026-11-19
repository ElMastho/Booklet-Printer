import json

import pytest

from booklet_printer import config, updater


@pytest.mark.parametrize(
    "candidate,current,newer",
    [
        ("1.0.1", "1.0.0", True),
        ("1.1", "1.0.9", True),
        ("2.0.0", "10.0.0", False),
        ("1.0.0", "1.0.0", False),
        ("1.0", "1.0.0", False),
        ("v1.2.0", "1.1.9", True),
    ],
)
def test_is_newer(candidate, current, newer):
    assert updater.is_newer(candidate.lstrip("v"), current) is newer


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()

    def read(self, *a):
        data, self.payload = self.payload, b""
        return data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_latest_release_parses_assets(monkeypatch):
    payload = {
        "tag_name": "v9.9.9",
        "body": "notes",
        "html_url": "https://example.invalid/r",
        "assets": [{"name": "other.zip", "url": "u1"}, {"name": updater.ASSET_NAME, "url": "u2"}],
    }
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(payload))
    rel = updater.check_for_update()
    assert rel is not None and rel.version == "9.9.9" and rel.asset_url == "u2"


def test_no_update_when_same_version(monkeypatch):
    payload = {"tag_name": "v" + updater.__version__, "assets": []}
    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda req, timeout=0: FakeResponse(payload))
    assert updater.check_for_update() is None


def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "cfg" / "config.json")
    config.save_config({"auto_update": False})
    assert config.load_config() == {"auto_update": False}


def test_update_script(tmp_path):
    from pathlib import Path

    script = updater.build_update_script(
        Path(r"C:\Temp\new.exe"), Path(r"C:\Apps\BookletPrinter.exe"), [111, 222], Path(r"C:\Temp\u.log")
    )
    assert script.count("\r\n") > 10
    assert ':wait111' in script and ':wait222' in script
    assert 'copy /Y /B "C:\\Temp\\new.exe" "C:\\Apps\\BookletPrinter.exe"' in script
    assert "PYINSTALLER_RESET_ENVIRONMENT=1" in script
    assert script.index("PYINSTALLER_RESET_ENVIRONMENT") < script.index('start ""')
