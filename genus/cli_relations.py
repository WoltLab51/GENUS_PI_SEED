"""Relation command surface, registered onto the root Click group."""
from __future__ import annotations

from collections.abc import Callable
import json
import sys

import click

from genus import reactors, relation_semantics, sources
from genus.cli_format import _print_relations


def register(main: click.Group, get_conn: Callable) -> tuple[click.Command, ...]:
    @main.command("relate")
    @click.argument("subject")
    @click.argument("predicate")
    @click.argument("object")
    @click.option("--source", default="human", show_default=True)
    @click.option(
        "--derivation",
        default=None,
        help="Provenance/metadata of the edge, e.g. a weight 'cos=0.71'.",
    )
    def relate(subject: str, predicate: str, object: str, source: str,
               derivation: str | None) -> None:
        """Assert a provenanced relation between two entities."""
        conn = get_conn()
        try:
            result = reactors.observe_relation(
                conn, subject, predicate, object, source, derivation=derivation
            )
            subject, object = relation_semantics.canonical_pair(subject, predicate, object)
            mark = f"   · {source}" + (f" ({derivation})" if derivation else "")
            status = " unchanged" if result["unchanged"] else ""
            click.echo(f"[REL]{status} {subject} -[{predicate}]-> {object}{mark}")
        finally:
            conn.close()

    @main.command("relate-bulk")
    @click.option(
        "--chunk",
        default=5000,
        type=click.IntRange(min=1),
        show_default=True,
        help="Commit every N inputs (bounds lock duration and transaction size).",
    )
    def relate_bulk(chunk: int) -> None:
        """Assert JSONL relations from stdin using bounded transactions."""
        conn = get_conn()
        written = pending = unchanged = errors = since_commit = 0
        try:
            for line in sys.stdin:
                line = line.strip()
                if not line:
                    continue
                try:
                    edge = json.loads(line)
                    subject = edge["subject"]
                    predicate = edge["predicate"]
                    object_ = edge["object"]
                    source = edge.get("source", "human")
                    derivation = edge.get("derivation")
                    if not all(
                        isinstance(value, str) and value
                        for value in (subject, predicate, object_, source)
                    ) or (derivation is not None and not isinstance(derivation, str)):
                        raise ValueError("relation fields must be non-empty strings")
                except Exception:
                    errors += 1
                    continue
                try:
                    result = reactors.observe_relation(
                        conn,
                        subject,
                        predicate,
                        object_,
                        source,
                        derivation=derivation,
                        commit=False,
                    )
                    if result["unchanged"]:
                        unchanged += 1
                    else:
                        pending += 1
                    since_commit += 1
                    if since_commit >= chunk:
                        conn.commit()
                        written += pending
                        pending = since_commit = 0
                except Exception:
                    # observe_relation rolls the current transaction back. Never report
                    # writes from that abandoned chunk as durable ledger events.
                    conn.rollback()
                    errors += 1
                    pending = since_commit = 0
            conn.commit()
            written += pending
        finally:
            conn.close()
        click.echo(
            f"[REL-BULK] {written} Kante(n) geschrieben"
            + (f", {unchanged} unverändert" if unchanged else "")
            + (f", {errors} Zeile(n) übersprungen" if errors else "")
        )

    @main.command("unrelate")
    @click.argument("subject")
    @click.argument("predicate")
    @click.argument("object")
    @click.option(
        "--source", default=None,
        help="Retract only this source's edge (default: every source).",
    )
    def unrelate(subject: str, predicate: str, object: str, source: str | None) -> None:
        """Retract a relation through the normal event path."""
        conn = get_conn()
        try:
            reactors.retract_relation(conn, subject, predicate, object, source)
            where = f"· {source}" if source else "· all sources"
            click.echo(f"[REL] retracted {subject} -[{predicate}]-> {object}   {where}")
        finally:
            conn.close()

    @main.command("relations")
    @click.argument("subject", required=False)
    def relations(subject: str | None) -> None:
        """Show the knowledge graph, optionally for one subject."""
        conn = get_conn()
        try:
            _print_relations(
                sources.relations(conn, subject),
                label=lambda node: sources.display(conn, node),
            )
        finally:
            conn.close()

    return relate, relate_bulk, unrelate, relations
