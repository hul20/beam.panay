# Jaro photographic collection

[The populated manifest](../config/photos.example.yaml) lists actual local files rather
than example paths. The collection covers Commons' Jaro Plaza category and its descendants,
including the belfry, monuments and aerial views, plus the Jaro Cathedral category.
It is a collection from these sources, not a claim to contain every photograph on the web.

The 2026-11-02 run discovered 227 candidates and collected **224 images (128.6 MB)**.
Three Manila procession images were excluded as outside the target area. All 224 manifest
entries successfully passed the project's `import-images` command and were copied into
[the normalized image job](../data/jaro/images/commons-jaro-20261102/).
Browse [the local gallery](../data/jaro/photos/commons/photo_gallery.html) for visual review.
Two files are original downloads; the remainder are Wikimedia-generated resized copies.

Each entry retains its creator, selected license, Commons description page, original image
URL and reuse conditions in `rights_statement`. CC BY, CC BY-SA, CC0 and Commons-marked
public-domain files are accepted when adequate source/author metadata is present.
Attribution and applicable share-alike obligations still apply to derivatives.

Original bulk downloads were rate-limited by Wikimedia. The collector follows the service's
recommendation to use standard 1280-pixel-wide copies, while retaining successfully obtained
originals. The manifest distinguishes these cases. Resized copies may have stripped EXIF
and are less suitable for fine architectural reconstruction than original photographs.

Source metadata and the download/exclusion report are stored beside the files in
[the photo directory](../data/jaro/photos/commons/). Exact duplicate downloaded files are
excluded. Different crops, viewpoints, historical photos, interiors and night views can
remain; they need visual selection before reconstruction. Landmark associations are inferred
from file titles and require review. Camera coordinates, headings and alignment are not guessed.

To resume the collector using its cached metadata and existing downloads:

```powershell
.\.venv\Scripts\python.exe scripts/collect_jaro_photos.py
```

The verified import command was:

```powershell
.\.venv\Scripts\iloilo3d.exe import-images --manifest config/photos.example.yaml --job data/jaro/processed/99d27ed9ec10a6183511 --output data/jaro/images/commons-jaro-20261102
```

Use a new output folder for another import; existing image jobs are immutable.

The collector checks licenses and image decoding before adding each local file. It stops a
download batch on HTTP 429; rerun later, respecting the provider's rate limit. The manifest
can be imported using the procedure in [the image intake guide](./imagery.md). No Google
Street View content was collected.
