# Species classifier

Classifies a microalgae microscope image into `Chlamydomonas_Reinhardtii`,
`Chlorella_FSP`, or `Spirulina_Platensis` (31 classical shape/texture
features -> StandardScaler -> XGBoost). Source model:
`G:\classification 5aza\Scope_3_Microalgae_shape_texture_convolution_classification-main\trained_models\`
(Chong et al. 2025, ~97% reported test accuracy).

For a spirulina farm, a non-`Spirulina_Platensis` prediction is a
contamination signal.

## Why `artifacts/raw_feature_stats.joblib` exists

The source repo's own per-feature-family extraction scripts each fit a
`StandardScaler` on their own raw features (population mean/std over their
image batch) and exported the *already-normalized* values. The combined
CSVs built from those exports were then fed into a second `StandardScaler`
(saved as the source repo's `scaler.joblib`) -- whose `mean_`/`scale_` are
therefore ~0/~1 (confirmed empirically), i.e. it's a near-identity transform
on top of normalization that isn't reproducible at inference time from a
single image, because it depends on population statistics that were never
saved.

`raw_feature_stats.joblib` reconstructs the missing first-stage mean/std by
sampling ~630 images (70 per class per batch) from the source repo's
`Microalgae_Image_Dataset/` and computing the same per-feature population
statistics. `predictor.py` applies this calibration before the source
repo's own `scaler.joblib`. Validated against a fresh 75-image sample:
97.3% accuracy, matching the paper's reported figure. Regenerate via
`models/species_classifier/calibrate.py` if the feature-extraction pipeline
in `features.py` ever changes.
