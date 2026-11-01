"""Portable GIS output; local-meter layers have an engineering CRS, never UTM labels."""

import json
from pathlib import Path

import geopandas as gpd
from pyproj import CRS
from shapely.geometry import shape

from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import GeographicDataset

LOCAL_CRS = CRS.from_wkt(
    'LOCAL_CS["Iloilo3D local east north meters",LOCAL_DATUM["Project origin",0],'
    'UNIT["metre",1],AXIS["East",EAST],AXIS["North",NORTH]]'
)


def write_geopackage(dataset: GeographicDataset, path: Path) -> None:
    """Create nine layers, retaining empty layers when source features are absent."""
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    for kind, objects, geometry_key in (
        ("buildings", dataset.buildings, "footprint"),
        ("roads", dataset.roads, "centerline"),
        ("public_spaces", dataset.public_spaces, "geometry"),
    ):
        rows = []
        geometries = []
        for obj in objects:
            record = obj.model_dump(mode="json")
            geometries.append(shape(record.pop(geometry_key)))
            rows.append(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in record.items()
                }
            )
        geo = gpd.GeoDataFrame(rows or {"id": []}, geometry=geometries, crs="EPSG:4326")
        projected = geo.to_crs(dataset.projected_crs)
        local = geo.copy()
        local.geometry = [frame.local_geometry(g) for g in geometries]
        local = local.set_crs(LOCAL_CRS, allow_override=True)
        for suffix, layer in (("wgs84", geo), ("projected", projected), ("local", local)):
            layer.to_file(
                path, layer=f"{kind}_{suffix}", driver="GPKG", engine="pyogrio", index=False
            )
