"""Validated stage contracts. Coordinates are always longitude, latitude."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from shapely.geometry import shape


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GeographicPoint(Model):
    longitude: float = Field(ge=-180, le=180)
    latitude: float = Field(ge=-90, le=90)
    elevation_m: float = 0


class BoundingBox(Model):
    west: float = Field(ge=-180, le=180)
    south: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)

    @model_validator(mode="after")
    def ordered(self) -> "BoundingBox":
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("Bounds require west < east and south < north; no dateline crossing")
        return self


class SourceRecord(Model):
    dataset: str = "OpenStreetMap"
    license_id: str = "ODbL-1.0"
    attribution: str = "© OpenStreetMap contributors"
    license_url: str = "https://www.openstreetmap.org/copyright"
    acquired_at: datetime
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_file: str
    endpoint: str | None = None
    query: str | None = None
    synthetic: bool = False


class PropertyEvidence(Model):
    status: Literal["mapped", "measured", "estimated", "unknown"] = "unknown"
    source: str | None = None
    accuracy_m: float | None = Field(default=None, ge=0)
    note: str | None = None


class Building(Model):
    id: str
    footprint: dict
    tags: dict[str, str]
    height_m: float | None = Field(default=None, gt=0)
    floors: float | None = Field(default=None, gt=0)
    source_version: str | None = None
    source_timestamp: str | None = None
    evidence: dict[str, PropertyEvidence] = Field(default_factory=dict)
    reconstruction_method: Literal["unprocessed", "A", "B", "C"] = "unprocessed"
    image_references: list[str] = Field(default_factory=list)
    mesh_references: list[str] = Field(default_factory=list)
    manual_overrides: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_footprint(self) -> "Building":
        geometry = shape(self.footprint)
        if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Building footprint must be polygonal")
        if geometry.is_empty or not geometry.is_valid or geometry.area <= 0:
            raise ValueError("Building footprint must be nonempty and valid")
        return self


class RoadSegment(Model):
    id: str
    osm_way_id: int
    start_node: int
    end_node: int
    node_ids: list[int]
    centerline: dict
    tags: dict[str, str]
    direction: Literal["forward", "reverse", "both", "unknown"]
    drivable_candidate: bool
    width_m: float | None = Field(default=None, gt=0)
    lanes: int | None = Field(default=None, gt=0)
    source_version: str | None = None
    source_timestamp: str | None = None

    @model_validator(mode="after")
    def valid_centerline(self) -> "RoadSegment":
        geometry = shape(self.centerline)
        if geometry.geom_type != "LineString" or geometry.is_empty or geometry.length == 0:
            raise ValueError("Road centerline must be a nonzero LineString")
        if len(self.node_ids) < 2:
            raise ValueError("Road segment needs at least two OSM nodes")
        return self


class PublicSpace(Model):
    """Mapped polygon boundary, without implying surveyed material or elevation."""

    id: str
    geometry: dict
    tags: dict[str, str]
    source_version: str | None = None
    source_timestamp: str | None = None

    @model_validator(mode="after")
    def valid_geometry(self) -> "PublicSpace":
        geometry = shape(self.geometry)
        if (
            geometry.geom_type not in {"Polygon", "MultiPolygon"}
            or geometry.is_empty
            or not geometry.is_valid
        ):
            raise ValueError("Public space must have a valid polygon boundary")
        return self


class GeographicDataset(Model):
    schema_version: Literal[1] = 1
    source: SourceRecord
    bounds: BoundingBox
    origin: GeographicPoint
    projected_crs: str
    elevation_datum: str
    buildings: list[Building]
    roads: list[RoadSegment]
    region_name: str = "Iloilo geographic prototype"
    public_spaces: list[PublicSpace] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ValidationReport(Model):
    valid: bool
    counts: dict[str, int]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    in_game_validation: Literal["pending"] = "pending"
