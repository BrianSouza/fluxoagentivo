from importlib.metadata import version

import harness


def test_package_version_matches_distribution() -> None:
    assert harness.__version__ == version("harness")
