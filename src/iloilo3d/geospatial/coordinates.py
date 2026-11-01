"""WGS84 -> projected easting/northing -> local X east, Y north, Z up.

Z is translated only. No vertical datum conversion is implied.
"""

from dataclasses import dataclass, field

from pyproj import Transformer
from shapely import transform
from shapely.affinity import translate
from shapely.geometry.base import BaseGeometry

from iloilo3d.models import GeographicPoint


@dataclass
class CoordinateFrame:
    origin: GeographicPoint
    projected_crs: str = "EPSG:32651"
    forward: Transformer = field(init=False, repr=False)
    inverse: Transformer = field(init=False, repr=False)
    origin_xy: tuple[float, float] = field(init=False)

    def __post_init__(self) -> None:
        self.forward = Transformer.from_crs(4326, self.projected_crs, always_xy=True)
        self.inverse = Transformer.from_crs(self.projected_crs, 4326, always_xy=True)
        self.origin_xy = self.forward.transform(self.origin.longitude, self.origin.latitude)

    def geographic_to_local(
        self, longitude: float, latitude: float, elevation_m: float = 0
    ) -> tuple[float, float, float]:
        x, y = self.forward.transform(longitude, latitude, errcheck=True)
        return x - self.origin_xy[0], y - self.origin_xy[1], elevation_m - self.origin.elevation_m

    def local_to_geographic(self, x: float, y: float, z: float = 0) -> tuple[float, float, float]:
        lon, lat = self.inverse.transform(
            x + self.origin_xy[0], y + self.origin_xy[1], errcheck=True
        )
        return lon, lat, z + self.origin.elevation_m

    def project_geometry(self, geometry: BaseGeometry) -> BaseGeometry:
        return transform(geometry, self.forward.transform, interleaved=False, include_z=None)

    def local_geometry(self, geometry: BaseGeometry) -> BaseGeometry:
        return translate(
            self.project_geometry(geometry),
            xoff=-self.origin_xy[0],
            yoff=-self.origin_xy[1],
            zoff=-self.origin.elevation_m,
        )
