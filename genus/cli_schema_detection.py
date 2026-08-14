from __future__ import annotations

import os
from pathlib import Path

import click

from genus import db, schema_detection


def register(root: click.Group) -> None:
    @root.group(name="db")
    def db_group() -> None:
        """Inspect the configured database without modifying it."""

    @db_group.command("status")
    @click.option("--path", "db_path", type=click.Path(path_type=Path))
    def db_status(db_path: Path | None) -> None:
        """Classify the database through the strict read-only connection path."""
        configured_path = db_path or Path(
            os.environ.get("GENUS_DB_PATH", "genus.sqlite3")
        )
        try:
            conn = db.connect_readonly(configured_path)
        except db.DatabaseNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc

        try:
            result = schema_detection.detect_schema(conn)
        finally:
            conn.close()

        migration_required = (
            "unknown"
            if result.migration_required is None
            else "yes" if result.migration_required else "no"
        )
        click.echo(f"Schema status: {result.status}")
        click.echo(f"Schema id: {result.schema_id or 'unknown'}")
        click.echo(f"Schema fingerprint: {result.fingerprint}")
        click.echo(f"Current schema: {'yes' if result.current else 'no'}")
        click.echo(f"Migration required: {migration_required}")
        click.echo("Database modified: no")
        raise click.exceptions.Exit(
            {"current": 0, "historical": 2, "unknown": 3}[result.status]
        )
