import json

import pytest

from booklet_printer import updater


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
    monkeypatch.setattr(updater, "config_path", lambda: tmp_path / "cfg" / "config.json")
    updater.save_config({"auto_update": False})
    assert updater.load_config() == {"auto_update": False}
