#!/usr/bin/env python3
"""Visualize GeoJSON patch annotations on a WSI thumbnail.

Requires OpenSlide for NDPI files. On Ubuntu, install the system package first:
  sudo apt-get install openslide-tools
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from parse_geojson_annotations import parse_geojson_file

LABEL_COLORS = {
    "C1": "#1f77b4",
    "C2": "#2ca02c",
    "C3": "#ff7f0e",
    "C4": "#9467bd",
    "C5": "#d62728",
    "": "#7f7f7f",
}


def load_wsi_thumbnail(wsi_path: Path, max_size: int) -> tuple[Image.Image, float, float]:
    try:
        import openslide
    except ImportError as exc:
        raise RuntimeError("openslide-python is required to read NDPI WSI files. Install openslide-python and the OpenSlide system library.") from exc

    slide = openslide.OpenSlide(str(wsi_path))
    width, height = slide.dimensions
    scale = min(max_size / width, max_size / height, 1.0)
    thumb_size = (int(width * scale), int(height * scale))
    thumb = slide.get_thumbnail(thumb_size).convert("RGB")
    slide.close()
    return thumb, thumb.width / width, thumb.height / height


def draw_annotations(thumb: Image.Image, annotations: list[dict], scale_x: float, scale_y: float) -> Image.Image:
    out = thumb.copy()
    draw = ImageDraw.Draw(out)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    for ann in annotations:
        label = ann.get("label", "")
        color = LABEL_COLORS.get(label, "#7f7f7f")
        x0 = float(ann["x_min"]) * scale_x
        y0 = float(ann["y_min"]) * scale_y
        x1 = float(ann["x_max"]) * scale_x
        y1 = float(ann["y_max"]) * scale_y
        draw.rectangle([x0, y0, x1, y1], outline=color, width=3)
        if label:
            draw.text((x0 + 3, y0 + 3), label, fill=color, font=font)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw GeoJSON annotations on a WSI thumbnail.")
    parser.add_argument("--wsi", type=Path, required=True, help="Path to NDPI WSI file.")
    parser.add_argument("--geojson", type=Path, required=True, help="Path to corresponding GeoJSON file.")
    parser.add_argument("--out", type=Path, required=True, help="Output PNG/JPG path.")
    parser.add_argument("--max-size", type=int, default=2000, help="Maximum thumbnail width/height.")
    args = parser.parse_args()

    thumb, scale_x, scale_y = load_wsi_thumbnail(args.wsi, args.max_size)
    annotations = parse_geojson_file(args.geojson)
    out = draw_annotations(thumb, annotations, scale_x, scale_y)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.out)
    print(f"Drew {len(annotations)} annotations.")
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
