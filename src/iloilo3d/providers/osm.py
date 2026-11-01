"""One bounded Overpass XML request, cached by query; offline OSM normalization.

OSMnx assembles footprint multipolygons. Roads split at shared OSM nodes, not
geometric crossings, so a bridge crossing does not become a false intersection.
"""

import hashlib
import logging
import math
import re
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree.ElementTree import Element

import httpx
import osmnx as ox
from defusedxml import ElementTree as SafeET
from shapely.geometry import LineString, box, mapping

from iloilo3d.config import ProjectConfig
from iloilo3d.errors import PipelineError
from iloilo3d.models import (
    Building,
    GeographicDataset,
    PropertyEvidence,
    PublicSpace,
    RoadSegment,
    SourceRecord,
)
from iloilo3d.storage.files import atomic_bytes, sha256_file, write_json

LOG = logging.getLogger(__name__)
DRIVE_CLASSES = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "road",
    "track",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}


def tags_of(element: Element) -> dict[str, str]:
    return {tag.attrib["k"]: tag.attrib["v"] for tag in element.findall("tag")}


def positive_number(value: str | None, *, length: bool = False) -> float | None:
    """Parse unambiguous numeric tags, meters, or feet; preserve other tags as unknown."""
    if value is None:
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(m|ft|')?\s*", value)
    if not match or (match[2] and not length):
        return None
    result = float(match[1]) * (0.3048 if match[2] in {"ft", "'"} else 1)
    return result if math.isfinite(result) and result > 0 else None


def overpass_query(config: ProjectConfig) -> str:
    b = config.region.bounds()
    bounds = f"{b.south:.9f},{b.west:.9f},{b.north:.9f},{b.east:.9f}"
    return (
        f"[out:xml][timeout:{config.acquisition.timeout_seconds}];"
        f'(way["building"]({bounds});relation["building"]["type"="multipolygon"]({bounds});'
        f'way["highway"]({bounds});'
        f'way["leisure"~"^(park|garden|pitch)$"]({bounds});'
        f'relation["leisure"~"^(park|garden|pitch)$"]["type"="multipolygon"]({bounds});'
        f'way["landuse"="grass"]({bounds}););(._;>;);out meta;'
    )


def read_osm(path: Path, max_bytes: int = 128 * 1024 * 1024) -> Element:
    if path.stat().st_size > max_bytes:
        raise PipelineError("OSM input exceeds the configured size limit")
    root = SafeET.parse(path).getroot()
    if root.tag != "osm":
        raise PipelineError("Expected OSM XML, not HTML, JSON, or an OSM change file")
    if root.find("remark") is not None:
        raise PipelineError("Overpass returned an incomplete result with a remark; retry later")
    for node in root.findall("node"):
        lon, lat = float(node.attrib["lon"]), float(node.attrib["lat"])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise PipelineError(f"Invalid coordinate on OSM node {node.attrib.get('id')}")
    return root


def acquire(
    config: ProjectConfig, *, refresh: bool = False, transport: httpx.BaseTransport | None = None
) -> tuple[Path, SourceRecord]:
    """Fetch or reuse a validated cache; no automatic retries for server errors."""
    config.validate_area()
    endpoint = config.acquisition.endpoint
    url = urlsplit(endpoint)
    if url.scheme != "https" or url.username or url.password or url.query or url.fragment:
        raise PipelineError(
            "Overpass endpoint must be HTTPS without credentials, query, or fragment"
        )
    query = overpass_query(config)
    key = hashlib.sha256((endpoint + "\n" + query).encode()).hexdigest()
    raw_dir = config.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path, metadata = raw_dir / f"{key}.osm", raw_dir / f"{key}.source.json"
    if not refresh and path.exists() and metadata.exists():
        source = SourceRecord.model_validate_json(metadata.read_text(encoding="utf-8"))
        if source.sha256 != sha256_file(path):
            raise PipelineError("Cached OSM checksum mismatch; use --refresh to acquire again")
        LOG.info("Using cached OSM source %s", key[:12])
        return path, source
    # Persisted between CLI calls. Concurrent writers are refused rather than racing.
    lock_path = raw_dir / ".overpass.lock"
    try:
        lock = lock_path.open("x")
    except FileExistsError as exc:
        raise PipelineError(f"Acquisition already locked: {lock_path}") from exc
    try:
        with lock:
            lock.write(datetime.now(UTC).isoformat())
        stamp = raw_dir / ".last-request"
        if stamp.exists():
            elapsed = time.time() - float(stamp.read_text())
            time.sleep(
                max(
                    0,
                    min(
                        config.acquisition.minimum_interval_seconds,
                        config.acquisition.minimum_interval_seconds - elapsed,
                    ),
                )
            )
        atomic_bytes(stamp, str(time.time()).encode())
        LOG.info("Requesting OSM roads and buildings for %s", config.region.name)
        chunks: list[bytes] = []
        size = 0
        with httpx.Client(
            transport=transport, timeout=config.acquisition.timeout_seconds + 15
        ) as client:
            with client.stream(
                "POST",
                endpoint,
                data={"data": query},
                headers={"User-Agent": "Iloilo3D/0.1 geographic prototype"},
            ) as response:
                if response.status_code != 200:
                    raise PipelineError(
                        f"Overpass HTTP {response.status_code}; no automatic retry. "
                        "For 429/504, wait or use a saved OSM XML file."
                    )
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > config.acquisition.max_download_mb * 1024 * 1024:
                        raise PipelineError("Overpass response exceeds download limit")
                    chunks.append(chunk)
        content = b"".join(chunks)
        # Validate before publishing so an error cannot replace a good cache.
        root = SafeET.fromstring(content)
        if root.tag != "osm" or root.find("remark") is not None:
            raise PipelineError("Overpass did not return complete OSM XML")
        source = SourceRecord(
            acquired_at=datetime.now(UTC),
            sha256=hashlib.sha256(content).hexdigest(),
            source_file=path.name,
            endpoint=endpoint,
            query=query,
        )
        atomic_bytes(path, content)
        write_json(metadata, source.model_dump(mode="json"))
        return path, source
    finally:
        lock_path.unlink(missing_ok=True)


def import_source(path: Path, config: ProjectConfig, *, synthetic: bool = False) -> SourceRecord:
    """Copy local OSM input into the raw store without changing its bytes."""
    read_osm(path, config.acquisition.max_download_mb * 1024 * 1024)
    checksum = sha256_file(path)
    destination = config.data_dir / "raw" / f"{checksum}.osm"
    if path.resolve() != destination.resolve():
        atomic_bytes(destination, path.read_bytes())
    source = SourceRecord(
        acquired_at=datetime.now(UTC),
        sha256=checksum,
        source_file=destination.name,
        synthetic=synthetic,
    )
    if synthetic:
        source.dataset = "Synthetic test fixture (not real geography)"
        source.license_id = "test-fixture"
        source.attribution = "Iloilo3D synthetic test data"
        source.license_url = ""
    write_json(destination.with_suffix(".source.json"), source.model_dump(mode="json"))
    return source


def extract(path: Path, config: ProjectConfig, source: SourceRecord) -> GeographicDataset:
    """Normalize complete footprints and connected road segments intersecting the AOI."""
    root = read_osm(path)
    bounds = config.region.bounds()
    boundary = box(bounds.west, bounds.south, bounds.east, bounds.north)
    warnings: list[str] = []
    elements = {(el.tag, int(el.attrib["id"])): el for el in root if "id" in el.attrib}
    buildings: list[Building] = []
    try:
        features = ox.features.features_from_xml(path, tags={"building": True})
    except ox._errors.InsufficientResponseError:
        features = None
    # Relation members with the same building tag must not become duplicate masses.
    relation_members: set[int] = set()
    if features is not None:
        for (kind, osm_id), row in features.iterrows():
            if kind == "relation" and row.geometry.geom_type in {"Polygon", "MultiPolygon"}:
                relation = elements[(kind, int(osm_id))]
                relation_members.update(
                    int(m.attrib["ref"])
                    for m in relation.findall("member")
                    if m.attrib.get("type") == "way" and m.attrib.get("role") in {"outer", ""}
                )
        for (kind, osm_id), row in features.sort_index().iterrows():
            if kind == "way" and int(osm_id) in relation_members:
                continue
            element = elements[(kind, int(osm_id))]
            tags = tags_of(element)
            if tags.get("building") == "no":
                continue
            geom = row.geometry
            identifier = f"osm/{kind}/{osm_id}"
            if geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.is_valid:
                warnings.append(f"{identifier}: skipped nonpolygon or invalid building geometry")
                continue
            if geom.is_empty or not geom.intersects(boundary):
                continue
            height = positive_number(tags.get("height"), length=True)
            floors = positive_number(tags.get("building:levels"))
            buildings.append(
                Building(
                    id=identifier,
                    footprint=mapping(geom),
                    tags=tags,
                    height_m=height,
                    floors=floors,
                    source_version=element.get("version"),
                    source_timestamp=element.get("timestamp"),
                    evidence={
                        "footprint": PropertyEvidence(
                            status="mapped",
                            source=identifier,
                            note="OSMnx may repair polygon topology; original XML is retained",
                        ),
                        "height": PropertyEvidence(
                            status="mapped" if height else "unknown",
                            source=identifier if height else None,
                        ),
                        "facade": PropertyEvidence(),
                        "geographic_alignment": PropertyEvidence(
                            status="mapped", source=identifier, note="Survey accuracy is unknown"
                        ),
                    },
                )
            )
    nodes = {
        int(n.attrib["id"]): (float(n.attrib["lon"]), float(n.attrib["lat"]))
        for n in root.findall("node")
    }
    ways: list[tuple[Element, list[int], dict[str, str]]] = []
    usage: Counter[int] = Counter()
    for way in root.findall("way"):
        tags = tags_of(way)
        if "highway" not in tags or tags.get("area") == "yes":
            continue
        refs = [int(nd.attrib["ref"]) for nd in way.findall("nd")]
        if len(refs) < 2 or any(ref not in nodes for ref in refs):
            warnings.append(f"osm/way/{way.attrib['id']}: skipped road with missing nodes")
            continue
        usage.update(set(refs))
        ways.append((way, refs, tags))
    roads: list[RoadSegment] = []
    for way, refs, tags in ways:
        cuts = [0] + [i for i in range(1, len(refs) - 1) if usage[refs[i]] > 1] + [len(refs) - 1]
        for start, end in zip(cuts, cuts[1:], strict=False):
            segment_nodes = refs[start : end + 1]
            geom = LineString([nodes[n] for n in segment_nodes])
            if geom.length == 0 or not geom.intersects(boundary):
                continue
            oneway = tags.get("oneway")
            direction = {
                "yes": "forward",
                "1": "forward",
                "true": "forward",
                "-1": "reverse",
                "no": "both",
                "0": "both",
                "false": "both",
            }.get(oneway, "unknown" if oneway else "both")
            if oneway is None and (
                tags.get("junction") == "roundabout" or tags["highway"] == "motorway"
            ):
                direction = "forward"
            lane_value = positive_number(tags.get("lanes"))
            motor_access = tags.get("motor_vehicle", tags.get("vehicle", tags.get("access")))
            roads.append(
                RoadSegment(
                    id=f"osm/way/{way.attrib['id']}/{start}-{end}",
                    osm_way_id=int(way.attrib["id"]),
                    start_node=segment_nodes[0],
                    end_node=segment_nodes[-1],
                    node_ids=segment_nodes,
                    centerline=mapping(geom),
                    tags=tags,
                    direction=direction,
                    drivable_candidate=tags["highway"] in DRIVE_CLASSES
                    and motor_access not in {"no", "private"},
                    width_m=positive_number(tags.get("width"), length=True),
                    lanes=int(lane_value) if lane_value and lane_value.is_integer() else None,
                    source_version=way.get("version"),
                    source_timestamp=way.get("timestamp"),
                )
            )
    public_spaces: list[PublicSpace] = []
    try:
        spaces = ox.features.features_from_xml(
            path, tags={"leisure": ["park", "garden", "pitch"], "landuse": "grass"}
        )
    except ox._errors.InsufficientResponseError:
        spaces = None
    if spaces is not None:
        for (kind, osm_id), row in spaces.sort_index().iterrows():
            geometry = row.geometry
            if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty:
                continue
            if not geometry.is_valid or not geometry.intersects(boundary):
                continue
            element = elements[(kind, int(osm_id))]
            public_spaces.append(
                PublicSpace(
                    id=f"osm/{kind}/{osm_id}",
                    geometry=mapping(geometry),
                    tags=tags_of(element),
                    source_version=element.get("version"),
                    source_timestamp=element.get("timestamp"),
                )
            )
    LOG.info(
        "Extracted %d footprints, %d road/path segments, %d public spaces",
        len(buildings),
        len(roads),
        len(public_spaces),
    )
    return GeographicDataset(
        source=source,
        bounds=bounds,
        origin=config.region.origin,
        projected_crs=config.region.projected_crs,
        elevation_datum=config.region.elevation_datum,
        buildings=buildings,
        roads=sorted(roads, key=lambda r: r.id),
        region_name=config.region.name,
        public_spaces=public_spaces,
        warnings=warnings,
    )
