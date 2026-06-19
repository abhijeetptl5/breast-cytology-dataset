#!/usr/bin/env python3
"""Example: display one extracted patch."""

from pathlib import Path
from PIL import Image

patch_path = Path("/path/to/breast-cytology-main/patches/<WSI_ID>/<CLASS_FOLDER>/<PATCH_FILE>.png")
img = Image.open(patch_path).convert("RGB")
print("Patch size:", img.size)
img.show()
