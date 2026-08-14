from __future__ import annotations

import os

import click

from genus import startup


def get_conn():
    """Format startup refusals for CLI users without duplicating gate semantics."""
    try:
        return startup.connect(os.environ.get("GENUS_DB_PATH", "genus.sqlite3"))
    except startup.StartupDatabaseError as exc:
        raise click.ClickException(str(exc)) from exc
