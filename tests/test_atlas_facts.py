from pathlib import Path

from click.testing import CliRunner

from genus import cli
from genus.cli import _atlas_facts

ROOT = Path(__file__).resolve().parents[1]


def test_atlas_facts_file_is_current():
    # docs/generated/ATLAS_FACTS.md is a projection of the code; if it drifts (a new
    # sensor/reactor/detector/threshold was added without regenerating), fail.
    committed = (ROOT / "docs" / "generated" / "ATLAS_FACTS.md").read_text(encoding="utf-8")
    assert _atlas_facts().strip() == committed.strip(), (
        "docs/generated/ATLAS_FACTS.md is stale — regenerate with `genus atlas-facts`"
    )


def test_atlas_facts_command_runs():
    result = CliRunner().invoke(cli.main, ["atlas-facts"])
    assert result.exit_code == 0
    assert "Beobachtungs-Reaktoren" in result.output
    assert "Preset-Budget" in result.output


def test_atlas_facts_derives_goal_and_dispatch_state_not_hand_typed():
    # Ronnys Frage (2026-07-03): "kann die Doku nicht völlig abgeleitet sein?" -- Ziel-Graph-
    # Zustand und Dispatch-Umfang sind Code-Zustand, keine Prosa, die von Hand nachgeführt
    # werden muss (und deshalb driften kann)
    text = _atlas_facts()
    assert "Ziele:" in text and "Fähigkeiten" in text and "fehlt" in text
    assert "Verstehens-Raster:" in text and "Feinblätter" in text
    assert "Companion-Dispatch:" in text and "handelbare Zellen" in text
    assert "Werkzeugbauer:" in text and "registrierte Werkzeuge" in text
