#!/usr/bin/env python3
"""Shared utilities for breast FNAC cytology dataset scripts."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
import yaml

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

DEFAULT_CLASS_FOLDER_MAP = {
    "I": "C1",
    "II": "C2",
    "III": "C3",
    "IV": "C4",
    "V": "C5",
}

LABEL_ALIASES = {
    "1": "C1", "I": "C1", "C1": "C1", "CATEGORY 1": "C1", "INSUFFICIENT": "C1",
    "2": "C2", "II": "C2", "C2": "C2", "CATEGORY 2": "C2", "BENIGN": "C2",
    "3": "C3", "III": "C3", "C3": "C3", "CATEGORY 3": "C3", "ATYPICAL": "C3",
    "4": "C4", "IV": "C4", "C4": "C4", "CATEGORY 4": "C4", "SUSPICIOUS": "C4",
    "5": "C5", "V": "C5", "C5": "C5", "CATEGORY 5": "C5", "MALIGNANT": "C5",
}


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load YAML configuration. Returns an empty dict when path is None."""
    if path is None:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def read_csv_safely(path: str | Path) -> pd.DataFrame:
    """Read a CSV as strings while preserving empty values."""
    path = Path(path)
    try:
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    except pd.errors.ParserError as exc:
        raise RuntimeError(
            f"Failed to parse CSV file: {path}. This often happens when comma-separated "
            "allowed values inside a cell were not quoted. Use semicolons or quote the field."
        ) from exc


def write_csv(rows: list[dict[str, Any]], path: str | Path) -> None:
    """Write a list of dictionaries to CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_colname(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def normalized_columns(df: pd.DataFrame) -> dict[str, str]:
    """Return mapping of normalized column names to original column names."""
    return {normalize_colname(c): c for c in df.columns}


def find_col(df: pd.DataFrame, aliases: Iterable[str], required: bool = False, label: str = "column") -> Optional[str]:
    """Find a column by normalized aliases."""
    norm_map = normalized_columns(df)
    for alias in aliases:
        key = normalize_colname(alias)
        if key in norm_map:
            return norm_map[key]
    if required:
        raise KeyError(f"Could not find required {label}. Tried aliases: {list(aliases)}")
    return None


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(str(value).replace(",", "")))
    except Exception:
        return default


def normalize_label(value: Any) -> str:
    """Normalize category labels to C1-C5 where possible."""
    s = str(value).strip()
    if not s:
        return ""
    upper = s.upper().replace("-", " ").replace("_", " ")
    upper = re.sub(r"\s+", " ", upper)
    if upper in LABEL_ALIASES:
        return LABEL_ALIASES[upper]
    match = re.search(r"\bC\s*([1-5])\b", upper)
    if match:
        return f"C{match.group(1)}"
    match = re.search(r"CATEGORY\s*([1-5])", upper)
    if match:
        return f"C{match.group(1)}"
    return s


def strip_known_suffixes(filename: str) -> str:
    p = Path(str(filename).strip())
    name = p.name
    for suffix in [".ndpi", ".svs", ".mrxs", ".tif", ".tiff", ".geojson", ".json", ".png", ".jpg", ".jpeg"]:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return p.stem


def md5_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def validation_row(check: str, observed: Any, expected: Any = "", status: str = "PASS", details: str = "") -> dict[str, Any]:
    return {
        "check": check,
        "observed": observed,
        "expected": expected,
        "status": status,
        "details": details,
    }


def pass_fail(condition: bool) -> str:
    return "PASS" if condition else "FAIL"


def print_summary(rows: list[dict[str, Any]]) -> None:
    total = len(rows)
    failed = sum(1 for r in rows if str(r.get("status", "")).upper() == "FAIL")
    warned = sum(1 for r in rows if str(r.get("status", "")).upper() == "WARN")
    print(f"Validation checks: {total} | PASS: {total - failed - warned} | WARN: {warned} | FAIL: {failed}")
    for r in rows:
        if str(r.get("status", "")).upper() in {"FAIL", "WARN"}:
            print(f"[{r['status']}] {r['check']}: observed={r['observed']} expected={r['expected']} {r.get('details','')}")
