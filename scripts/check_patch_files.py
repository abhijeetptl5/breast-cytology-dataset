#!/usr/bin/env python3
"""Check patch files for existence, readability, class-folder validity, and basic image dimensions."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from PIL import Image
from tqdm import tqdm

from common import DEFAULT_CLASS_FOLDER_MAP, IMAGE_EXTENSIONS, load_config, pass_fail, validation_row, write_csv, print_summary


def check_image(path: Path) -> tuple[bool, int | None, int | None, str]:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            width, height = img.size
        return True, width, height, ""
    except Exception as exc:
        return False, None, None, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate extracted patch image files.")
    parser.add_argument("--patches-dir", type=Path, required=True, help="Path to patches/ directory.")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config.")
    parser.add_argument("--max-read", type=int, default=0, help="Maximum number of patch files to open/read. Use 0 for all files.")
    parser.add_argument("--out", type=Path, default=Path("outputs/patch_file_validation_report.csv"), help="Output validation report CSV.")
    parser.add_argument("--details-out", type=Path, default=None, help="Optional per-file detail CSV.")
    args = parser.parse_args()

    config = load_config(args.config)
    expected = config.get("expected", {}) if config else {}
    class_folder_map = config.get("class_folder_map", DEFAULT_CLASS_FOLDER_MAP)

    patch_paths = [p for p in args.patches_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    rows = []
    details = []
    rows.append(validation_row("patch_files_found", len(patch_paths), expected.get("n_patches", ""), pass_fail(not expected.get("n_patches") or len(patch_paths) == expected.get("n_patches"))))

    class_folders = []
    for p in patch_paths:
        try:
            rel = p.relative_to(args.patches_dir)
            class_folders.append(rel.parts[1] if len(rel.parts) >= 2 else "")
        except Exception:
            class_folders.append("")
    invalid_folders = sorted(set(class_folders) - set(class_folder_map.keys()))
    rows.append(validation_row("invalid_class_folders", len(invalid_folders), 0, pass_fail(len(invalid_folders) == 0), "; ".join(invalid_folders)))

    to_read = patch_paths if args.max_read == 0 else patch_paths[: args.max_read]
    readable = 0
    widths = []
    heights = []
    for p in tqdm(to_read, desc="Checking image readability"):
        ok, w, h, error = check_image(p)
        readable += int(ok)
        if w is not None:
            widths.append(w)
        if h is not None:
            heights.append(h)
        if args.details_out:
            details.append({
                "patch_relative_path": p.relative_to(args.patches_dir).as_posix(),
                "readable": ok,
                "width": w or "",
                "height": h or "",
                "error": error,
            })
    rows.append(validation_row("readable_patch_files_checked", readable, len(to_read), pass_fail(readable == len(to_read))))
    if widths and heights:
        rows.append(validation_row("min_patch_width", min(widths), ">0", pass_fail(min(widths) > 0)))
        rows.append(validation_row("min_patch_height", min(heights), ">0", pass_fail(min(heights) > 0)))
        rows.append(validation_row("unique_patch_sizes_checked", len(set(zip(widths, heights))), "variable sizes allowed", "PASS"))

    write_csv(rows, args.out)
    if args.details_out:
        pd.DataFrame(details).to_csv(args.details_out, index=False)
    print_summary(rows)
    print(f"Wrote: {args.out}")


if __name__ == "__main__":
    main()
