import sqlite3

import pytest

from genus import reactors
from genus.db import init_schema
from genus.sensor import mock_cpu, mock_memory


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
