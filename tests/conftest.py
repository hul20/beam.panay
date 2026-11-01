"""Small, explicitly synthetic geographic fixtures; tests never need an API."""

from pathlib import Path

import pytest

from iloilo3d.config import ProjectConfig


@pytest.fixture
def config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(data_dir=tmp_path / "data")


@pytest.fixture
def osm_file() -> Path:
    return Path(__file__).parent / "fixtures" / "synthetic.osm"
