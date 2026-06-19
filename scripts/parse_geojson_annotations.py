#!/usr/bin/env python3
"""Parse WSI-level GeoJSON rectangle annotations into a flat CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from common import load_json, normalize_label, strip_known_suffixes

LABEL_KEYS = [
    "label", "class", "category", "classification", "name", "object_type", "yokohama_category",
    "diagnostic_category", "pathClass", "path_class",
]


def extract_label(properties: dict[str, Any]) -> str:
    """Extract a likely annotation label from GeoJSON feature properties."""
    for key in LABEL_KEYS:
        value = properties.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            # QuPath often stores classification as {"name": "...", "color": [...]}
            for nested_key in ["name", "label", "class"]:
                if nested_key in value:
                    return normalize_label(value[nested_key])
        else:
            label = normalize_label(value)
            if label:
                return label
    # Try any string-like property containing C1-C5 or Roman numerals.
    for value in properties.values():
        if isinstance(value, str):
            label = normalize_label(value)
            if label in {"C1", "C2", "C3", "C4", "C5"}:
                return label
    return ""


def flatten_coords(coords: Any) -> list[tuple[float, float]]:
    """Flatten nested GeoJSON coordinate arrays to x/y pairs."""
    points: list[tuple[float, float]] = []
    if not isinstance(coords, (list, tuple)):
        return points
    if len(coords) >= 2 and all(isinstance(v, (int, float)) for v in coords[:2]):
        points.append((float(coords[0]), float(coords[1])))
        return points
    for item in coords:
        points.extend(flatten_coords(item))
    return points


def feature_bbox(feature: dict[str, Any]) -> tuple[float, float, float, float] | None:
    geom = feature.get("geometry") or {}
    points = flatten_coords(geom.get("coordinates"))
    if not points:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def parse_geojson_file(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    data = load_json(path)
    features = data.get("features", []) if isinstance(data, dict) else []
    rows = []
    stem = strip_known_suffixes(path.name)
    for idx, feature in enumerate(features):
        bbox = feature_bbox(feature)
        if bbox is None:
            continue
        x_min, y_min, x_max, y_max = bbox
        props = feature.get("properties") or {}
        label = extract_label(props)
        rows.append({
            "geojson_file": path.name,
            "wsi_file_stem": stem,
            "annotation_index": idx,
            "label": label,
            "x_min": round(x_min, 3),
            "y_min": round(y_min, 3),
            "x_max": round(x_max, 3),
            "y_max": round(y_max, 3),
            "width": round(x_max - x_min, 3),
            "height": round(y_max - y_min, 3),
            "geometry_type": (feature.get("geometry") or {}).get("type", ""),
        })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse WSI-level GeoJSON annotations into CSV.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--geojson", type=Path, help="Single GeoJSON file.")
    group.add_argument("--geojson-dir", type=Path, help="Directory containing GeoJSON files.")
    parser.add_argument("--out", type=Path, required=True, help="Output CSV path.")
    args = parser.parse_args()

    if args.geojson:
        paths = [args.geojson]
    else:
        paths = sorted(list(args.geojson_dir.glob("*.geojson")) + list(args.geojson_dir.glob("*.json")))

    all_rows = []
    for path in tqdm(paths, desc="Parsing GeoJSON"):
        all_rows.extend(parse_geojson_file(path))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(all_rows).to_csv(args.out, index=False)
    print(f"Parsed {len(paths)} GeoJSON files and {len(all_rows)} annotations.")
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
