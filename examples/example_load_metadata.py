#!/usr/bin/env python3
"""Example: load metadata and print headline counts."""

from pathlib import Path
import pandas as pd

metadata_dir = Path("/path/to/breast-cytology-main/metadata")
master = pd.read_csv(metadata_dir / "master_metadata.csv")

print("Rows:", len(master))
print("Patients:", master["patient_id"].nunique())
print("WSIs:", master["wsi_file_stem"].nunique() if "wsi_file_stem" in master.columns else master["slide_number"].nunique())
print("Stain counts:")
print(master["stain_type"].value_counts())
