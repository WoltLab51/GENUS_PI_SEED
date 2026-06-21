import tomllib
from pathlib import Path

import genus


def test_package_version_matches_pyproject():
    # Guard against version drift: the package version and pyproject must agree,
    # so the declared version can never silently lag what is shipped.
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert genus.__version__ == data["project"]["version"]
