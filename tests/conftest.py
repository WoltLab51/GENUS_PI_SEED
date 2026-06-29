import sqlite3

import pytest

from genus import reactors
from genus.db import init_schema
from genus.sensor import (
    mock_activity,
    mock_cpu,
    mock_disk,
    mock_memory,
    mock_temperature,
    mock_weather,
)


@pytest.fixture(autouse=True)
def _isolate_pause(tmp_path, monkeypatch):
    # Tests must never read the AMBIENT pause flag (e.g. a paused Pi during a deploy's test
    # run, where GENUS_DB_PATH points at the real ledger). Pin the marker at a per-test temp
    # path that does not exist -> is_paused() is False unless the test sets it itself.
    monkeypatch.setenv("GENUS_PAUSE_FILE", str(tmp_path / "paused"))


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    init_schema(c)
    yield c
    c.close()


class ConnProxy:
    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        return None


@pytest.fixture
def cli_conn(conn):
    return ConnProxy(conn)


def observe_cpu_value(conn, value: float) -> list[str]:
    reading = mock_cpu(value)
    result = reactors.observe_cpu_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]


def observe_memory_value(conn, value: float) -> list[str]:
    reading = mock_memory(value)
    result = reactors.observe_memory_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]


def observe_disk_value(conn, value: float) -> list[str]:
    reading = mock_disk(value)
    result = reactors.observe_disk_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]


def observe_activity_value(conn, value: float) -> list[str]:
    reading = mock_activity(value)
    result = reactors.observe_activity_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]


def observe_temperature_value(conn, value: float) -> list[str]:
    reading = mock_temperature(value)
    result = reactors.observe_temperature_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]


def observe_weather_value(conn, value: float) -> list[str]:
    reading = mock_weather(value)
    result = reactors.observe_weather_reading(conn, reading)
    return [event["event_type"] for event in result["events"]]
