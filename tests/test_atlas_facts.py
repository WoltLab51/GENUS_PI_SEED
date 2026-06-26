from pathlib import Path

from click.testing import CliRunner

from genus import cli
from genus.cli import _atlas_facts

ROOT = Path(__file__).resolve().parents[1]


def test_atlas_facts_file_is_current():
    # docs/genus_atlas_facts.md is a projection of the code; if it drifts (a new
    # sensor/reactor/detector/threshold was added without regenerating), fail.
    committed = (ROOT / "docs" / "genus_atlas_facts.md").read_text(encoding="utf-8")
    assert _atlas_facts().strip() == committed.strip(), (
        "docs/genus_atlas_facts.md is stale — regenerate with `genus atlas-facts`"
    )


def test_atlas_facts_command_runs():
    result = CliRunner().invoke(cli.main, ["atlas-facts"])
    assert result.exit_code == 0
    assert "Beobachtungs-Reaktoren" in result.output
    assert "Preset-Budget" in result.output
