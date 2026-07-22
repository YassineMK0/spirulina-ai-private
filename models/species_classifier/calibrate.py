"""Regenerate artifacts/raw_feature_stats.joblib -- see README.md for why
this calibration step exists. Run manually if features.py's extraction
pipeline changes; not part of the request-serving path.

Usage:
    python -m models.species_classifier.calibrate
"""
from __future__ import annotations

import os
import random
from pathlib import Path

import cv2
import joblib
import numpy as np

from .features import extract_features

DATASET_ROOT = Path(
    r"G:\classification 5aza\Scope_3_Microalgae_shape_texture_convolution_classification-main\Microalgae_Image_Dataset"
)
BATCHES = ["Batch_1", "Batch_2", "Batch_3"]
CLASSES = ["Chlamydomonas_Reinhardtii", "Chlorella_FSP", "Spirulina_Platensis"]
N_PER_CLASS_PER_BATCH = 70
OUTPUT_PATH = Path(__file__).parent / "artifacts" / "raw_feature_stats.joblib"


def main() -> None:
    random.seed(7)
    rows = []
    n_errors = 0

    for batch in BATCHES:
        for cls in CLASSES:
            folder = DATASET_ROOT / batch / cls
            files = sorted(os.listdir(folder))
            sample = random.sample(files, min(N_PER_CLASS_PER_BATCH, len(files)))
            for fname in sample:
                img = cv2.imread(str(folder / fname))
                if img is None:
                    n_errors += 1
                    continue
                try:
                    rows.append(extract_features(img))
                except ValueError:
                    n_errors += 1
        print(f"  done {batch}  n={len(rows)}  errors={n_errors}")

    X = np.array(rows)
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1.0  # guard against a degenerate constant feature

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    joblib.dump({"mean": mean, "std": std, "n_samples": len(rows)}, OUTPUT_PATH)
    print(f"\nsaved calibration stats from {len(rows)} images ({n_errors} errors) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
