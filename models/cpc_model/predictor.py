"""CPC (C-Phycocyanin) concentration predictor from spirulina images.

Architecture: CNN encoder (ConvTrunk) -> XGBoost regressor, trained on the
Chong et al. 2025 dataset (~11,520 images, 6 days, pooled all conditions).

Preprocessing (must match training exactly):
  - 75% centre-crop → resize to target_size (default 128x128)
  - BGR channel order (cv2.imread native), scale to [0, 1]
  - retention and target_size are baked into the checkpoint

Training-data CPC range: 0.076 – 0.446 mg/mL (random-split R²=0.988).

Model file: bundled in this package under artifacts/. Set env var
CPC_MODEL_PATH to override (e.g. to point at a newer checkpoint).
"""

from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn as nn

_DEFAULT_PATH = Path(__file__).parent / "artifacts" / "biomass_cpc_model_random_split.pt"
_CPC_RANGE = (0.076, 0.446)  # mg/mL — training data bounds


class _ConvTrunk(nn.Module):
    """5-layer CNN backbone identical to the one used during training."""

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(3, 16, 3),   nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(16, 32, 3),  nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3),  nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(128, 256, 3), nn.ReLU(),
            nn.AdaptiveAvgPool2d((5, 5)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class CPCPredictor:
    """Singleton: loads on first call to CPCPredictor.load()."""

    _instance: CPCPredictor | None = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @classmethod
    def load(cls) -> "CPCPredictor":
        if cls._instance is None:
            model_path = Path(os.getenv("CPC_MODEL_PATH", str(_DEFAULT_PATH)))
            ckpt = torch.load(model_path, map_location="cpu", weights_only=False)

            encoder = _ConvTrunk()
            encoder.load_state_dict(ckpt["encoder_state_dict"])
            encoder.eval()

            prep = ckpt["preprocessing"]
            inst = object.__new__(cls)
            inst._encoder = encoder
            inst._xgb = ckpt["xgboost"]
            inst._retention = float(prep["retention"])
            inst._target_size = tuple(prep["target_size"])  # (W, H) for cv2.resize
            cls._instance = inst

        return cls._instance

    # ------------------------------------------------------------------
    # Public inference API
    # ------------------------------------------------------------------

    def predict_bytes(self, image_bytes: bytes) -> dict:
        """Predict from raw image bytes (JPEG / PNG / BMP …)."""
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

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _predict_bgr(self, img_bgr: np.ndarray) -> dict:
        resized = self._crop_resize(img_bgr)
        x = resized.transpose(2, 0, 1).astype(np.float32) / 255.0  # CHW, [0,1]
        x_t = torch.from_numpy(x).unsqueeze(0)  # (1, 3, H, W)

        with torch.no_grad():
            feats = self._encoder(x_t).flatten(1).numpy()  # (1, 6400)

        cpc = float(self._xgb.predict(feats)[0])
        in_range = _CPC_RANGE[0] <= cpc <= _CPC_RANGE[1]

        return {
            "cpc_mgml": round(cpc, 4),
            "unit": "mg/mL",
            "in_training_range": in_range,
            "training_range": {"min": _CPC_RANGE[0], "max": _CPC_RANGE[1]},
        }

    def _crop_resize(self, img_bgr: np.ndarray) -> np.ndarray:
        h, w = img_bgr.shape[:2]
        nh = max(1, int(h * self._retention))
        nw = max(1, int(w * self._retention))
        top  = (h - nh) // 2
        left = (w - nw) // 2
        crop = img_bgr[top: top + nh, left: left + nw]
        return cv2.resize(crop, self._target_size)  # resize takes (W, H)
