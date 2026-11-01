"""Strict configuration with a small, explicit acquisition boundary."""

from pathlib import Path

import yaml
from pydantic import Field, model_validator
from pyproj import CRS, Transformer
from shapely import transform
from shapely.geometry import box

from iloilo3d.models import BoundingBox, GeographicPoint, Model


class Region(Model):
    name: str = "Iloilo City Proper prototype"
    origin: GeographicPoint = Field(
        default_factory=lambda: GeographicPoint(longitude=122.5685, latitude=10.6952)
    )
    size_m: float = Field(default=250, gt=0, le=2000)
    bbox: BoundingBox | None = None
    projected_crs: str = "EPSG:32651"
    elevation_datum: str = "unknown; origin Z is a simulation reference, not measured terrain"

    @model_validator(mode="after")
    def valid_projection(self) -> "Region":
        crs = CRS.from_user_input(self.projected_crs)
        if not crs.is_projected or any(a.unit_name != "metre" for a in crs.axis_info[:2]):
            raise ValueError("Processing CRS must be projected in meters")
        area = crs.area_of_use
        if area and not (
            area.west <= self.origin.longitude <= area.east
            and area.south <= self.origin.latitude <= area.north
        ):
            raise ValueError("Origin lies outside the processing CRS area of use")
        return self

    def bounds(self) -> BoundingBox:
        if self.bbox:
            return self.bbox
        forward = Transformer.from_crs(4326, self.projected_crs, always_xy=True)
        inverse = Transformer.from_crs(self.projected_crs, 4326, always_xy=True)
        x, y = forward.transform(self.origin.longitude, self.origin.latitude)
        half = self.size_m / 2
        west, south, east, north = inverse.transform_bounds(x - half, y - half, x + half, y + half)
        return BoundingBox(west=west, south=south, east=east, north=north)


class Acquisition(Model):
    endpoint: str = "https://overpass-api.de/api/interpreter"
    timeout_seconds: int = Field(default=90, ge=5, le=300)
    max_area_km2: float = Field(default=1, gt=0, le=25)
    max_download_mb: int = Field(default=32, ge=1, le=128)
    minimum_interval_seconds: float = Field(default=2, ge=1, le=60)


class ProjectConfig(Model):
    region: Region = Field(default_factory=Region)
    acquisition: Acquisition = Field(default_factory=Acquisition)
    data_dir: Path = Path("data")

    def validate_area(self) -> None:
        bounds = self.region.bounds()
        projection = Transformer.from_crs(4326, self.region.projected_crs, always_xy=True)
        polygon = transform(
            box(bounds.west, bounds.south, bounds.east, bounds.north),
            projection.transform,
            interleaved=False,
        )
        if polygon.area > self.acquisition.max_area_km2 * 1_000_000:
            raise ValueError("Region exceeds acquisition.max_area_km2; select a smaller prototype")
        area = CRS.from_user_input(self.region.projected_crs).area_of_use
        if area and not (
            area.west <= bounds.west < bounds.east <= area.east
            and area.south <= bounds.south < bounds.north <= area.north
        ):
            raise ValueError("Bounding box lies outside the processing CRS area of use")


def load_config(path: Path) -> ProjectConfig:
    config = ProjectConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    if not config.data_dir.is_absolute():
        config.data_dir = (path.resolve().parent / config.data_dir).resolve()
    config.validate_area()
    return config
