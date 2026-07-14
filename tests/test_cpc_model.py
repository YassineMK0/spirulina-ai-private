"""Tests for the CPC image predictor (models/cpc_model).

Unit tests use a synthetic 128x128 BGR image so they don't require real
spirulina photos. The model file is loaded from CPC_MODEL_PATH or the
default Windows path — tests are skipped if it doesn't exist.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

MODEL_PATH = Path(
    os.getenv(
        "CPC_MODEL_PATH",
        r"G:\cpc detection\second and third\biomass_cpc_model_random_split.pt",
    )
)

pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason=f"CPC model file not found: {MODEL_PATH}",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_image_bytes(h: int = 200, w: int = 200, fmt: str = ".jpg") -> bytes:
    """Return JPEG/PNG-encoded bytes of a synthetic green-tinted image."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :, 1] = 80   # green channel — spirulina-ish colour
    img[:, :, 0] = 20   # some blue
    success, buf = cv2.imencode(fmt, img)
    assert success, f"cv2.imencode failed for {fmt}"
    return buf.tobytes()


# ---------------------------------------------------------------------------
# CPCPredictor unit tests
# ---------------------------------------------------------------------------

class TestCPCPredictor:
    def test_load_returns_singleton(self):
        from models.cpc_model.predictor import CPCPredictor
        a = CPCPredictor.load()
        b = CPCPredictor.load()
        assert a is b

    def test_predict_bytes_returns_expected_keys(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes())
        assert "cpc_mgml" in result
        assert "unit" in result
        assert "in_training_range" in result
        assert "training_range" in result

    def test_predict_bytes_cpc_is_float(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes())
        assert isinstance(result["cpc_mgml"], float)

    def test_predict_bytes_unit_is_mgml(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes())
        assert result["unit"] == "mg/mL"

    def test_predict_bytes_training_range_shape(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes())
        r = result["training_range"]
        assert r["min"] < r["max"]

    def test_predict_bytes_various_sizes(self):
        """Predictor must handle any input resolution (adaptive pool inside CNN)."""
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        for (h, w) in [(64, 64), (128, 128), (480, 640), (1080, 1920)]:
            result = predictor.predict_bytes(_make_image_bytes(h, w))
            assert isinstance(result["cpc_mgml"], float), f"failed for {h}x{w}"

    def test_predict_bytes_png_format(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes(fmt=".png"))
        assert isinstance(result["cpc_mgml"], float)

    def test_predict_bytes_invalid_data_raises(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        with pytest.raises(ValueError, match="could not decode"):
            predictor.predict_bytes(b"not-an-image")

    def test_predict_path(self, tmp_path):
        from models.cpc_model.predictor import CPCPredictor
        img = np.zeros((150, 150, 3), dtype=np.uint8)
        img[:, :, 1] = 60
        p = tmp_path / "test.jpg"
        cv2.imwrite(str(p), img)
        predictor = CPCPredictor.load()
        result = predictor.predict_path(p)
        assert isinstance(result["cpc_mgml"], float)

    def test_predict_path_missing_file_raises(self):
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        with pytest.raises(FileNotFoundError):
            predictor.predict_path("/nonexistent/path/image.jpg")

    def test_cpc_value_plausible(self):
        """CPC for a plain synthetic image should be close to training-range bounds."""
        from models.cpc_model.predictor import CPCPredictor
        predictor = CPCPredictor.load()
        result = predictor.predict_bytes(_make_image_bytes())
        # Very loose bound — the model was never trained on synthetic images.
        # We just verify the output isn't wildly nonsensical (e.g. NaN or 1e9).
        assert -10.0 < result["cpc_mgml"] < 10.0


# ---------------------------------------------------------------------------
# FastAPI endpoint integration test
# ---------------------------------------------------------------------------

class TestCPCEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from api.main import app
        return TestClient(app)

    def test_cpc_predict_returns_200(self, client):
        image_bytes = _make_image_bytes()
        resp = client.post(
            "/cpc/predict",
            files={"file": ("test.jpg", io.BytesIO(image_bytes), "image/jpeg")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "cpc_mgml" in data

    def test_cpc_predict_invalid_image_returns_422(self, client):
        resp = client.post(
            "/cpc/predict",
            files={"file": ("bad.jpg", io.BytesIO(b"garbage"), "image/jpeg")},
        )
        assert resp.status_code == 422

    def test_cpc_predict_empty_file_returns_400(self, client):
        resp = client.post(
            "/cpc/predict",
            files={"file": ("empty.jpg", io.BytesIO(b""), "image/jpeg")},
        )
        assert resp.status_code == 400
