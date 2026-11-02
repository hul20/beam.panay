"""Reviewed local corrections; raw OSM records remain immutable."""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from iloilo3d.errors import PipelineError


class Correction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=5)
    evidence: Literal["measured", "visual_estimate"]


class RoadCorrection(Correction):
    width_m: float = Field(gt=1, le=30)


class BuildingCorrection(Correction):
    height_m: float | None = Field(default=None, gt=1, le=100)
    footprint_scale: float | None = Field(default=None, ge=0.5, le=1.5)


class GeometryOverrides(BaseModel):
    model_config = ConfigDict(extra="forbid")

    roads: dict[str, RoadCorrection] = Field(default_factory=dict)
    buildings: dict[str, BuildingCorrection] = Field(default_factory=dict)


def load_overrides(path: Path | None) -> GeometryOverrides:
    if path is None:
        return GeometryOverrides()
    if not path.is_file():
        raise PipelineError(f"Overrides file is missing: {path}")
    data = yaml.safe_load(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise PipelineError("Overrides must be a YAML mapping")
    return GeometryOverrides.model_validate(data)
