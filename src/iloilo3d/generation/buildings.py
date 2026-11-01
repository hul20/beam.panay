"""Height interpretation keeps mapped open roofs from becoming solid walls."""

from dataclasses import dataclass

from iloilo3d.errors import PipelineError
from iloilo3d.models import Building
from iloilo3d.providers.osm import positive_number


@dataclass(frozen=True)
class BuildingProfile:
    bottom: float
    top: float
    open_roof: bool
    bottom_status: str

    @property
    def obstructs_ground(self) -> bool:
        """Conservative prototype vehicle clearance; not a surveyed guarantee."""
        return self.bottom < 3.0


def building_profile(building: Building, fallback_height_m: float = 6) -> BuildingProfile:
    roof = building.tags.get("building") == "roof"
    top = building.height_m or (building.floors * 3 if building.floors else fallback_height_m)
    mapped_bottom = positive_number(building.tags.get("min_height"), length=True)
    bottom = mapped_bottom if mapped_bottom is not None else max(0, top - 0.25) if roof else 0
    if bottom >= top:
        raise PipelineError(f"{building.id}: min_height must be below total height")
    return BuildingProfile(
        bottom, top, roof, "mapped" if mapped_bottom is not None else "estimated"
    )
