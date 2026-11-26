"""Module A: Forest baseline classification at the 2020-12-31 cutoff date."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.pipeline import Pipeline

from forestix.features import FEATURE_COLUMNS

# Map 4-group dataset labels -> 3-class baseline status at 2020-12-31
GROUP_TO_BASELINE: dict[str, str] = {
    "G1": "FOREST",
    "G4": "FOREST",
    "G2": "NON_FOREST",
    "G3": "PLANTATION",
}


def map_group_to_baseline(group_labels: pd.Series) -> pd.Series:
    """Convert G1/G2/G3/G4 labels to 2020-12-31 baseline classes (FOREST / NON_FOREST / PLANTATION)."""
    return group_labels.map(GROUP_TO_BASELINE)


def train(features: pd.DataFrame, labels: pd.Series, spec: dict[str, Any] | None = None) -> Pipeline:
    """Train the Module A Random Forest baseline classifier on pre-cutoff features.

    Serves: CM-1, FR-03.
    """
    _ = spec
    x = features[FEATURE_COLUMNS]
    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "rf",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=6,
                    min_samples_leaf=2,
                    class_weight="balanced",
                    random_state=42,
                ),
            ),
        ]
    )
    clf.fit(x, labels)
    return clf


def predict(model: Pipeline, features: pd.DataFrame) -> pd.DataFrame:
    """Predict forest status at the cutoff date along with confidence probability.

    Serves: CM-1, FR-03.
    """
    x = features[FEATURE_COLUMNS]
    probs = model.predict_proba(x)
    classes = list(model.classes_)
    pred_idx = np.argmax(probs, axis=1)
    pred_cls = [classes[i] for i in pred_idx]
    conf = probs[np.arange(len(probs)), pred_idx]

    forest_idx = classes.index("FOREST") if "FOREST" in classes else None
    prob_forest = probs[:, forest_idx] if forest_idx is not None else np.zeros(len(probs))

    return pd.DataFrame(
        {
            "plot_id": features["plot_id"].values if "plot_id" in features.columns else range(len(x)),
            "predicted_class": pred_cls,
            "confidence": np.round(conf, 4),
            "prob_forest": np.round(prob_forest, 4),
            "is_forest_2020": [c == "FOREST" for c in pred_cls],
        }
    )


def spatial_cv(
    features: pd.DataFrame,
    labels: pd.Series,
    districts: pd.Series,
    spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Leave-One-District-Out spatial cross-validation (Zero Data Leakage Policy).

    Serves: CM-1, DS-2.
    """
    oof_rows: list[pd.DataFrame] = []
    per_district: dict[str, dict[str, Any]] = {}

    for dist in sorted(districts.unique()):
        test_mask = districts == dist
        train_mask = ~test_mask
        model = train(features[train_mask], labels[train_mask], spec)
        preds = predict(model, features[test_mask])
        preds["true_baseline"] = labels[test_mask].values
        preds["district"] = dist
        oof_rows.append(preds)

        acc_3 = float(accuracy_score(labels[test_mask], preds["predicted_class"]))
        bin_true = labels[test_mask] == "FOREST"
        bin_pred = preds["predicted_class"] == "FOREST"
        acc_bin = float(accuracy_score(bin_true, bin_pred))
        per_district[dist] = {
            "n_plots": int(test_mask.sum()),
            "accuracy_3class": round(acc_3, 4),
            "accuracy_forest_binary": round(acc_bin, 4),
        }

    oof_df = pd.concat(oof_rows, ignore_index=True)
    overall_3 = float(accuracy_score(oof_df["true_baseline"], oof_df["predicted_class"]))
    bin_true_all = oof_df["true_baseline"] == "FOREST"
    bin_pred_all = oof_df["predicted_class"] == "FOREST"
    overall_bin = float(accuracy_score(bin_true_all, bin_pred_all))

    classes_order = ["FOREST", "NON_FOREST", "PLANTATION"]
    cm = confusion_matrix(oof_df["true_baseline"], oof_df["predicted_class"], labels=classes_order)
    report = classification_report(
        oof_df["true_baseline"], oof_df["predicted_class"], labels=classes_order, zero_division=0
    )

    return {
        "per_district": per_district,
        "overall_accuracy_3class": round(overall_3, 4),
        "overall_accuracy_forest_binary": round(overall_bin, 4),
        "confusion_matrix_labels": classes_order,
        "confusion_matrix": cm.tolist(),
        "classification_report": report,
        "oof_predictions": oof_df,
    }
