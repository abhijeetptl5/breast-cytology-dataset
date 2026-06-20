# Breast Cytology Dataset


This repository contains utility scripts for working with the **A Multi-Center Breast FNAC Cytology Dataset for AI-Assisted Patch-wise Classification Using C1--C5 Reporting Categories** dataset. The dataset is released through Zenodo and consists of breast fine needle aspiration cytology (FNAC) whole-slide images (WSIs), WSI-level GeoJSON box annotations, extracted patch images, metadata files, and a WSI manifest.

The repository is intended to help users validate the released metadata, inspect the Zenodo manifest, parse GeoJSON annotations, extract patches from NDPI WSIs, generate patch indices, create patient-level train/validation/test splits, visualize annotations, and run simple baseline patch-wise classification experiments.

## Dataset access

Main Zenodo record:

- **Title:** A Multi-Center Breast FNAC Cytology Dataset for AI-Assisted Patch-wise Classification Using C1--C5 Reporting Categories
- **DOI:** https://doi.org/10.5281/zenodo.20763900

The main Zenodo record contains extracted patch images, WSI-level GeoJSON annotation files, metadata files, a data dictionary, and a manifest linking WSI files to the corresponding Zenodo WSI records. The full set of 470 NDPI WSIs is distributed across 21 linked Zenodo records listed in the main Zenodo record and in `manifest/zenodo_files_manifest.csv`.

## Dataset overview

| Attribute | Value |
|---|---:|
| Patients | 321 |
| Whole-slide images | 470 |
| WSI format | NDPI |
| Scanner | Hamamatsu whole slide scanner |
| Magnification | 40x |
| Spatial resolution | 0.25 microns per pixel |
| PAP-stained WSIs | 190 |
| MGG-stained WSIs | 280 |
| Extracted patches | 7,398 |
| Approximate full dataset size | 950 GB |
| Main Zenodo records for WSIs | 21 linked records |

## Diagnostic group distribution

| Diagnosis group | Patients | WSIs |
|---|---:|---:|
| Non-cancerous | 209 | 304 |
| Cancerous | 112 | 166 |
| **Total** | **321** | **470** |

## C1--C5 category distribution

| Yokohama category | Description | Patients | WSIs | Extracted patches |
|---|---|---:|---:|---:|
| C1 | Insufficient / inadequate | 4 | 9 | 33 |
| C2 | Benign | 194 | 281 | 3,706 |
| C3 | Atypical | 11 | 14 | 478 |
| C4 | Suspicious for malignancy | 11 | 15 | 402 |
| C5 | Malignant | 101 | 151 | 2,779 |
| **Total** |  | **321** | **470** | **7,398** |

## Expected dataset structure

After downloading and extracting `breast-cytology-main.zip`, the expected structure is:

```text
breast-cytology-main/
  geojson/
    <WSI_ID>.geojson
    ...
  patches/
    <WSI_ID>/
      I/
        <patch images>
      II/
        <patch images>
      III/
        <patch images>
      IV/
        <patch images>
      V/
        <patch images>
  metadata/
    master_metadata.csv
    patient_metadata.csv
    slide_metadata.csv
    site_metadata.csv
    class_summary.csv
    dataset_summary.csv
    metadata_validation_summary.csv
    data_dictionary.csv
    README_metadata_release.md
  manifest/
    zenodo_files_manifest.csv
```

The 470 NDPI WSI files are stored separately across 21 linked Zenodo records. The file `manifest/zenodo_files_manifest.csv` maps each WSI filename to its linked Zenodo record.

## Label schema

The dataset follows the International Academy of Cytology Yokohama System for breast FNAC reporting:

| Label | Meaning |
|---|---|
| C1 | Insufficient or inadequate |
| C2 | Benign |
| C3 | Atypical |
| C4 | Suspicious for malignancy |
| C5 | Malignant |

The extracted patch directory uses Roman numeral class folders. These map to the C1--C5 categories as follows:

| Patch folder | Yokohama label |
|---|---|
| `I` | C1 insufficient / inadequate |
| `II` | C2 benign |
| `III` | C3 atypical |
| `IV` | C4 suspicious for malignancy |
| `V` | C5 malignant |


## Basic usage

Set paths according to your extracted dataset location. Example root layout:

```text
/path/to/breast-cytology/
  geojson/
  patches/
  metadata/
  manifest/
  wsis/
    <NDPI files downloaded from linked Zenodo records>
```

### Validate dataset folder structure

```bash
python scripts/validate_dataset_structure.py \
  --dataset-root /path/to/breast-cytology
```

### Validate metadata files

```bash
python scripts/validate_metadata.py \
  --metadata-dir /path/to/breast-cytology/metadata
```

This checks core dataset counts, patient-slide linkage, stain distributions, diagnosis distributions, C1--C5 category counts, patch counts, and data-dictionary coverage.

### Validate WSI manifest

```bash
python scripts/validate_manifest.py \
  --manifest /path/to/breast-cytology/manifest/zenodo_files_manifest.csv \
  --metadata-dir /path/to/breast-cytology/metadata
```

This checks that 470 NDPI WSI files are represented across 21 linked Zenodo records and that WSI stems match the metadata.

### Parse GeoJSON annotations

```bash
python scripts/parse_geojson_annotations.py \
  --geojson-dir /path/to/breast-cytology/geojson \
  --output-csv outputs/geojson_annotations.csv
```

This creates a flat table of WSI identifiers, annotation indices, labels, and rectangular box coordinates.

### Extract patches from WSI using GeoJSON

Single WSI mode:

```bash
python scripts/extract_patches_from_geojson.py \
  --wsi /path/to/wsis/11B2235241P.ndpi \
  --geojson /path/to/breast-cytology/geojson/11B2235241P.geojson \
  --output-dir /path/to/output_patches
```

Batch mode:

```bash
python scripts/extract_patches_from_geojson.py \
  --wsi-dir /path/to/wsis \
  --geojson-dir /path/to/breast-cytology/geojson \
  --output-dir /path/to/output_patches
```

Output patches are named using WSI stem and level-0 coordinates:

```text
<WSI_NAME>_x<X_COORD>_y<Y_COORD>.png
```

Example:

```text
11B2235241P_x12345_y67890.png
```

By default, patches are saved under:

```text
output_patches/<WSI_ID>/<LABEL_FOLDER>/<WSI_ID>_x<X>_y<Y>.png
```

### Create patch index

```bash
python scripts/create_patch_index.py \
  --patches-dir /path/to/breast-cytology/patches \
  --output-csv outputs/patch_index.csv
```

The patch index can be used for training, validation, and data inspection.

### Check patch files

```bash
python scripts/check_patch_files.py \
  --patches-dir /path/to/breast-cytology/patches \
  --metadata-dir /path/to/breast-cytology/metadata
```

This checks patch readability, class-folder organization, and linkage to parent WSI identifiers.

### Create patient-level splits

```bash
python scripts/create_patient_level_splits.py \
  --metadata-dir /path/to/breast-cytology/metadata \
  --output-csv outputs/patient_level_splits.csv \
  --stratify-by yokohama_category \
  --train 0.70 \
  --val 0.15 \
  --test 0.15 \
  --seed 42
```

Splitting should be performed at patient level rather than patch level to reduce leakage from visually similar patches from the same patient appearing in multiple subsets.

### Visualize WSI annotations

```bash
python scripts/visualize_wsi_annotations.py \
  --wsi /path/to/wsis/11B2235241P.ndpi \
  --geojson /path/to/breast-cytology/geojson/11B2235241P.geojson \
  --output outputs/11B2235241P_annotations.png
```

### Train a simple baseline classifier

```bash
python examples/example_train_baseline.py \
  --patch-index outputs/patch_index.csv \
  --splits outputs/patient_level_splits.csv \
  --output-dir outputs/baseline_resnet18
```

This baseline is intended only as a starter example. It should not be treated as a definitive benchmark, because apparently every dataset README now has to say the obvious before someone builds a leaderboard out of fumes.


## Citation

If you use this dataset or code, please cite the Zenodo dataset and the associated manuscript.

```bibtex
@dataset{Patil_2026_breast_fnac_cytology,
  author    = {Patil, Abhijeet and Jain, Garima and Sethi, Amit},
  title     = {{A Multi-Center Breast FNAC Cytology Dataset for AI-Assisted Patch-wise Classification Using C1--C5 Reporting Categories}},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.20763900},
  url       = {https://doi.org/10.5281/zenodo.20763900}
}
```
