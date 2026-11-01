"""Geographic validity and source-node road connectivity diagnostics."""

import networkx as nx
from shapely.geometry import shape

from iloilo3d.geospatial.coordinates import CoordinateFrame
from iloilo3d.models import GeographicDataset, ValidationReport


def validate_dataset(dataset: GeographicDataset) -> ValidationReport:
    errors: list[str] = []
    warnings = list(dataset.warnings)
    identifiers = [obj.id for obj in [*dataset.buildings, *dataset.roads]]
    if len(identifiers) != len(set(identifiers)):
        errors.append("Duplicate persistent feature identifiers")
    frame = CoordinateFrame(dataset.origin, dataset.projected_crs)
    for obj in dataset.buildings:
        geom = frame.local_geometry(shape(obj.footprint))
        if not geom.is_valid or geom.is_empty or geom.area <= 0:
            errors.append(f"{obj.id}: invalid projected footprint")
    network = nx.Graph()
    for road in dataset.roads:
        if road.drivable_candidate:
            network.add_edge(road.start_node, road.end_node)
    components = nx.number_connected_components(network)
    if components > 1:
        warnings.append(f"{components} disconnected drivable road components in selected area")
    if not dataset.buildings:
        warnings.append("No mapped building footprints; no substitute buildings were invented")
    if not dataset.roads:
        warnings.append("No mapped road segments")
    if not network:
        warnings.append("No drivable candidate roads; area is unsuitable for a driving prototype")
    warnings.append("Vertical datum and surface elevation are unverified; no terrain generated")
    unknown_heights = sum(building.height_m is None for building in dataset.buildings)
    if unknown_heights:
        warnings.append(f"{unknown_heights} buildings have no parseable mapped height")
    return ValidationReport(
        valid=not errors,
        counts={
            "buildings": len(dataset.buildings),
            "road_segments": len(dataset.roads),
            "drivable_components": components,
            "intersection_nodes": sum(degree >= 3 for _, degree in network.degree()),
        },
        errors=errors,
        warnings=warnings,
    )
