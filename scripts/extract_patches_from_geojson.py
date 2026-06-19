#!/usr/bin/env python3
"""Extract patch images from NDPI/WSI files using rectangular GeoJSON annotations.

The output patch filename is:

    <wsi_stem>_x<x_min>_y<y_min>.png

By default, patches are written under:

    <output_dir>/<wsi_stem>/<label_folder>/<wsi_stem>_x<x_min>_y<y_min>.png

where <label_folder> is inferred from the GeoJSON annotation properties when possible.
Use --flat to write directly under <output_dir>/<wsi_stem>/.

Coordinates are assumed to be level-0 WSI pixel coordinates, which is the common
format for QuPath GeoJSON exports. OpenSlide is used for WSI reading.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from PIL import Image

VALID_IMAGE_EXTENSIONS = {".ndpi", ".svs", ".mrxs", ".tif", ".tiff"}
VALID_LABEL_FOLDERS = {"I", "II", "III", "IV", "V"}

# Common aliases seen in annotation files and metadata.
LABEL_TO_FOLDER = {
    "i": "I",
    "ii": "II",
    "iii": "III",
    "iv": "IV",
    "v": "V",
    "1": "I",
    "2": "II",
    "3": "III",
    "4": "IV",
    "5": "V",
    "c1": "I",
    "c2": "II",
    "c3": "III",
    "c4": "IV",
    "c5": "V",
    "category i": "I",
    "category ii": "II",
    "category iii": "III",
    "category iv": "IV",
    "category v": "V",
    "insufficient": "I",
    "inadequate": "I",
    "benign": "II",
    "atypical": "III",
    "suspicious": "IV",
    "suspicious for malignancy": "IV",
    "malignant": "V",
}

DEFAULT_LABEL_KEYS = (
    "label",
    "class",
    "category",
    "classification",
    "classification_name",
    "classificationName",
    "name",
    "pathClass",
    "yokohama_category",
    "yokohama_category_original",
    "diagnostic_category",
)


def load_openslide():
    """Import openslide lazily so --help works even when OpenSlide is absent."""
    try:
        import openslide  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "OpenSlide Python bindings are required. Install with `pip install openslide-python` "
            "and ensure the OpenSlide shared library is installed on your system."
        ) from exc
    return openslide


def sanitize_name(value: str) -> str:
    value = str(value).strip()
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "unknown"


def normalize_label(value: Any) -> str | None:
    """Convert a label value into folder I-V when possible."""
    if value is None:
        return None

    if isinstance(value, dict):
        # QuPath sometimes stores labels as {"name": "C2"} or similar.
        for key in ("name", "value", "label", "classification", "class"):
            if key in value:
                found = normalize_label(value[key])
                if found:
                    return found
        return None

    text = str(value).strip()
    if not text:
        return None

    cleaned = text.lower().strip()
    cleaned = cleaned.replace("category", "category ")
    cleaned = re.sub(r"\s+", " ", cleaned)

    # Direct exact matches first.
    if cleaned in LABEL_TO_FOLDER:
        return LABEL_TO_FOLDER[cleaned]

    # Common strings such as "C2 benign", "II - benign", "Category IV".
    m = re.search(r"\bC\s*([1-5])\b", cleaned, flags=re.IGNORECASE)
    if m:
        return LABEL_TO_FOLDER[m.group(1)]

    roman_pattern = r"\b(I|II|III|IV|V)\b"
    m = re.search(roman_pattern, text, flags=re.IGNORECASE)
    if m:
        return LABEL_TO_FOLDER[m.group(1).lower()]

    for key, folder in LABEL_TO_FOLDER.items():
        if key in cleaned:
            return folder

    return sanitize_name(text)


def get_nested_value(properties: dict[str, Any], key: str) -> Any:
    """Return a property value. Supports dotted paths like classification.name."""
    if "." not in key:
        return properties.get(key)
    current: Any = properties
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def infer_label(properties: dict[str, Any], explicit_key: str | None = None) -> str | None:
    if explicit_key:
        return normalize_label(get_nested_value(properties, explicit_key))

    for key in DEFAULT_LABEL_KEYS:
        value = get_nested_value(properties, key)
        label = normalize_label(value)
        if label:
            return label

    # Last resort: inspect all scalar property values.
    for value in properties.values():
        if isinstance(value, (str, int, float)):
            label = normalize_label(value)
            if label in VALID_LABEL_FOLDERS:
                return label
        elif isinstance(value, dict):
            label = normalize_label(value)
            if label:
                return label

    return None


def iter_points_from_coordinates(coords: Any) -> Iterable[tuple[float, float]]:
    """Yield 2D points from nested GeoJSON coordinate arrays."""
    if not isinstance(coords, list):
        return

    # A point coordinate: [x, y] or [x, y, z]
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        yield float(coords[0]), float(coords[1])
        return

    for item in coords:
        yield from iter_points_from_coordinates(item)


def bbox_from_geometry(geometry: dict[str, Any]) -> tuple[int, int, int, int] | None:
    """Return integer level-0 bbox (x_min, y_min, x_max, y_max)."""
    if not geometry:
        return None

    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")

    if geom_type == "GeometryCollection":
        boxes = [bbox_from_geometry(g) for g in geometry.get("geometries", [])]
        boxes = [b for b in boxes if b is not None]
        if not boxes:
            return None
        x0 = min(b[0] for b in boxes)
        y0 = min(b[1] for b in boxes)
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        return x0, y0, x1, y1

    points = list(iter_points_from_coordinates(coords))
    if not points:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    x0 = int(math.floor(min(xs)))
    y0 = int(math.floor(min(ys)))
    x1 = int(math.ceil(max(xs)))
    y1 = int(math.ceil(max(ys)))

    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def read_geojson_features(geojson_path: Path) -> list[dict[str, Any]]:
    with geojson_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") == "FeatureCollection":
        return data.get("features", []) or []
    if data.get("type") == "Feature":
        return [data]
    if "features" in data:
        return data.get("features", []) or []

    raise ValueError(f"Unsupported GeoJSON structure in {geojson_path}")


def clamp_bbox(
    bbox: tuple[int, int, int, int],
    width: int,
    height: int,
    padding: int = 0,
) -> tuple[int, int, int, int] | None:
    x0, y0, x1, y1 = bbox
    x0 -= padding
    y0 -= padding
    x1 += padding
    y1 += padding

    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(width, x1)
    y1 = min(height, y1)

    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def extract_patch(slide: Any, bbox: tuple[int, int, int, int], read_level: int) -> Image.Image:
    """Extract an RGB patch from a slide using level-0 bbox coordinates."""
    x0, y0, x1, y1 = bbox
    downsample = float(slide.level_downsamples[read_level])
    level_w = max(1, int(math.ceil((x1 - x0) / downsample)))
    level_h = max(1, int(math.ceil((y1 - y0) / downsample)))
    patch = slide.read_region((x0, y0), read_level, (level_w, level_h)).convert("RGB")
    return patch


def find_matching_wsi(wsi_dir: Path, stem: str) -> Path | None:
    for ext in VALID_IMAGE_EXTENSIONS:
        candidate = wsi_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
        candidate_upper = wsi_dir / f"{stem}{ext.upper()}"
        if candidate_upper.exists():
            return candidate_upper
    matches = [p for p in wsi_dir.iterdir() if p.is_file() and p.stem == stem and p.suffix.lower() in VALID_IMAGE_EXTENSIONS]
    if matches:
        return matches[0]
    return None


def unique_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 100000):
        candidate = parent / f"{stem}_dup{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create unique output path for {path}")


def extract_from_pair(
    wsi_path: Path,
    geojson_path: Path,
    output_dir: Path,
    read_level: int = 0,
    label_key: str | None = None,
    flat: bool = False,
    padding: int = 0,
    overwrite: bool = False,
    skip_unlabeled: bool = False,
    unknown_label: str = "unknown",
) -> tuple[int, int]:
    openslide = load_openslide()
    features = read_geojson_features(geojson_path)
    wsi_stem = wsi_path.stem

    saved = 0
    skipped = 0

    with openslide.OpenSlide(str(wsi_path)) as slide:
        width, height = slide.dimensions
        if read_level < 0 or read_level >= len(slide.level_dimensions):
            raise ValueError(f"Invalid read level {read_level}; slide has {len(slide.level_dimensions)} levels")

        for idx, feature in enumerate(features):
            geometry = feature.get("geometry") or {}
            properties = feature.get("properties") or {}

            bbox = bbox_from_geometry(geometry)
            if bbox is None:
                skipped += 1
                continue

            bbox = clamp_bbox(bbox, width=width, height=height, padding=padding)
            if bbox is None:
                skipped += 1
                continue

            label = infer_label(properties, explicit_key=label_key)
            if label is None:
                if skip_unlabeled:
                    skipped += 1
                    continue
                label = unknown_label

            x0, y0, _, _ = bbox
            filename = f"{wsi_stem}_x{x0}_y{y0}.png"

            if flat:
                out_subdir = output_dir / wsi_stem
            else:
                out_subdir = output_dir / wsi_stem / sanitize_name(label)
            out_subdir.mkdir(parents=True, exist_ok=True)

            out_path = out_subdir / filename
            if out_path.exists() and not overwrite:
                out_path = unique_output_path(out_path)

            patch = extract_patch(slide, bbox, read_level=read_level)
            patch.save(out_path)
            saved += 1

    return saved, skipped


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract patch PNGs from WSI files using rectangular GeoJSON annotations.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    single = parser.add_argument_group("single-slide mode")
    single.add_argument("--wsi", type=Path, help="Path to one WSI file, for example .ndpi")
    single.add_argument("--geojson", type=Path, help="Path to the corresponding GeoJSON annotation file")

    batch = parser.add_argument_group("batch mode")
    batch.add_argument("--wsi-dir", type=Path, help="Directory containing WSI files")
    batch.add_argument("--geojson-dir", type=Path, help="Directory containing GeoJSON files matched by stem")

    parser.add_argument("--output-dir", type=Path, required=True, help="Directory where extracted patches will be written")
    parser.add_argument("--read-level", type=int, default=0, help="OpenSlide level used for extraction. Coordinates are still assumed level-0.")
    parser.add_argument("--label-key", type=str, default=None, help="Optional explicit GeoJSON property key for labels, e.g. classification.name")
    parser.add_argument("--flat", action="store_true", help="Do not create class subdirectories; write under output_dir/wsi_stem")
    parser.add_argument("--padding", type=int, default=0, help="Optional padding in level-0 pixels added around each box")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing patches with the same filename")
    parser.add_argument("--skip-unlabeled", action="store_true", help="Skip annotations where no label can be inferred")
    parser.add_argument("--unknown-label", type=str, default="unknown", help="Folder name used for unlabeled annotations when not skipping")

    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.wsi and args.geojson:
        if not args.wsi.exists():
            raise SystemExit(f"WSI not found: {args.wsi}")
        if not args.geojson.exists():
            raise SystemExit(f"GeoJSON not found: {args.geojson}")
        saved, skipped = extract_from_pair(
            wsi_path=args.wsi,
            geojson_path=args.geojson,
            output_dir=args.output_dir,
            read_level=args.read_level,
            label_key=args.label_key,
            flat=args.flat,
            padding=args.padding,
            overwrite=args.overwrite,
            skip_unlabeled=args.skip_unlabeled,
            unknown_label=args.unknown_label,
        )
        print(f"{args.wsi.name}: saved={saved}, skipped={skipped}")
        return 0

    if args.wsi_dir and args.geojson_dir:
        if not args.wsi_dir.exists():
            raise SystemExit(f"WSI directory not found: {args.wsi_dir}")
        if not args.geojson_dir.exists():
            raise SystemExit(f"GeoJSON directory not found: {args.geojson_dir}")

        total_saved = 0
        total_skipped = 0
        processed = 0
        missing_wsi = 0

        for geojson_path in sorted(args.geojson_dir.glob("*.geojson")):
            wsi_path = find_matching_wsi(args.wsi_dir, geojson_path.stem)
            if wsi_path is None:
                print(f"[WARN] No matching WSI found for {geojson_path.name}", file=sys.stderr)
                missing_wsi += 1
                continue

            saved, skipped = extract_from_pair(
                wsi_path=wsi_path,
                geojson_path=geojson_path,
                output_dir=args.output_dir,
                read_level=args.read_level,
                label_key=args.label_key,
                flat=args.flat,
                padding=args.padding,
                overwrite=args.overwrite,
                skip_unlabeled=args.skip_unlabeled,
                unknown_label=args.unknown_label,
            )
            print(f"{wsi_path.name}: saved={saved}, skipped={skipped}")
            total_saved += saved
            total_skipped += skipped
            processed += 1

        print(
            f"Done. processed_wsis={processed}, missing_wsi={missing_wsi}, "
            f"saved_patches={total_saved}, skipped_annotations={total_skipped}"
        )
        return 0 if missing_wsi == 0 else 1

    raise SystemExit("Use either --wsi + --geojson for one slide, or --wsi-dir + --geojson-dir for batch mode.")


if __name__ == "__main__":
    raise SystemExit(main())
