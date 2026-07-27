"""Microalgae species classifier from a microscope image.

Architecture: 31 classical shape/texture features (Hu moments, geometrical,
GLCM, LBP -- see features.py) -> StandardScaler -> XGBoost classifier,
trained on the Chong et al. 2025 dataset (9450 images, 3 species),
~97% test accuracy (see trained_models/comparison_report.md in the source
repo). For a spirulina farm, a prediction other than Spirulina_Platensis is
a contamination signal.

Model files: bundled in this package under artifacts/ (xgboost_model.joblib,
scaler.joblib, label_encoder.joblib, feature_names.joblib). Set env var
SPECIES_MODEL_DIR to override (e.g. to point at a newer/retrained set).
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import joblib
import numpy as np

from .features import extract_features

_DEFAULT_DIR = Path(__file__).parent / "artifacts"
_CALIBRATION_PATH = Path(__file__).parent / "artifacts" / "raw_feature_stats.joblib"
_TARGET_SPECIES = "Spirulina_Platensis"


class SpeciesClassifier:
    """Singleton: loads on first call to SpeciesClassifier.load()."""

    _instance: "SpeciesClassifier | None" = None

    @classmethod
    def load(cls) -> "SpeciesClassifier":
        if cls._instance is None:
            model_dir = Path(os.getenv("SPECIES_MODEL_DIR", str(_DEFAULT_DIR)))

            inst = object.__new__(cls)
            inst._model = joblib.load(model_dir / "xgboost_model.joblib")
            inst._scaler = joblib.load(model_dir / "scaler.joblib")
            inst._label_encoder = joblib.load(model_dir / "label_encoder.joblib")
            inst._feature_names = joblib.load(model_dir / "feature_names.joblib")
            # The source repo's own per-feature-family scripts each z-score
            # normalized their raw features (population mean/std over their
            # image batch) *before* export -- scaler.joblib was then fit on
            # top of that already-normalized data (confirmed: its mean_/
            # scale_ are ~0/~1), so it alone can't undo raw pixel-scale
            # features at inference time. This calibration file holds the
            # missing first-stage population mean/std, computed by sampling
            # the source dataset -- see models/species_classifier/README.md.
            calib = joblib.load(_CALIBRATION_PATH)
            inst._calib_mean = calib["mean"]
            inst._calib_std = calib["std"]
            cls._instance = inst

        return cls._instance

    def predict_bytes(self, image_bytes: bytes) -> dict:
        """Predict from raw image bytes (JPEG / PNG / BMP ...)."""
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise ValueError("could not decode image — check format/content")
        return self._predict_bgr(img_bgr)

    def predict_path(self, path: str | Path) -> dict:
        """Predict from a file path."""
        img_bgr = cv2.imread(str(path))
        if img_bgr is None:
            raise FileNotFoundError(f"could not read image: {path}")
        return self._predict_bgr(img_bgr)

    def _predict_bgr(self, img_bgr: np.ndarray) -> dict:
        features = extract_features(img_bgr)
        calibrated = (features - self._calib_mean) / self._calib_std
        scaled = self._scaler.transform(calibrated.reshape(1, -1))

        proba = self._model.predict_proba(scaled)[0]
        classes = self._label_encoder.classes_
        probabilities = {cls: round(float(p), 4) for cls, p in zip(classes, proba)}

        best_idx = int(np.argmax(proba))
        species = str(classes[best_idx])
        confidence = round(float(proba[best_idx]), 4)
        is_target = species == _TARGET_SPECIES

        return {
            "species": species,
            "confidence": confidence,
            "probabilities": probabilities,
            "is_target_species": is_target,
            "warning": (
                None if is_target else
                f"Detected {species.replace('_', ' ')} — possible contamination, not {_TARGET_SPECIES.replace('_', ' ')}"
            ),
        }
