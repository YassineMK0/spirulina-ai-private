"""Feature extraction reconstructing the "Optimised_image_pre-processing_combined"
31-feature set the species-classifier XGBoost model was trained on.

Source repo: G:\\classification 5aza\\Scope_3_Microalgae_shape_texture_convolution_classification-main
The exact script that combined the four feature families into that dataset
isn't present in the source repo (only its output CSVs are) -- this
reconstructs it from the individual per-family scripts, picking the variant
each script's own header comment or column/bin count matches:
  - Geometrical: Canny edge detection (its script header says "Best results
    for geometrical features"; the Adaptive-Threshold/no-threshold variants
    are both labelled "Base case").
  - Hu moments / GLCM / LBP: plain grayscale, no extra preprocessing (their
    "_Multi_Img_Process" alternates are exploratory -- the LBP one even calls
    cv2.imshow()/cv2.waitKey(0), which would hang a batch run over thousands
    of images, so it can't be what produced the training CSVs).
Validated against the labeled source dataset -- see verify_species_classifier.py.
"""
from __future__ import annotations

import numpy as np
import cv2
from skimage.feature import graycomatrix, graycoprops, local_binary_pattern

_GLCM_DISTANCES = [1, 3, 5]
_GLCM_ANGLES = [0, np.pi / 4, np.pi / 2, 3 * np.pi / 4]
_GLCM_PROPS = ["contrast", "dissimilarity", "homogeneity", "energy", "correlation"]
_TEXTURE_SIZE = (512, 512)  # (W, H) for cv2.resize
_LBP_N_POINTS = 8
_LBP_RADIUS = 3


def _hu_moments(gray: np.ndarray) -> np.ndarray:
    # findContours needs an actual binary image to find meaningful per-object
    # contours -- calling it on raw grayscale (as the source repo's simplest
    # "_Gray" Hu-moments script does) degenerates to one contour around
    # ~the whole frame, producing a near-identical Hu vector for every image
    # regardless of content (confirmed empirically). Threshold first, using
    # the same bilateral-blur + adaptive-threshold the source repo's
    # "_Multi_Img_Process" Hu-moments variant uses for exactly this reason.
    blurred = cv2.bilateralFilter(gray, 40, 1, 25)
    thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hu_list = [cv2.HuMoments(cv2.moments(c)).flatten() for c in contours]
    if not hu_list:
        raise ValueError("no contours found for Hu-moments extraction")
    return np.mean(hu_list, axis=0)


def _geometrical(gray: np.ndarray) -> np.ndarray:
    canny = cv2.Canny(gray, 150, 175)
    contours, _ = cv2.findContours(canny, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    rows = []
    for cnt in contours:
        if len(cnt) < 5:
            continue  # cv2.fitEllipse requires at least 5 points

        area = cv2.contourArea(cnt)
        perimeter = cv2.arcLength(cnt, True)
        _, (w, h), _ = cv2.minAreaRect(cnt)
        feret_diameter = max(w, h)

        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = float(area) / hull_area if hull_area else 0.0
        convexity = float(area) / hull_area if hull_area else 0.0

        rect = cv2.boundingRect(cnt)
        rect_area = rect[2] * rect[3]
        extent = float(area) / rect_area if rect_area else 0.0

        aspect_ratio = float(w) / h if w > h else float(h) / w
        circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter else 0.0

        (_, _), (MA, ma), _ = cv2.fitEllipse(cnt)
        eccentricity = np.sqrt(1 - (MA / ma) ** 2) if ma else 0.0

        rows.append([eccentricity, convexity, feret_diameter, area, perimeter,
                     solidity, extent, aspect_ratio, circularity])

    if not rows:
        raise ValueError("no contours found for geometrical-feature extraction")
    return np.mean(rows, axis=0)


def _glcm(gray: np.ndarray) -> np.ndarray:
    resized = cv2.resize(gray, _TEXTURE_SIZE)
    glcm = graycomatrix(resized, distances=_GLCM_DISTANCES, angles=_GLCM_ANGLES,
                         levels=256, symmetric=True, normed=True)
    # Matches the source script exactly: only the (distance=1, angle=0) cell
    # of each property matrix is used, not an average across distances/angles.
    return np.array([graycoprops(glcm, prop).ravel()[0] for prop in _GLCM_PROPS])


def _lbp(gray: np.ndarray) -> np.ndarray:
    resized = cv2.resize(gray, _TEXTURE_SIZE)
    lbp = local_binary_pattern(resized, _LBP_N_POINTS, _LBP_RADIUS, method="uniform")
    hist, _ = np.histogram(lbp.ravel(), bins=np.arange(0, _LBP_N_POINTS + 3),
                            range=(0, _LBP_N_POINTS + 2))
    hist = hist.astype(float)
    hist /= (hist.sum() + 1e-7)
    return hist


def extract_features(img_bgr: np.ndarray) -> np.ndarray:
    """Return the 31 features in the exact order of feature_names.joblib:
    Hu_1..7, Eccentricity, Convexity, FeretDiameter, Area, Perimeter,
    Solidity, Extent, AspectRatio, Circularity, contrast, dissimilarity,
    homogeneity, energy, correlation, feature_0..9 (LBP histogram)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return np.concatenate([
        _hu_moments(gray),
        _geometrical(gray),
        _glcm(gray),
        _lbp(gray),
    ])
