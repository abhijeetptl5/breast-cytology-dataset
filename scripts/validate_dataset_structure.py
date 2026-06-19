#!/usr/bin/env python3
"""Validate the expected top-level dataset structure.

Expected main release layout:
  breast-cytology-main/
    geojson/
    patches/
    metadata/
    manifest/
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common import IMAGE_EXTENSIONS, load_config, pass_fail, validation_row, write_csv, print_summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate top-level dataset directory structure.")
    parser.add_argument("--dataset-root", type=Path, required=True, help="Path to extracted breast-cytology-main directory.")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config with expected counts.")
    parser.add_argument("--out", type=Path, default=Path("outputs/dataset_structure_validation_report.csv"))
    args = parser.parse_args()

    config = load_config(args.config)
    expected = config.get("expected", {}) if config else {}

    rows = []
    for dirname in ["geojson", "patches", "metadata", "manifest"]:
        exists = (args.dataset_root / dirname).is_dir()
        rows.append(validation_row(f"top_level_dir::{dirname}", exists, True, pass_fail(exists)))

    geojson_dir = args.dataset_root / "geojson"
    if geojson_dir.exists():
        n_geojson = len(list(geojson_dir.glob("*.geojson"))) + len(list(geojson_dir.glob("*.json")))
        rows.append(validation_row("geojson_file_count", n_geojson, expected.get("n_wsis", ""), pass_fail(not expected.get("n_wsis") or n_geojson == expected.get("n_wsis"))))

    patch_dir = args.dataset_root / "patches"
    if patch_dir.exists():
        n_patch_files = len([p for p in patch_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS])
        rows.append(validation_row("patch_file_count", n_patch_files, expected.get("n_patches", ""), pass_fail(not expected.get("n_patches") or n_patch_files == expected.get("n_patches"))))

    manifest = args.dataset_root / "manifest" / "zenodo_files_manifest.csv"
    rows.append(validation_row("manifest_file_present", manifest.exists(), True, pass_fail(manifest.exists())))

    readme = args.dataset_root / "metadata" / "README_metadata_release.md"
    rows.append(validation_row("metadata_readme_present", readme.exists(), True, pass_fail(readme.exists())))

    write_csv(rows, args.out)
    print_summary(rows)
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
