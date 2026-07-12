"""Small, explicit budgets for the two root integration modules.

They are not style limits. They prevent the known concentration points from silently
absorbing another subsystem while registries/slices are being extracted.
"""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _lines(relative: str) -> int:
    return len((ROOT / relative).read_text(encoding="utf-8").splitlines())


def test_root_cli_keeps_shrinking_behind_registered_command_slices():
    # Audited baseline was 2,239 physical lines; the first extracted command slice
    # plus new diagnostics lands below this tighter ceiling.
    assert _lines("genus/cli.py") <= 2230


def test_companion_does_not_grow_past_the_audited_concentration_point():
    assert _lines("genus/companion.py") <= 1715
