"""
SnowHealth Demand Forecasting - Model Utilities
Training, evaluation, comparison, and experiment tracking helpers.
"""
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import json
import os


def compute_metrics(y_true, y_pred) -> dict:
    """Compute regression metrics."""
    return {
        "mae": round(mean_absolute_error(y_true, y_pred), 4),
        "rmse": round(np.sqrt(mean_squared_error(y_true, y_pred)), 4),
        "mape": round(np.mean(np.abs((y_true - y_pred) / np.maximum(y_true, 1))) * 100, 4),
        "r2": round(r2_score(y_true, y_pred), 4),
    }


def compare_models(results: dict) -> pd.DataFrame:
    """Compare multiple model results side-by-side."""
    rows = []
    for name, metrics in results.items():
        row = {"Model": name}
        row.update(metrics)
        rows.append(row)
    df = pd.DataFrame(rows)
    df = df.sort_values("rmse")
    return df


def get_feature_importance(model, feature_names: list, model_type: str = "xgboost") -> pd.DataFrame:
    """Extract feature importance from a trained model."""
    if model_type in ("xgboost", "lightgbm"):
        importances = model.feature_importances_
    else:
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            return pd.DataFrame({"Feature": feature_names, "Importance": [0] * len(feature_names)})
    fi_df = pd.DataFrame({
        "Feature": feature_names,
        "Importance": importances
    }).sort_values("Importance", ascending=False).reset_index(drop=True)
    fi_df["Importance_Pct"] = round(fi_df["Importance"] / fi_df["Importance"].sum() * 100, 2)
    return fi_df


def save_feature_importance_artifact(fi_df: pd.DataFrame, model_name: str, output_dir: str = "/tmp") -> str:
    """Save feature importance to a JSON artifact file."""
    artifact_path = os.path.join(output_dir, f"{model_name}_feature_importance.json")
    artifact = {
        "model_name": model_name,
        "top_features": fi_df.head(20).to_dict(orient="records"),
        "total_features": len(fi_df),
    }
    with open(artifact_path, "w") as f:
        json.dump(artifact, f, indent=2)
    return artifact_path


def generate_comparison_report(baseline_metrics: dict, tuned_metrics: dict) -> pd.DataFrame:
    """Generate baseline vs tuned model comparison report."""
    rows = []
    for metric_name in baseline_metrics:
        baseline_val = baseline_metrics[metric_name]
        tuned_val = tuned_metrics[metric_name]
        if metric_name in ("r2",):
            improvement = tuned_val - baseline_val
            pct = (improvement / abs(baseline_val)) * 100 if baseline_val != 0 else 0
        else:
            improvement = baseline_val - tuned_val
            pct = (improvement / baseline_val) * 100 if baseline_val != 0 else 0
        rows.append({
            "Metric": metric_name.upper(),
            "Baseline": round(baseline_val, 4),
            "Tuned": round(tuned_val, 4),
            "Improvement": round(improvement, 4),
            "Improvement_Pct": round(pct, 2),
        })
    return pd.DataFrame(rows)


def create_prediction_df(y_true, y_pred, feature_df: pd.DataFrame, model_name: str) -> pd.DataFrame:
    """Create a DataFrame with predictions and metadata for monitoring."""
    pred_df = feature_df[["STORE_ID", "SKU_ID", "TRANSACTION_DATE"]].copy()
    pred_df["ACTUAL_UNITS"] = y_true.values if hasattr(y_true, "values") else y_true
    pred_df["PREDICTED_UNITS"] = np.round(y_pred).astype(int)
    pred_df["RESIDUAL"] = pred_df["ACTUAL_UNITS"] - pred_df["PREDICTED_UNITS"]
    pred_df["ABS_ERROR"] = np.abs(pred_df["RESIDUAL"])
    pred_df["MODEL_NAME"] = model_name
    pred_df["PREDICTION_TIMESTAMP"] = pd.Timestamp.now()
    return pred_df
