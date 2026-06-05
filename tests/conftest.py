import sqlite3

import pytest

from genus import ledger, rules
from genus.db import init_schema
from genus.sensor import mock_cpu


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
    observation_id = ledger.append(
        conn,
        "observation_created",
        {
            "source": reading["source"],
            "raw_value": reading["raw_value"],
            "unit": reading["unit"],
            "interval": reading["interval"],
        },
    )
    ledger.append(
        conn,
        "evidence_recorded",
        {
            "observation_id": observation_id,
            "metric_key": rules.METRIC_KEY,
            "metric_value": reading["raw_value"],
        },
    )
    return rules.apply_cpu_threshold(conn)
