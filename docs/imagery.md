# Phase 4: photo intake and Street View reference

The local image importer accepts JPEG, PNG, and WebP files with explicit reconstruction
permission. It verifies each file, checks its SHA-256 hash after copying, records ownership,
license, capture data, EXIF GPS/heading where available, and optional persistent building
IDs. Original pixels remain unchanged. Missing camera pose or location stays unknown; an
associated building ID alone does not certify alignment. The importer does not run
photogrammetry, segmentation, depth estimation, or texture generation yet.

The [photo manifest](../config/photos.example.yaml) now contains downloaded Commons files;
see [collection details](./photo_collection.md). Copy it to a separate manifest for your own
photos rather than replacing those provenance records. Paths are
relative to the manifest. Every image needs a creator, license ID, rights statement, and
`allows_reconstruction: true`. Accepted sources are `user_captured` and
`licensed_third_party`; a third-party entry still requires actual authorization for this
use. Google Street View imagery is not accepted by this import pipeline.

```powershell
.\.venv\Scripts\python.exe -m iloilo3d import-images `
  --manifest config/my_photos.yaml `
  --job data/jaro/processed/99d27ed9ec10a6183511 `
  --output data/jaro/images/first_batch
```

The importer writes `images.json` and an `originals/` directory in a new output folder.
The manifest hash, geographic job, and per-image checksums provide provenance. Files with
unresolved rights, corrupt pixels, duplicate content, or unknown building IDs fail before
publication. Keep originals private; permissions to reconstruct do not automatically grant
redistribution rights.

For reference only, set `GOOGLE_MAPS_API_KEY` in the environment and run:

```powershell
.\.venv\Scripts\python.exe -m iloilo3d streetview-reference `
  --latitude 10.7243667 --longitude 122.5573278
```

This performs one official metadata request. It reports availability, location, date if
provided, attribution, and an official Google Maps Street View viewing link. It does not
save a panorama ID, fetch imagery, or authorize reconstruction. No Google response enters
the independent photo or geometry datasets. Metadata availability has not been tested
against the live API because no project key was supplied.

Official references: [Street View metadata](https://developers.google.com/maps/documentation/streetview/metadata),
[Google Maps viewing URLs](https://developers.google.com/maps/documentation/urls/get-started).
