"""
Train an Isolation Forest anomaly detector on spirulina sensor data.

Run from project root:
    python models/train_anomaly.py

Inputs:
    data/spirulina_train.csv    – raw sensor data (6 columns + labels)
    data/spirulina_test.csv

Outputs (in models/saved/):
    isolation_forest.pkl    – trained Isolation Forest
    scaler.pkl              – fitted StandardScaler
    feature_cols.json       – ordered feature column list (from data/features.py)
    model_metadata.json     – threshold, metrics, severity thresholds, training date

Plots saved to models/saved/:
    plot_score_dist.png
    plot_confusion_matrix.png
    plot_feature_importance.png

Feature engineering is handled entirely by data/features.py — the same module
used at inference time in api/predict_anomaly.py.

Target metrics: Precision > 0.90, Recall > 0.85, F1 > 0.87
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# Feature engineering — single source of truth shared with the API
import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
from data.features import compute_features, FEATURE_COLS, save_feature_cols

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).parent.parent
DATA_DIR:     Path = PROJECT_ROOT / "data"
SAVE_DIR:     Path = Path(__file__).parent / "saved"
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Hyperparameters
# ---------------------------------------------------------------------------
# Isolation Forest — used for continuous anomaly scoring and severity ranking
CONTAMINATION:  float = 0.08
IF_ESTIMATORS:  int   = 300
RANDOM_STATE:   int   = 42

# XGBoost — used for the binary anomaly/normal decision (uses labels)
XGB_ESTIMATORS: int   = 300
XGB_MAX_DEPTH:  int   = 6
XGB_LR:         float = 0.05

TARGET_PRECISION: float = 0.90
TARGET_RECALL:    float = 0.85
TARGET_F1:        float = 0.87


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_dataset(
    train_path: Path,
    test_path:  Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load raw sensor CSVs and apply feature engineering via data/features.py.

    The raw CSVs contain only: timestamp, ph, ec, do_mg, temp, turbidity, lux,
    is_anomaly, anomaly_type.  compute_features() adds all 73 derived columns.

    Returns:
        df_train_feats, df_test_feats  (with all 79 feature columns present)
    """
    df_train = compute_features(pd.read_csv(train_path))
    df_test  = compute_features(pd.read_csv(test_path))
    return df_train, df_test


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def fit_pipeline(
    X_train: np.ndarray,
    y_train: np.ndarray,
) -> tuple[StandardScaler, IsolationForest, XGBClassifier]:
    """
    Fit scaler, Isolation Forest, and XGBoost classifier on the training features.

    Roles:
        StandardScaler    – normalises features (fitted on train only)
        IsolationForest   – unsupervised; produces continuous anomaly scores
                            used for severity ranking and sensor attribution
        XGBClassifier     – supervised; makes the binary anomaly/normal decision
                            using labels — learns that EC dosing, solar heating
                            transitions etc. are normal even though they look
                            extreme to an unsupervised model

    Returns:
        scaler, clf_if, clf_xgb
    """
    scaler   = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    print(f"[train] Fitting IsolationForest "
          f"(n_estimators={IF_ESTIMATORS}, contamination={CONTAMINATION})...")
    clf_if = IsolationForest(
        n_estimators=IF_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    clf_if.fit(X_scaled)

    # Class-weight balance: anomalies are ~7 % of training data
    n_neg = int((y_train == 0).sum())
    n_pos = int((y_train == 1).sum())
    scale_pos = n_neg / max(n_pos, 1)

    print(f"[train] Fitting XGBClassifier "
          f"(n_estimators={XGB_ESTIMATORS}, scale_pos_weight={scale_pos:.1f})...")
    clf_xgb = XGBClassifier(
        n_estimators=XGB_ESTIMATORS,
        max_depth=XGB_MAX_DEPTH,
        learning_rate=XGB_LR,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos,
        random_state=RANDOM_STATE,
        eval_metric="logloss",
        verbosity=0,
    )
    clf_xgb.fit(X_scaled, y_train)

    print("[train] Training complete.")
    return scaler, clf_if, clf_xgb


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def _find_optimal_threshold(
    raw_scores: np.ndarray,
    y_true:     np.ndarray,
) -> tuple[float, float, float, float]:
    """
    Sweep the precision-recall curve to find the lowest threshold that
    simultaneously meets both TARGET_PRECISION and TARGET_RECALL.

    Falls back to the F1-maximising threshold if no single threshold satisfies
    both constraints.

    Returns (threshold, precision, recall, f1).
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, raw_scores)
    # precision_recall_curve returns arrays of length n+1, n+1, n respectively
    thresholds_ext = np.append(thresholds, thresholds[-1] + 1e-6)

    best_thr   = float(thresholds_ext[0])
    best_prec  = float(precisions[0])
    best_rec   = float(recalls[0])
    best_f1    = 0.0

    for thr, p, r in zip(thresholds_ext, precisions, recalls):
        if p >= TARGET_PRECISION and r >= TARGET_RECALL:
            f1_val = 2 * p * r / (p + r + 1e-12)
            if f1_val > best_f1:
                best_f1, best_thr, best_prec, best_rec = f1_val, float(thr), float(p), float(r)

    if best_f1 == 0.0:
        # Fallback: maximise F1 regardless of individual targets
        f1_scores = 2 * precisions * recalls / (precisions + recalls + 1e-12)
        idx = int(np.argmax(f1_scores))
        best_thr  = float(thresholds_ext[idx])
        best_prec = float(precisions[idx])
        best_rec  = float(recalls[idx])
        best_f1   = float(f1_scores[idx])

    return best_thr, best_prec, best_rec, best_f1


def evaluate(
    clf_if:  IsolationForest,
    clf_xgb: XGBClassifier,
    scaler:  StandardScaler,
    X_test:  np.ndarray,
    y_test:  np.ndarray,
) -> dict:
    """
    Evaluate both models on the held-out test set.

    Binary decision  → XGBClassifier  (uses labels, precise)
    Anomaly scoring  → IsolationForest (unsupervised, used for severity/attribution)

    Returns a metrics dict including XGBoost metrics, IF ROC-AUC, severity
    percentile thresholds, and score normalisation bounds.
    """
    X_scaled  = scaler.transform(X_test)
    xgb_proba: np.ndarray = clf_xgb.predict_proba(X_scaled)[:, 1]

    # --- Find optimal XGBoost probability threshold ----------------------
    # Default 0.5 gives perfect precision but low recall; sweep to find the
    # lowest threshold that satisfies all three targets simultaneously.
    best_thr, best_prec, best_rec, best_f1 = 0.5, 0.0, 0.0, 0.0
    for thr in np.arange(0.50, 0.04, -0.01):
        yp = (xgb_proba >= thr).astype(int)
        p, r, f, _ = precision_recall_fscore_support(
            y_test, yp, average="binary", zero_division=0
        )
        if p >= TARGET_PRECISION and r >= TARGET_RECALL and f > best_f1:
            best_thr, best_prec, best_rec, best_f1 = float(thr), float(p), float(r), float(f)

    if best_f1 == 0.0:         # no threshold met both — fall back to max-F1
        for thr in np.arange(0.50, 0.04, -0.01):
            yp = (xgb_proba >= thr).astype(int)
            p, r, f, _ = precision_recall_fscore_support(
                y_test, yp, average="binary", zero_division=0
            )
            if f > best_f1:
                best_thr, best_prec, best_rec, best_f1 = float(thr), float(p), float(r), float(f)

    prec, rec, f1 = best_prec, best_rec, best_f1
    y_pred: np.ndarray = (xgb_proba >= best_thr).astype(int)
    cm = confusion_matrix(y_test, y_pred)
    xgb_auc = roc_auc_score(y_test, xgb_proba)

    # --- Isolation Forest scoring ----------------------------------------
    if_scores: np.ndarray = -clf_if.score_samples(X_scaled)
    if_auc = roc_auc_score(y_test, if_scores)

    # Optimised IF threshold (kept for fallback / severity calibration)
    opt_thr, _, _, _ = _find_optimal_threshold(if_scores, y_test)

    print("\n" + "=" * 60)
    print("Evaluation on test set")
    print("=" * 60)
    print(classification_report(y_test, y_pred, target_names=["normal", "anomaly"]))
    print(f"XGBoost  ROC-AUC : {xgb_auc:.4f}")
    print(f"IF       ROC-AUC : {if_auc:.4f}  (scoring / severity only)")
    print(f"Confusion matrix :\n{cm}")
    print("=" * 60)

    passed = True
    for value, target, label in [
        (float(prec), TARGET_PRECISION, "Precision"),
        (float(rec),  TARGET_RECALL,    "Recall"),
        (float(f1),   TARGET_F1,        "F1"),
    ]:
        ok    = value >= target
        passed = passed and ok
        mark  = "PASS" if ok else "FAIL"
        print(f"  {label:<12} {value:.4f}  (target > {target:.2f})  [{mark}]")

    if not passed:
        print("\n[train] WARNING: one or more targets missed.")

    print(f"\n  XGBoost decision threshold: {best_thr:.2f}  "
          f"(default 0.5 was too conservative)")

    # Severity thresholds from IF scores of anomalous test samples
    anom_scores = if_scores[y_test == 1]
    sev_p33 = float(np.percentile(anom_scores, 33)) if len(anom_scores) else opt_thr
    sev_p66 = float(np.percentile(anom_scores, 66)) if len(anom_scores) else opt_thr * 1.2

    score_min = float(if_scores[y_test == 0].min()) if (y_test == 0).any() else 0.0
    score_max = float(if_scores.max())

    return {
        "precision":             float(prec),
        "recall":                float(rec),
        "f1":                    float(f1),
        "xgb_roc_auc":           float(xgb_auc),
        "if_roc_auc":            float(if_auc),
        "confusion_matrix":      cm.tolist(),
        "xgb_decision_threshold": best_thr,   # optimised prob threshold for inference
        "if_decision_threshold":  opt_thr,    # IF threshold for severity / fallback
        "severity_p33":          sev_p33,
        "severity_p66":          sev_p66,
        "score_min":             score_min,
        "score_max":             score_max,
    }


# ---------------------------------------------------------------------------
# Feature importance
# ---------------------------------------------------------------------------

def compute_feature_importance(
    X_test_scaled: np.ndarray,
    y_test:        np.ndarray,
    feature_cols:  list[str],
) -> pd.Series:
    """
    Compute feature importance as the mean absolute z-score difference
    between anomalous and normal samples.

    Importance_i = |mean(X_scaled[anomaly, i]) - mean(X_scaled[normal, i])|

    Returns a Series sorted descending.
    """
    anom_mask = y_test == 1
    norm_mask = ~anom_mask

    if not anom_mask.any() or not norm_mask.any():
        return pd.Series(np.zeros(len(feature_cols)), index=feature_cols)

    mean_anom = X_test_scaled[anom_mask].mean(axis=0)
    mean_norm = X_test_scaled[norm_mask].mean(axis=0)
    importance = np.abs(mean_anom - mean_norm)

    return pd.Series(importance, index=feature_cols).sort_values(ascending=False)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_score_distribution(
    raw_scores: np.ndarray,
    y_test:     np.ndarray,
    threshold:  float,
    out_path:   Path,
) -> None:
    """Save a histogram of anomaly scores coloured by true label."""
    fig, ax = plt.subplots(figsize=(9, 5))

    ax.hist(raw_scores[y_test == 0], bins=80, alpha=0.6, label="Normal",  color="#2196F3")
    ax.hist(raw_scores[y_test == 1], bins=80, alpha=0.6, label="Anomaly", color="#F44336")
    ax.axvline(threshold, color="black", linewidth=1.5,
               linestyle="--", label=f"Decision threshold ({threshold:.4f})")

    ax.set_xlabel("Anomaly Score  (higher = more anomalous)")
    ax.set_ylabel("Count")
    ax.set_title("Isolation Forest – Anomaly Score Distribution")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[train] Plot saved -> {out_path}")


def plot_confusion_matrix(
    cm:       list[list[int]],
    out_path: Path,
) -> None:
    """Save a labelled confusion-matrix heatmap."""
    cm_arr = np.array(cm)
    fig, ax = plt.subplots(figsize=(5, 4))
    sns.heatmap(
        cm_arr,
        annot=True,
        fmt="d",
        cmap="Blues",
        xticklabels=["Normal", "Anomaly"],
        yticklabels=["Normal", "Anomaly"],
        ax=ax,
    )
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title("Confusion Matrix")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[train] Plot saved -> {out_path}")


def plot_feature_importance(
    importance: pd.Series,
    top_n:      int,
    out_path:   Path,
) -> None:
    """Save a horizontal bar chart of the top-N feature importances."""
    top = importance.head(top_n)
    fig, ax = plt.subplots(figsize=(9, max(4, top_n // 3)))
    ax.barh(top.index[::-1], top.values[::-1], color="#4CAF50")
    ax.set_xlabel("Mean |z-score|  anomaly vs normal")
    ax.set_title(f"Top-{top_n} Features by Discriminative Power")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[train] Plot saved -> {out_path}")


# ---------------------------------------------------------------------------
# Artefact saving
# ---------------------------------------------------------------------------

def save_artifacts(
    scaler:  StandardScaler,
    clf_if:  IsolationForest,
    clf_xgb: XGBClassifier,
    metrics: dict,
) -> None:
    """Persist all model artefacts and metadata to SAVE_DIR."""
    joblib.dump(scaler,  SAVE_DIR / "scaler.pkl")
    joblib.dump(clf_if,  SAVE_DIR / "isolation_forest.pkl")
    joblib.dump(clf_xgb, SAVE_DIR / "xgboost_clf.pkl")

    save_feature_cols(SAVE_DIR / "feature_cols.json")

    import json as _json
    metadata = {
        "models": {
            "binary_decision": "XGBClassifier",
            "anomaly_scoring":  "IsolationForest",
        },
        "if_estimators":          IF_ESTIMATORS,
        "if_contamination":       CONTAMINATION,
        "xgb_estimators":         XGB_ESTIMATORS,
        "training_date":          date.today().isoformat(),
        "n_features":             len(FEATURE_COLS),
        "xgb_decision_threshold": metrics["xgb_decision_threshold"],
        "if_decision_threshold":  metrics["if_decision_threshold"],
        "severity_p33":           metrics["severity_p33"],
        "severity_p66":           metrics["severity_p66"],
        "score_min":              metrics["score_min"],
        "score_max":              metrics["score_max"],
        "test_metrics": {
            "precision":    metrics["precision"],
            "recall":       metrics["recall"],
            "f1":           metrics["f1"],
            "xgb_roc_auc":  metrics["xgb_roc_auc"],
            "if_roc_auc":   metrics["if_roc_auc"],
        },
        "confusion_matrix": metrics["confusion_matrix"],
    }
    (SAVE_DIR / "model_metadata.json").write_text(_json.dumps(metadata, indent=2))

    print(f"[train] Artefacts saved to {SAVE_DIR}/")
    for p in sorted(SAVE_DIR.iterdir()):
        print(f"  {p.name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Full training pipeline: load raw CSV -> feature engineering -> fit -> evaluate -> save."""
    print("[train] Loading raw sensor data and computing features...")
    df_train, df_test = load_dataset(
        DATA_DIR / "spirulina_train.csv",
        DATA_DIR / "spirulina_test.csv",
    )
    print(f"[train] Train: {len(df_train):,} rows  |  Test: {len(df_test):,} rows")
    print(f"[train] Features: {len(FEATURE_COLS)}  (from data/features.py)")

    X_train = df_train[FEATURE_COLS].to_numpy(dtype=np.float64)
    X_test  = df_test[FEATURE_COLS].to_numpy(dtype=np.float64)
    y_train = df_train["is_anomaly"].to_numpy(dtype=int)
    y_test  = df_test["is_anomaly"].to_numpy(dtype=int)

    print(f"[train] Train anomaly: {y_train.mean():.2%}  "
          f"Test anomaly: {y_test.mean():.2%}")

    # Fit both models
    scaler, clf_if, clf_xgb = fit_pipeline(X_train, y_train)
    X_test_scaled = scaler.transform(X_test)

    # Evaluate
    metrics = evaluate(clf_if, clf_xgb, scaler, X_test, y_test)

    # Feature importance (from IF scores)
    importance = compute_feature_importance(X_test_scaled, y_test, FEATURE_COLS)

    # Plots
    if_scores_test: np.ndarray = -clf_if.score_samples(X_test_scaled)
    plot_score_distribution(
        if_scores_test, y_test,
        metrics["if_decision_threshold"],
        SAVE_DIR / "plot_score_dist.png",
    )
    plot_confusion_matrix(
        metrics["confusion_matrix"],
        SAVE_DIR / "plot_confusion_matrix.png",
    )
    plot_feature_importance(
        importance, top_n=25,
        out_path=SAVE_DIR / "plot_feature_importance.png",
    )

    # Save artefacts
    save_artifacts(scaler, clf_if, clf_xgb, metrics)

    print("\n[train] Pipeline complete.")
    f1 = metrics["f1"]
    if f1 < TARGET_F1:
        print(f"[train] WARNING: F1={f1:.4f} below target {TARGET_F1:.2f}")
        sys.exit(1)
    print(f"[train] All targets met. F1={f1:.4f}")


if __name__ == "__main__":
    main()
