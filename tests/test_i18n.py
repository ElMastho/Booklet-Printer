import sys

import pytest

from booklet_printer import i18n


def test_catalogs_have_the_same_keys():
    assert set(i18n.EN) == set(i18n.FR)


def test_placeholders_match():
    import string

    fmt = string.Formatter()
    for key, en in i18n.EN.items():
        fields_en = {f for _, f, _, _ in fmt.parse(en) if f}
        fields_fr = {f for _, f, _, _ in fmt.parse(i18n.FR[key]) if f}
        assert fields_en == fields_fr, key


def test_switch_language():
    try:
        assert i18n.set_language("fr") == "fr"
        assert i18n.t("page.blank") == "Page blanche"
        i18n.set_language("en")
        assert i18n.t("page.blank") == "Blank page"
        assert i18n.t("does.not.exist") == "does.not.exist"
    finally:
        i18n.set_language("en")


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Windows uses the UI language API first")
def test_system_language_from_env(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.system_language() == "fr"
