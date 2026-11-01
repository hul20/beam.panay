# Sources, provenance, and licensing

## OpenStreetMap

The first provider uses the documented Overpass API to request building ways,
building multipolygon relations, road ways, and their member nodes. Each request is
bounded by configured area, timeout, response size, and a persisted minimum request
interval. A lock prevents concurrent requests in the same data directory. Cache use
avoids duplicate requests; transient failures are surfaced for a later explicit retry.

Attribution: **© OpenStreetMap contributors**. Data is available under ODbL 1.0:
<https://www.openstreetmap.org/copyright>. Generated data keeps this record; repository
code licensing does not change the source-data terms. Review derivative-database and
produced-work obligations before redistributing a map or processed database.

OSM is not a survey guarantee. Footprints may be absent, outdated, or incomplete.
Missing heights stay null at ingestion. Parsed `height` values are mapped properties,
not independently measured values. Ambiguous units or values remain in raw tags.
Building relations retain courtyards and suppress duplicate outer-member building ways.
OSMnx can repair geometry during assembly; raw XML remains the audit source. Conflicting
independent footprint datasets are not yet reconciled.

The synthetic fixture under tests is explicitly labeled and is not real geography.
Use `--synthetic` whenever processing it through the CLI.

## BeamNG content

The exporter reads the installed game's Starter Level template for scene hierarchy,
spawn fields, environment, and metadata. The template's hash and selected members are
recorded. Game-derived files remain subject to BeamNG's terms. They are excluded from
Git, and the exporter does not publish or install a mod automatically.

## Imagery: not implemented in this milestone

No imagery provider or computer-vision stage is currently enabled. A future normalized
camera/image contract must include source identity, documented rights, permitted uses,
geographic scope, retention/redistribution restrictions, and per-image provenance.

Ordinary Google Street View access is reference/display only. No screenshot capture,
tile extraction, panorama download, geometry inference, segmentation, texture generation,
or photogrammetry from ordinary Google API imagery is part of this system. The reserved
environment variable in `.env.example` does not confer reconstruction rights.

A future rights-enabled Google-origin provider must default to disabled and require
documented permission for each operation and geographic scope. User-owned photographs,
owned panoramas, Mapillary, and KartaView need source-specific permissions checks before
reconstruction ingestion. Open Buildings coverage and licensing have not yet been evaluated.

## Technical references checked

- [OSMnx 2.1.1 API: features_from_xml](https://osmnx.readthedocs.io/en/stable/user-reference.html#osmnx.features.features_from_xml)
- [Overpass QL](https://wiki.openstreetmap.org/wiki/Overpass_API/Overpass_QL)
- [BeamNG Level Creation](https://documentation.beamng.com/modding/levels/level_creation/)
- [BeamNG overview and Starter Level](https://documentation.beamng.com/modding/levels/level_creation/section1/)
- [BeamNG mesh authoring and export](https://documentation.beamng.com/modding/levels/level_creation/section11/)

OSMnx and BeamNG pages were inspected during implementation; the Overpass link is the
query-language reference. Installed template contents were also inspected directly.

