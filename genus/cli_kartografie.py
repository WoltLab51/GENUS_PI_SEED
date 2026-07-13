"""Click command slice for the generated GENUS dependency and effect map."""
from __future__ import annotations

import json

import click

from genus import kartografie, kartografie_render


def register(main: click.Group) -> click.Group:
    @main.group("kartografie")
    def kartografie_group() -> None:
        """Build or verify the source-bound GENUS system map."""

    @kartografie_group.command("build")
    @click.option("--json-output", is_flag=True, help="Emit the map summary as JSON.")
    def build(json_output: bool) -> None:
        try:
            data = kartografie.build_map()
            paths = kartografie_render.write_artifacts(data)
        except (OSError, SyntaxError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        if json_output:
            click.echo(
                json.dumps(
                    {
                        "content_sha256": data["content_sha256"],
                        "paths": [str(path.relative_to(kartografie.ROOT)) for path in paths],
                        "summary": data["summary"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return
        click.echo(
            "[KARTE] "
            f"{data['summary']['modules']} Module, "
            f"{data['summary']['event_types']} Events, "
            f"{data['summary']['edges']} Kanten; "
            f"Inhalt {data['content_sha256'][:16]}"
        )
        for path in paths:
            click.echo(f"[KARTE] wrote {path.relative_to(kartografie.ROOT)}")

    @kartografie_group.command("check")
    @click.option("--json-output", is_flag=True, help="Emit the check result as JSON.")
    def check(json_output: bool) -> None:
        try:
            data = kartografie.build_map()
            stale = kartografie_render.stale_artifacts(data)
        except (OSError, SyntaxError, ValueError) as exc:
            raise click.ClickException(str(exc)) from exc
        result = {
            "content_sha256": data["content_sha256"],
            "ok": not stale,
            "stale": [str(path.relative_to(kartografie.ROOT)) for path in stale],
            "summary": data["summary"],
        }
        if json_output:
            click.echo(json.dumps(result, ensure_ascii=False, sort_keys=True))
        elif stale:
            click.echo(
                "[KARTE] stale: " + ", ".join(result["stale"]) + "; run `genus kartografie build`",
                err=True,
            )
        else:
            click.echo(
                "[KARTE] current: "
                f"{data['summary']['nodes']} Knoten, {data['summary']['edges']} Kanten, "
                f"Inhalt {data['content_sha256'][:16]}"
            )
        if stale:
            raise click.exceptions.Exit(1)

    return kartografie_group
