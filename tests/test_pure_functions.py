"""Tests for the pure functions (no network, no disk beyond tmp_path)."""

from datetime import date, datetime

import pytest

from config import ConfigError, choose_instance, load_instances
from docx_builder import _period_text, _sanitize_text
from generate_report import filter_by_technician
from glpi_api import _parse_datetime, _total_from_content_range
from image_utils import detect_mime
from models import ACTOR_ASSIGNED, ACTOR_OBSERVER, Actor, Ticket, Update, html_to_text


@pytest.mark.parametrize(
    "value, expected",
    [("0-99/148", 148), ("100-147/148", 148), ("0-0/0", 0), (None, None), ("", None), ("no-total", None), ("0-9/x", None)],
)
def test_total_from_content_range(value, expected):
    assert _total_from_content_range(value) == expected


def test_parse_datetime():
    assert _parse_datetime("2026-08-03 08:12:40") == datetime(2026, 8, 3, 8, 12, 40)
    assert _parse_datetime(None) is None
    assert _parse_datetime("not a date") is None


@pytest.mark.parametrize(
    "head, mime",
    [
        (b"\x89PNG\r\n\x1a\n...", "image/png"),
        (b"\xff\xd8\xff\xe0...", "image/jpeg"),
        (b"GIF89a...", "image/gif"),
        (b"BM...", "image/bmp"),
        (b"<!DOCTYPE html><html>", None),  # an error page must never become an "image"
        (b"", None),
    ],
)
def test_detect_mime(head, mime):
    assert detect_mime(head) == mime


def test_html_to_text_unescapes_entities_and_strips_tags():
    # GLPI 10 returns rich text with the HTML encoded as entities
    encoded = "&#60;p&#62;First&#60;/p&#62;&#60;p&#62;Line&#60;br&#62;break&#60;/p&#62;&#60;ul&#62;&#60;li&#62;item&#60;/li&#62;&#60;/ul&#62;"
    assert html_to_text(encoded) == "First\n\nLine\nbreak\n\n- item"


def test_sanitize_text():
    assert _sanitize_text("normal text") == "normal text"
    assert _sanitize_text("see data:image/png;base64,iVBORw0KGgo") == ""
    long_but_legit = "word " * 400  # long, but with spaces: passes untouched
    assert _sanitize_text(long_but_legit) == long_but_legit
    junk = "x" * 2000  # long and without spaces: most likely invalid data
    assert _sanitize_text(junk).startswith("[Trecho muito longo omitido")


def test_period_text():
    assert _period_text((date(2026, 8, 1), date(2026, 8, 31))) == "Agosto de 2026"
    assert _period_text((date(2026, 8, 1), date(2026, 8, 15))) == "01/08/2026 a 15/08/2026"
    assert _period_text(None) == ""


def _ticket(id_, assignee=None, observer=None, solution_author=None):
    t = Ticket(id_, f"Ticket {id_}", "Solucionado", "Média", "-", "-", "", None, None)
    if assignee:
        t.actors.append(Actor(ACTOR_ASSIGNED, assignee))
    if observer:
        t.actors.append(Actor(ACTOR_OBSERVER, observer))
    if solution_author:
        t.updates.append(Update(None, solution_author, "done", is_solution=True))
    return t


def test_filter_by_technician_counts_observer_and_author_and_groups():
    tickets = [
        _ticket(1, assignee="Bruno Carvalho"),
        _ticket(2, observer="Ana Ribeiro"),  # technician only as observer
        _ticket(3, solution_author="Ana Ribeiro"),  # technician only as solution author
        _ticket(4, assignee="Diego Martins"),  # not in the list
    ]
    kept, by_ticket = filter_by_technician(tickets, "ana ribeiro, Bruno")
    assert [t.id for t in kept] == [2, 3, 1]  # grouped by name, original order within each group
    assert by_ticket == {1: "Bruno Carvalho", 2: "Ana Ribeiro", 3: "Ana Ribeiro"}


def test_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[instances.main]\nname = "Main"\nurl = "https://glpi.example.com/"\ntechnicians = ["Ana", " "]\n',
        encoding="utf-8",
    )
    instances = load_instances(str(path))
    main = choose_instance(instances, None)  # only one: no need to name it
    assert main.url == "https://glpi.example.com"
    assert main.technicians == ["Ana"]
    with pytest.raises(ConfigError):
        choose_instance(instances, "other")


def test_config_missing_or_invalid(tmp_path):
    with pytest.raises(ConfigError):
        load_instances(str(tmp_path / "does_not_exist.toml"))
    invalid = tmp_path / "config.toml"
    invalid.write_text('[instances."with space"]\nurl = "https://x"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_instances(str(invalid))
