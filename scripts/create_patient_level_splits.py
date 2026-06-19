#!/usr/bin/env python3
"""Create leakage-safe train/validation/test splits at patient level."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from common import find_col, normalize_label, read_csv_safely

PATIENT_ID_ALIASES = ["patient_id", "patient_identifier", "case_id", "subject_id"]
CLASS_ALIASES = ["yokohama_category", "category", "class", "diagnostic_category"]
DIAGNOSIS_ALIASES = ["diagnosis_group", "diagnosis", "diagnostic_group"]
SITE_ALIASES = ["study_site", "site", "center", "centre"]


def make_patient_table(metadata: pd.DataFrame, patient_col: str, stratify_col: str | None) -> pd.DataFrame:
    cols = [patient_col]
    if stratify_col and stratify_col not in cols:
        cols.append(stratify_col)
    patients = metadata[cols].drop_duplicates().copy()
    if stratify_col:
        # If a patient appears with multiple stratification labels, keep the most frequent.
        patients = (
            metadata.groupby(patient_col)[stratify_col]
            .agg(lambda x: x.astype(str).value_counts().index[0])
            .reset_index()
        )
    else:
        patients = metadata[[patient_col]].drop_duplicates().copy()
        patients["stratify_label"] = "all"
        stratify_col = "stratify_label"
    return patients.rename(columns={patient_col: "patient_id", stratify_col: "stratify_label"})


def safe_stratify(labels: pd.Series) -> pd.Series | None:
    counts = labels.value_counts()
    # Stratification requires at least two patients per class in each split step.
    if (counts < 2).any():
        print("WARNING: At least one stratification class has fewer than 2 patients. Falling back to unstratified split.")
        return None
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description="Create patient-level train/validation/test splits.")
    parser.add_argument("--metadata", type=Path, required=True, help="Patient, slide, or master metadata CSV.")
    parser.add_argument("--out", type=Path, required=True, help="Output patient split CSV.")
    parser.add_argument("--slide-out", type=Path, default=None, help="Optional slide-level split CSV, when metadata has slide rows.")
    parser.add_argument("--patch-index", type=Path, default=None, help="Optional patch_index.csv to assign patch-level splits.")
    parser.add_argument("--patch-out", type=Path, default=None, help="Optional output patch_index_with_splits.csv.")
    parser.add_argument("--stratify-col", type=str, default="yokohama_category", help="Column to stratify by. Use 'diagnosis_group' or 'yokohama_category'.")
    parser.add_argument("--train", type=float, default=0.70)
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--test", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if abs(args.train + args.val + args.test - 1.0) > 1e-6:
        raise ValueError("train + val + test must sum to 1.0")

    metadata = read_csv_safely(args.metadata)
    patient_col = find_col(metadata, PATIENT_ID_ALIASES, required=True, label="patient id")

    stratify_col = None
    if args.stratify_col:
        if args.stratify_col == "yokohama_category":
            stratify_col = find_col(metadata, CLASS_ALIASES, required=False)
        elif args.stratify_col == "diagnosis_group":
            stratify_col = find_col(metadata, DIAGNOSIS_ALIASES, required=False)
        else:
            stratify_col = find_col(metadata, [args.stratify_col], required=False)

    patients = make_patient_table(metadata, patient_col, stratify_col)
    patients["stratify_label"] = patients["stratify_label"].map(lambda x: normalize_label(x) if str(x).upper().startswith(("C", "CATEGORY", "I", "V")) else str(x).strip())

    train_df, temp_df = train_test_split(
        patients,
        train_size=args.train,
        random_state=args.seed,
        shuffle=True,
        stratify=safe_stratify(patients["stratify_label"]),
    )

    relative_test = args.test / (args.val + args.test)
    strat_temp = safe_stratify(temp_df["stratify_label"])
    val_df, test_df = train_test_split(
        temp_df,
        test_size=relative_test,
        random_state=args.seed,
        shuffle=True,
        stratify=strat_temp,
    )

    train_df = train_df.copy(); train_df["split"] = "train"
    val_df = val_df.copy(); val_df["split"] = "val"
    test_df = test_df.copy(); test_df["split"] = "test"
    split_df = pd.concat([train_df, val_df, test_df], ignore_index=True).sort_values(["split", "patient_id"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    split_df.to_csv(args.out, index=False)
    print(f"Wrote patient-level splits: {args.out}")
    print(split_df.groupby(["split", "stratify_label"]).size().unstack(fill_value=0))

    split_map = split_df.set_index("patient_id")["split"].to_dict()

    if args.slide_out:
        slide_df = metadata.copy()
        slide_df["split"] = slide_df[patient_col].map(split_map)
        args.slide_out.parent.mkdir(parents=True, exist_ok=True)
        slide_df.to_csv(args.slide_out, index=False)
        print(f"Wrote slide/metadata-level splits: {args.slide_out}")

    if args.patch_index:
        if not args.patch_out:
            raise ValueError("--patch-out is required when --patch-index is provided")
        patch_df = read_csv_safely(args.patch_index)
        patch_patient_col = find_col(patch_df, PATIENT_ID_ALIASES, required=True, label="patient id in patch index")
        patch_df["split"] = patch_df[patch_patient_col].map(split_map)
        missing = int((patch_df["split"].astype(str).str.strip() == "").sum())
        if missing:
            print(f"WARNING: {missing} patches did not receive a split. Check patient_id linkage.")
        args.patch_out.parent.mkdir(parents=True, exist_ok=True)
        patch_df.to_csv(args.patch_out, index=False)
        print(f"Wrote patch-level splits: {args.patch_out}")


if __name__ == "__main__":
    main()
