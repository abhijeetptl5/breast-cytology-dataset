#!/usr/bin/env python3
"""Create a patch-level index from the released patches directory."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from common import DEFAULT_CLASS_FOLDER_MAP, IMAGE_EXTENSIONS, find_col, load_config, read_csv_safely


def build_patch_index(patches_dir: Path, class_folder_map: dict[str, str]) -> pd.DataFrame:
    rows = []
    if not patches_dir.exists():
        raise FileNotFoundError(f"Patches directory does not exist: {patches_dir}")

    wsi_dirs = [p for p in sorted(patches_dir.iterdir()) if p.is_dir()]
    for wsi_dir in tqdm(wsi_dirs, desc="Indexing WSI patch folders"):
        for class_dir in sorted([p for p in wsi_dir.iterdir() if p.is_dir()]):
            class_folder = class_dir.name
            label = class_folder_map.get(class_folder, "")
            for patch_path in sorted(class_dir.rglob("*")):
                if not patch_path.is_file() or patch_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                rows.append({
                    "patch_id": patch_path.stem,
                    "patch_filename": patch_path.name,
                    "patch_relative_path": patch_path.relative_to(patches_dir).as_posix(),
                    "wsi_file_stem": wsi_dir.name,
                    "class_folder": class_folder,
                    "yokohama_category": label,
                    "patch_extension": patch_path.suffix.lower(),
                })
    return pd.DataFrame(rows)


def merge_slide_metadata(patch_df: pd.DataFrame, slide_metadata_path: Path) -> pd.DataFrame:
    slide_df = read_csv_safely(slide_metadata_path)
    stem_col = find_col(slide_df, ["wsi_file_stem", "slide_number", "slide_id", "wsi_id"], required=True, label="WSI stem in slide metadata")
    keep_cols = [stem_col]
    for aliases in [
        ["patient_id"],
        ["slide_number", "slide_id"],
        ["stain_type", "stain"],
        ["diagnosis_group", "diagnosis"],
        ["study_site", "site", "center", "centre"],
    ]:
        col = find_col(slide_df, aliases, required=False)
        if col and col not in keep_cols:
            keep_cols.append(col)
    meta = slide_df[keep_cols].drop_duplicates(subset=[stem_col]).copy()
    meta = meta.rename(columns={stem_col: "wsi_file_stem"})
    return patch_df.merge(meta, on="wsi_file_stem", how="left")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create patch-level index CSV from patches directory.")
    parser.add_argument("--patches-dir", type=Path, required=True, help="Path to patches/ directory.")
    parser.add_argument("--slide-metadata", type=Path, default=None, help="Optional slide/master metadata CSV to merge patient/stain/site fields.")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config with class_folder_map.")
    parser.add_argument("--out", type=Path, required=True, help="Output patch index CSV.")
    args = parser.parse_args()

    config = load_config(args.config)
    class_folder_map = config.get("class_folder_map", DEFAULT_CLASS_FOLDER_MAP)
    patch_df = build_patch_index(args.patches_dir, class_folder_map)

    if args.slide_metadata:
        patch_df = merge_slide_metadata(patch_df, args.slide_metadata)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    patch_df.to_csv(args.out, index=False)
    print(f"Indexed {len(patch_df)} patch files.")
    print(f"Class counts:\n{patch_df['yokohama_category'].value_counts().sort_index().to_string() if len(patch_df) else 'No patches found'}")
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
