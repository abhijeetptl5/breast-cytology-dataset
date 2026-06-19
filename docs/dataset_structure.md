# Dataset structure

The main Zenodo record contains `breast-cytology-main.zip`. After extraction, the expected top-level folders are:

- `geojson/`: WSI-level GeoJSON annotation files. Each file corresponds to one WSI and contains rectangular patch-coordinate annotations.
- `patches/`: Extracted image patches organized by WSI and class folder.
- `metadata/`: Public CSV metadata files and metadata README.
- `manifest/`: Zenodo WSI file manifest.

WSIs are distributed across linked Zenodo records and are listed in `manifest/zenodo_files_manifest.csv`. The WSI format is NDPI.
