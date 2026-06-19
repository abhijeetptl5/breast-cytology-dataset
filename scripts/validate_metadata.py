#!/usr/bin/env python3
"""Validate metadata CSV files for the breast FNAC cytology dataset.

This script checks headline counts, class counts, patient/slide linkage,
metadata filename coverage, and common CSV hygiene problems.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import pandas as pd

from common import (
    as_int,
    find_col,
    load_config,
    normalize_label,
    pass_fail,
    print_summary,
    read_csv_safely,
    validation_row,
    write_csv,
)

PATIENT_ID_ALIASES = ["patient_id", "patient_identifier", "case_id", "subject_id"]
SLIDE_ID_ALIASES = ["slide_number", "slide_id", "wsi_id", "wsi_file_stem"]
WSI_STEM_ALIASES = ["wsi_file_stem", "wsi_stem", "wsi_id", "slide_number", "slide_id"]
STAIN_ALIASES = ["stain_type", "stain", "staining"]
DIAGNOSIS_ALIASES = ["diagnosis_group", "diagnosis", "diagnostic_group"]
CLASS_ALIASES = ["yokohama_category", "category", "class", "diagnostic_category"]
PATCH_TOTAL_ALIASES = ["total_patch_count", "patch_count", "n_patches", "number_of_patches"]
SITE_ALIASES = ["study_site", "site", "center", "centre", "hospital_center"]
GEOJSON_AVAILABLE_ALIASES = ["geojson_file_available", "geojson_annotation_available", "annotation_available"]
PATCH_AVAILABLE_ALIASES = ["patch_annotation_available", "patch_available", "patches_available"]

PATCH_CLASS_ALIASES = {
    "C1": ["c1_patch_count", "c1_patches", "patch_count_c1", "category_i_patch_count"],
    "C2": ["c2_patch_count", "c2_patches", "patch_count_c2", "category_ii_patch_count"],
    "C3": ["c3_patch_count", "c3_patches", "patch_count_c3", "category_iii_patch_count"],
    "C4": ["c4_patch_count", "c4_patches", "patch_count_c4", "category_iv_patch_count"],
    "C5": ["c5_patch_count", "c5_patches", "patch_count_c5", "category_v_patch_count"],
}


def load_metadata_files(metadata_dir: Path) -> dict[str, pd.DataFrame]:
    files = {}
    for path in sorted(metadata_dir.glob("*.csv")):
        files[path.name] = read_csv_safely(path)
    return files


def unique_count(df: pd.DataFrame, col: str | None) -> int:
    if not col:
        return 0
    return int(df[col].astype(str).str.strip().replace("", pd.NA).dropna().nunique())


def count_by_col(df: pd.DataFrame, col: str | None) -> dict[str, int]:
    if not col:
        return {}
    s = df[col].astype(str).str.strip()
    return {str(k): int(v) for k, v in s.value_counts(dropna=False).sort_index().items()}


def patient_level_counts(master: pd.DataFrame, patient_col: str, class_or_diag_col: str) -> dict[str, int]:
    tmp = master[[patient_col, class_or_diag_col]].drop_duplicates()
    # If a patient has multiple labels, count the first unique label per patient and warn elsewhere.
    tmp = tmp.drop_duplicates(subset=[patient_col], keep="first")
    return {str(k): int(v) for k, v in tmp[class_or_diag_col].astype(str).str.strip().value_counts().sort_index().items()}


def get_expected(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("expected", {}) if config else {}


def validate_required_files(metadata_dir: Path, files: dict[str, pd.DataFrame], config: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    required = config.get("required_metadata_files", [])
    if not required:
        required = [
            "master_metadata.csv", "patient_metadata.csv", "slide_metadata.csv", "site_metadata.csv",
            "class_summary.csv", "dataset_summary.csv", "metadata_validation_summary.csv", "data_dictionary.csv",
        ]
    for fname in required:
        exists = (metadata_dir / fname).exists()
        rows.append(validation_row(f"required_file::{fname}", exists, True, pass_fail(exists)))
    return rows


def validate_data_dictionary(files: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows = []
    dd = files.get("data_dictionary.csv")
    if dd is None:
        rows.append(validation_row("data_dictionary_present", False, True, "FAIL"))
        return rows

    extra_cols = [c for c in dd.columns if str(c).startswith("Unnamed") or str(c).strip() == ""]
    rows.append(validation_row("data_dictionary_extra_blank_columns", len(extra_cols), 0, pass_fail(len(extra_cols) == 0), ", ".join(extra_cols)))

    file_col = find_col(dd, ["file_name", "filename", "file"], required=False)
    if file_col:
        file_values = set(dd[file_col].astype(str).str.strip())
        old_public = sorted([v for v in file_values if "_public.csv" in v])
        rows.append(validation_row("data_dictionary_no_old_public_filenames", len(old_public), 0, pass_fail(len(old_public) == 0), "; ".join(old_public)))

        expected_files = {
            "master_metadata.csv", "patient_metadata.csv", "slide_metadata.csv", "site_metadata.csv",
            "class_summary.csv", "dataset_summary.csv", "metadata_validation_summary.csv", "data_dictionary.csv",
        }
        missing = sorted(expected_files - file_values)
        rows.append(validation_row("data_dictionary_file_coverage", len(expected_files) - len(missing), len(expected_files), pass_fail(not missing), "; missing: " + "; ".join(missing) if missing else ""))
    else:
        rows.append(validation_row("data_dictionary_file_name_column", "missing", "present", "FAIL"))
    return rows


def validate_master(master: pd.DataFrame, expected: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    patient_col = find_col(master, PATIENT_ID_ALIASES, required=True, label="patient id column")
    slide_col = find_col(master, SLIDE_ID_ALIASES, required=True, label="slide id column")
    wsi_col = find_col(master, WSI_STEM_ALIASES, required=False)
    stain_col = find_col(master, STAIN_ALIASES, required=False)
    diagnosis_col = find_col(master, DIAGNOSIS_ALIASES, required=False)
    class_col = find_col(master, CLASS_ALIASES, required=False)
    patch_total_col = find_col(master, PATCH_TOTAL_ALIASES, required=False)
    site_col = find_col(master, SITE_ALIASES, required=False)
    geojson_avail_col = find_col(master, GEOJSON_AVAILABLE_ALIASES, required=False)
    patch_avail_col = find_col(master, PATCH_AVAILABLE_ALIASES, required=False)

    n_patients = unique_count(master, patient_col)
    n_wsis = unique_count(master, wsi_col or slide_col)
    rows.append(validation_row("unique_patients", n_patients, expected.get("n_patients", ""), pass_fail(not expected.get("n_patients") or n_patients == expected.get("n_patients"))))
    rows.append(validation_row("unique_wsis", n_wsis, expected.get("n_wsis", ""), pass_fail(not expected.get("n_wsis") or n_wsis == expected.get("n_wsis"))))

    if stain_col and expected.get("stain_counts"):
        counts = count_by_col(master, stain_col)
        for stain, exp in expected["stain_counts"].items():
            obs = counts.get(stain, 0)
            rows.append(validation_row(f"stain_count::{stain}", obs, exp, pass_fail(obs == exp)))

    if diagnosis_col and expected.get("diagnosis_counts"):
        wsi_counts = count_by_col(master, diagnosis_col)
        pat_counts = patient_level_counts(master, patient_col, diagnosis_col)
        for diag, exp_dict in expected["diagnosis_counts"].items():
            rows.append(validation_row(f"diagnosis_wsi_count::{diag}", wsi_counts.get(diag, 0), exp_dict.get("wsis", ""), pass_fail(wsi_counts.get(diag, 0) == exp_dict.get("wsis"))))
            rows.append(validation_row(f"diagnosis_patient_count::{diag}", pat_counts.get(diag, 0), exp_dict.get("patients", ""), pass_fail(pat_counts.get(diag, 0) == exp_dict.get("patients"))))

    if class_col and expected.get("class_counts"):
        normalized = master[class_col].map(normalize_label)
        tmp = master.copy()
        tmp["__class_norm"] = normalized
        wsi_counts = {str(k): int(v) for k, v in tmp["__class_norm"].value_counts().sort_index().items()}
        pat_tmp = tmp[[patient_col, "__class_norm"]].drop_duplicates(subset=[patient_col], keep="first")
        pat_counts = {str(k): int(v) for k, v in pat_tmp["__class_norm"].value_counts().sort_index().items()}
        for cls, exp_dict in expected["class_counts"].items():
            rows.append(validation_row(f"class_wsi_count::{cls}", wsi_counts.get(cls, 0), exp_dict.get("wsis", ""), pass_fail(wsi_counts.get(cls, 0) == exp_dict.get("wsis"))))
            rows.append(validation_row(f"class_patient_count::{cls}", pat_counts.get(cls, 0), exp_dict.get("patients", ""), pass_fail(pat_counts.get(cls, 0) == exp_dict.get("patients"))))

    if patch_total_col:
        total_patches = sum(as_int(v) for v in master[patch_total_col])
        rows.append(validation_row("total_patch_count", total_patches, expected.get("n_patches", ""), pass_fail(not expected.get("n_patches") or total_patches == expected.get("n_patches"))))

        zero_patch = int((master[patch_total_col].map(as_int) == 0).sum())
        rows.append(validation_row("zero_patch_wsis", zero_patch, "documented", "PASS" if zero_patch >= 0 else "FAIL"))

    # Sum class-specific patch counts if available.
    patch_class_sum = 0
    class_patch_details = []
    for cls, aliases in PATCH_CLASS_ALIASES.items():
        col = find_col(master, aliases, required=False)
        if col:
            obs = sum(as_int(v) for v in master[col])
            patch_class_sum += obs
            exp = expected.get("class_counts", {}).get(cls, {}).get("patches", "")
            rows.append(validation_row(f"class_patch_count::{cls}", obs, exp, pass_fail(not exp or obs == exp)))
            class_patch_details.append(cls)
    if class_patch_details and expected.get("n_patches"):
        rows.append(validation_row("class_patch_counts_sum", patch_class_sum, expected.get("n_patches"), pass_fail(patch_class_sum == expected.get("n_patches"))))

    if geojson_avail_col:
        geo_counts = count_by_col(master, geojson_avail_col)
        rows.append(validation_row("geojson_availability_values", geo_counts, "review", "PASS"))

    if patch_avail_col:
        patch_counts = count_by_col(master, patch_avail_col)
        rows.append(validation_row("patch_annotation_availability_values", patch_counts, "review", "PASS"))

    if site_col:
        empty_sites = int((master[site_col].astype(str).str.strip() == "").sum())
        rows.append(validation_row("empty_site_values", empty_sites, 0, pass_fail(empty_sites == 0)))

    # Check patient does not have conflicting diagnosis/class/site if columns exist.
    for col, label in [(diagnosis_col, "diagnosis"), (class_col, "class"), (site_col, "site")]:
        if col:
            conflicts = master.groupby(patient_col)[col].nunique(dropna=False)
            n_conflict = int((conflicts > 1).sum())
            status = "WARN" if n_conflict else "PASS"
            rows.append(validation_row(f"patient_level_{label}_conflicts", n_conflict, 0, status))

    return rows


def validate_summary_files(files: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows = []
    # Basic parse/shape checks. Detailed values are covered by master_metadata.
    for fname in ["patient_metadata.csv", "slide_metadata.csv", "site_metadata.csv", "class_summary.csv", "dataset_summary.csv", "metadata_validation_summary.csv"]:
        df = files.get(fname)
        if df is None:
            rows.append(validation_row(f"summary_file_present::{fname}", False, True, "FAIL"))
        else:
            rows.append(validation_row(f"summary_file_nonempty::{fname}", len(df), ">0", pass_fail(len(df) > 0)))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate breast FNAC metadata files.")
    parser.add_argument("--metadata-dir", type=Path, required=True, help="Path to metadata directory.")
    parser.add_argument("--config", type=Path, default=None, help="Optional YAML config with expected counts.")
    parser.add_argument("--out", type=Path, default=Path("outputs/metadata_validation_report.csv"), help="Output validation CSV.")
    args = parser.parse_args()

    config = load_config(args.config)
    expected = get_expected(config)
    files = load_metadata_files(args.metadata_dir)

    rows: list[dict[str, Any]] = []
    rows.extend(validate_required_files(args.metadata_dir, files, config))
    rows.extend(validate_data_dictionary(files))
    rows.extend(validate_summary_files(files))

    master = files.get("master_metadata.csv")
    if master is None:
        master = files.get("slide_metadata.csv")
    if master is None:
        rows.append(validation_row("master_or_slide_metadata_present", False, True, "FAIL"))
    else:
        rows.extend(validate_master(master, expected))

    write_csv(rows, args.out)
    print_summary(rows)
    print(f"Wrote validation report to: {args.out}")


if __name__ == "__main__":
    main()
