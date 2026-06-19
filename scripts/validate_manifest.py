#!/usr/bin/env python3
"""Validate the Zenodo WSI manifest for the breast FNAC cytology dataset."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import (
    find_col,
    load_config,
    pass_fail,
    print_summary,
    read_csv_safely,
    strip_known_suffixes,
    validation_row,
    write_csv,
)

FILENAME_ALIASES = ["filename", "file_name", "wsi_filename", "wsi_file"]
SIZE_ALIASES = ["filesize_bytes", "file_size_bytes", "size", "size_bytes"]
CHECKSUM_ALIASES = ["checksum", "md5", "file_checksum"]
FILE_ID_ALIASES = ["file_id", "zenodo_file_id", "id"]
RECORD_ALIASES = ["deposition_id", "record_id", "zenodo_record_id", "zenodo_record", "recid"]
URL_ALIASES = ["zenodo_record_url", "record_url", "url"]
STEM_ALIASES = ["wsi_file_stem", "file_stem", "stem"]
FORMAT_ALIASES = ["file_format", "format", "wsi_format"]
SET_ALIASES = ["set_number", "set", "record_set"]


def checksum_is_md5(value: str) -> bool:
    s = str(value).strip().lower()
    if s.startswith("md5:"):
        s = s.split(":", 1)[1]
    return bool(re.fullmatch(r"[a-f0-9]{32}", s))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Zenodo WSI manifest.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to zenodo_files_manifest.csv.")
    parser.add_argument("--slide-metadata", type=Path, default=None, help="Optional slide/master metadata CSV for stem matching.")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config with expected counts.")
    parser.add_argument("--out", type=Path, default=Path("outputs/manifest_validation_report.csv"), help="Output validation CSV.")
    args = parser.parse_args()

    config = load_config(args.config)
    expected = config.get("expected", {}) if config else {}
    manifest = read_csv_safely(args.manifest)

    rows = []
    filename_col = find_col(manifest, FILENAME_ALIASES, required=True, label="filename column")
    size_col = find_col(manifest, SIZE_ALIASES, required=False)
    checksum_col = find_col(manifest, CHECKSUM_ALIASES, required=False)
    file_id_col = find_col(manifest, FILE_ID_ALIASES, required=False)
    record_col = find_col(manifest, RECORD_ALIASES, required=False)
    url_col = find_col(manifest, URL_ALIASES, required=False)
    stem_col = find_col(manifest, STEM_ALIASES, required=False)
    format_col = find_col(manifest, FORMAT_ALIASES, required=False)
    set_col = find_col(manifest, SET_ALIASES, required=False)

    filenames = manifest[filename_col].astype(str).str.strip()
    rows.append(validation_row("manifest_rows", len(manifest), expected.get("n_wsis", ""), pass_fail(not expected.get("n_wsis") or len(manifest) == expected.get("n_wsis"))))
    rows.append(validation_row("unique_manifest_filenames", filenames.nunique(), len(manifest), pass_fail(filenames.nunique() == len(manifest))))

    ext = str(expected.get("wsi_extension", ".ndpi")).lower()
    n_ext = int(filenames.str.lower().str.endswith(ext).sum())
    rows.append(validation_row(f"files_with_extension::{ext}", n_ext, len(manifest), pass_fail(n_ext == len(manifest))))

    if stem_col:
        stems = manifest[stem_col].astype(str).str.strip()
    else:
        stems = filenames.map(strip_known_suffixes)
    rows.append(validation_row("unique_wsi_file_stems", stems.nunique(), len(manifest), pass_fail(stems.nunique() == len(manifest))))

    if format_col:
        bad_formats = manifest.loc[manifest[format_col].astype(str).str.upper().str.strip() != "NDPI", format_col].unique().tolist()
        rows.append(validation_row("file_format_values_are_ndpi", len(bad_formats), 0, pass_fail(len(bad_formats) == 0), "; ".join(map(str, bad_formats))))

    if size_col:
        sizes = manifest[size_col].astype(str).str.replace(",", "", regex=False)
        positive = sizes.astype(float) > 0
        rows.append(validation_row("positive_file_sizes", int(positive.sum()), len(manifest), pass_fail(int(positive.sum()) == len(manifest))))
    else:
        rows.append(validation_row("filesize_column_present", False, True, "WARN"))

    if checksum_col:
        valid = manifest[checksum_col].map(checksum_is_md5)
        rows.append(validation_row("valid_md5_checksums", int(valid.sum()), len(manifest), pass_fail(int(valid.sum()) == len(manifest))))
    else:
        rows.append(validation_row("checksum_column_present", False, True, "WARN"))

    if file_id_col:
        n_missing = int((manifest[file_id_col].astype(str).str.strip() == "").sum())
        rows.append(validation_row("missing_file_ids", n_missing, 0, pass_fail(n_missing == 0)))
    else:
        rows.append(validation_row("file_id_column_present", False, True, "WARN"))

    if record_col:
        n_records = manifest[record_col].astype(str).str.strip().nunique()
        rows.append(validation_row("unique_zenodo_wsi_records", n_records, expected.get("n_zenodo_wsi_records", ""), pass_fail(not expected.get("n_zenodo_wsi_records") or n_records == expected.get("n_zenodo_wsi_records"))))
        counts = manifest.groupby(record_col, sort=False)[filename_col].count().tolist()
        expected_counts = expected.get("wsi_record_counts")
        if expected_counts:
            rows.append(validation_row("wsi_count_sequence_by_record", counts, expected_counts, pass_fail(counts == expected_counts)))
    else:
        rows.append(validation_row("zenodo_record_column_present", False, True, "WARN"))

    if url_col:
        good = manifest[url_col].astype(str).str.contains(r"zenodo\.org/records?/[0-9]+", regex=True)
        rows.append(validation_row("zenodo_record_urls_valid", int(good.sum()), len(manifest), pass_fail(int(good.sum()) == len(manifest))))

    if args.slide_metadata:
        slide_meta = read_csv_safely(args.slide_metadata)
        meta_stem_col = find_col(slide_meta, ["wsi_file_stem", "slide_number", "slide_id", "wsi_id"], required=True, label="metadata WSI stem")
        meta_stems = set(slide_meta[meta_stem_col].astype(str).str.strip())
        manifest_stems = set(stems.astype(str).str.strip())
        missing_in_manifest = sorted(meta_stems - manifest_stems)
        missing_in_metadata = sorted(manifest_stems - meta_stems)
        rows.append(validation_row("metadata_stems_missing_in_manifest", len(missing_in_manifest), 0, pass_fail(len(missing_in_manifest) == 0), "; ".join(missing_in_manifest[:10])))
        rows.append(validation_row("manifest_stems_missing_in_metadata", len(missing_in_metadata), 0, pass_fail(len(missing_in_metadata) == 0), "; ".join(missing_in_metadata[:10])))

    write_csv(rows, args.out)
    print_summary(rows)
    print(f"Wrote validation report to: {args.out}")


if __name__ == "__main__":
    main()
