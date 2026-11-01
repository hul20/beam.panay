"""Watertight polygon extrusion including concavities and courtyard holes."""

import math
from dataclasses import dataclass

from shapely import constrained_delaunay_triangles, remove_repeated_points
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from iloilo3d.errors import PipelineError


@dataclass
class Mesh:
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]

    def validate(self) -> None:
        if not self.vertices or not self.triangles:
            raise PipelineError("Empty mesh")
        for vertex in self.vertices:
            if not all(math.isfinite(value) for value in vertex):
                raise PipelineError("Nonfinite mesh vertex")
        edges: dict[tuple[int, int], int] = {}
        for face in self.triangles:
            if len(set(face)) != 3 or any(
                index < 0 or index >= len(self.vertices) for index in face
            ):
                raise PipelineError("Invalid triangle indices")
            a, b, c = (self.vertices[index] for index in face)
            ab, ac = [b[i] - a[i] for i in range(3)], [c[i] - a[i] for i in range(3)]
            normal = (
                ab[1] * ac[2] - ab[2] * ac[1],
                ab[2] * ac[0] - ab[0] * ac[2],
                ab[0] * ac[1] - ab[1] * ac[0],
            )
            if sum(value * value for value in normal) <= 1e-20:
                raise PipelineError(f"Degenerate triangle at {a}, {b}, {c}")
            for edge in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
                edges[edge] = edges.get(edge, 0) + 1
        invalid_edges = [
            (self.vertices[a], self.vertices[b])
            for (a, b), count in edges.items()
            if count != 1 or edges.get((b, a)) != 1
        ]
        if invalid_edges:
            raise PipelineError(
                f"Mesh is not a closed, consistently oriented manifold: {invalid_edges[:3]}"
            )


def extrude(polygon: Polygon, bottom: float, top: float) -> Mesh:
    if not polygon.is_valid or polygon.is_empty or not top > bottom:
        raise PipelineError("Extrusion requires a valid polygon and positive height")
    polygon = orient(remove_repeated_points(polygon), sign=1)
    vertices: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    lookup: dict[tuple[float, float, float], int] = {}

    def vertex(x: float, y: float, z: float) -> int:
        key = (float(x), float(y), float(z))
        if key not in lookup:
            lookup[key] = len(vertices)
            vertices.append(key)
        return lookup[key]

    for triangle in constrained_delaunay_triangles(polygon).geoms:
        coordinates = list(orient(triangle, sign=1).exterior.coords)[:3]
        roof = tuple(vertex(x, y, top) for x, y in coordinates)
        base = tuple(vertex(x, y, bottom) for x, y in reversed(coordinates))
        triangles.extend([roof, base])
    for ring in [polygon.exterior, *polygon.interiors]:
        coordinates = list(ring.coords)
        for (x1, y1), (x2, y2) in zip(coordinates, coordinates[1:], strict=False):
            a, b = vertex(x1, y1, bottom), vertex(x2, y2, bottom)
            c, d = vertex(x2, y2, top), vertex(x1, y1, top)
            triangles.extend([(a, b, c), (a, c, d)])
    mesh = Mesh(vertices, triangles)
    mesh.validate()
    return mesh


def extrude_test_surface(polygon: Polygon) -> list[tuple[Mesh, float]]:
    """Open point-touching pinches only when needed for a manifold test collider.

    The returned inset is recorded in export provenance. Never apply this fallback
    to original building footprints. A 2 mm inset can create tiny surface seams.
    """
    try:
        return [(extrude(polygon, -0.5, 0), 0.0)]
    except PipelineError:
        repaired = polygon.buffer(-0.002, join_style="mitre")
        if repaired.is_empty:
            raise PipelineError("Test surface collapsed during 2 mm pinch repair") from None
        pieces = list(repaired.geoms) if repaired.geom_type == "MultiPolygon" else [repaired]
        return [(extrude(piece, -0.5, 0), 0.002) for piece in pieces]
