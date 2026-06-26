import tomllib
from pathlib import Path

import genus


def test_package_version_matches_pyproject():
    # Guard against version drift: the package version and pyproject must agree,
    # so the declared version can never silently lag what is shipped.
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert genus.__version__ == data["project"]["version"]


def test_visual_atlas_stamp_matches_version():
    # Keep the visual atlas from silently drifting: its version stamp must match
    # the package, so a release forces a glance at the state-dependent diagrams
    # (maturity, dispatch, eye-vs-mind, journey) and an update where they drifted.
    atlas = Path(__file__).resolve().parents[1] / "docs" / "genus_visual_atlas.html"
    assert f"v{genus.__version__}" in atlas.read_text(encoding="utf-8")
